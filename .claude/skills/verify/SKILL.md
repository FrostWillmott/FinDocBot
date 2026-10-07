---
name: verify
description: Run the FinDocBot API against a throwaway Postgres and a stub Ollama to observe a change at the HTTP surface.
---

# Verifying FinDocBot changes at the API

The surface is the FastAPI app (`/documents/upload`, `/search`, `/ask`).
Drive it with curl; don't run pytest here.

## Isolated stack (doesn't touch `make up` state or ports 5432/8000/11434)

```bash
S=<scratch dir>
# Postgres on a spare port
docker run -d --rm --name findocbot-verify-db \
  -e POSTGRES_DB=findocbot -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -p 127.0.0.1:55432:5432 \
  pgvector/pgvector:pg16

# Apply the Alembic migrations to the throwaway database
POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:55432/findocbot \
EMBEDDING_DIM=768 uv run alembic upgrade head

# Stub Ollama on :51434 (script below); /api/generate returns $S/mode.json verbatim
python3 $S/stub_ollama.py 51434 $S/mode.json &

OLLAMA_BASE_URL=http://127.0.0.1:51434 \
POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:55432/findocbot \
  uv run uvicorn findocbot.main:create_app --factory --host 127.0.0.1 --port 58000 &

curl -F "file=@docs/samples/aurora-ridge-annual-report-2025.pdf;type=application/pdf" \
  http://127.0.0.1:58000/documents/upload
# Returns 202 with {"document_id": "...", "status": "pending"}; the worker
# parses/embeds in the background, so poll the document:
curl http://127.0.0.1:58000/documents/<document_id>
# ...until "status" is "ready" (or "failed" with an "error").
```

Stub Ollama (embeddings must be 768-dim to pass the repository's length check):

```python
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def do_GET(self):  # /health pings /api/version
        data = json.dumps({"version": "stub"}).encode()
        self.send_response(200 if self.path == "/api/version" else 404)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/embed":
            out = {"embeddings": [[0.1] * 768 for _ in body["input"]]}
        elif self.path == "/api/generate":
            out = {"response": open(sys.argv[2]).read()}
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
```

Write the model's JSON reply to `mode.json`, then `POST /ask`
`{"question": "...", "top_k": 2}`; add the returned `session_id` to follow-up
calls (an id the server did not issue is a 404). Persisted turns:
`docker exec findocbot-verify-db psql -U postgres -d findocbot -c "select * from chat_turns"`.

## Before/after comparison

`git worktree add --detach $S/before <rev>^`, then run the venv's uvicorn with
`--app-dir $S/before/src` on another port. `--app-dir` wins over the editable
install; confirm through traceback paths in the log.

## Gotchas

- App logs go to stderr as `time LEVEL logger: message`; filter out
  uvicorn's own lines with `grep -v "INFO:"`.
- A user-run Ollama may already hold :11434, so keep the stub on its own port.
- Teardown: kill uvicorn and the stub, `docker stop findocbot-verify-db` (`--rm`
  removes it), `git worktree remove`.
