# Verification: encrypted PDFs and a missing crypto provider (2026-11-05)

**Change.** `pypdf[crypto]` is installed, so AES-encrypted PDFs with an empty user
password parse. A `DependencyError` from pypdf (no crypto provider) is logged at ERROR and
becomes an `InfrastructureError`: the document ends `failed` with a fixed message naming
the server, not the file. Checked on `master` at `13fab44` (PR #83).

**Method.** The `verify` skill: a throwaway Postgres (`pgvector/pgvector:pg16`, port 55432),
migrations applied with `alembic upgrade head`, a stub Ollama on 51434 and two app
instances. The second ran with a stub `cryptography` package first on `PYTHONPATH` whose
import raises `ImportError`, which is how pypdf sees a missing extra. Test files were built
with `tests.factories.build_encrypted_pdf_bytes`.

| Flow | Port | Result | Verdict |
|------|------|--------|---------|
| Sample report (`docs/samples`) | 58000 | `202`, then `ready`; 5 chunks | PASS |
| AES-128, empty user password | 58000 | `202`, then `ready`; 1 chunk | PASS |
| RC4-128, user password `secret` | 58000 | `202`, then `failed`: "Uploaded file is not a readable PDF: File has not been decrypted" | PASS |
| AES-128, crypto provider absent | 58001 | `202`, then `failed`: "The server cannot decrypt this PDF: its PDF library lacks a crypto provider." | PASS |
| `POST /search` over the ready documents | 58000 | hits from the sample report | PASS |

The pypdf text ("cryptography>=3.1 is required for AES algorithm") appears only in the log:

```text
ERROR findocbot.infrastructure.pdf_parser: pypdf cannot decrypt upload: cryptography>=3.1 is required for AES algorithm
WARNING findocbot.use_cases.ingestion: Ingestion of document e901edc5-... failed: The server cannot decrypt this PDF: its PDF library lacks a crypto provider.
```

**Verdict: PASS.** Not covered: a real image without `cryptography` (the missing extra is
simulated through the import), and `/ask`.
