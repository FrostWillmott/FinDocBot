# AI engineering conventions

Apply to projects integrating LLMs / building AI features. Assumes `python-core.md`.
Rule levels (`[MUST]` / `[MUST-UNLESS]` / `[PREFER]`) are defined in `_LEVELS.md`.

## LLM input is untrusted — treat it like user input from an attacker  [MUST]
Anything that reaches a prompt from an external source (user text, scraped
content, third-party API fields, documents) is attacker-controlled. Prompt
injection is the default threat, not an edge case.
- Sanitise untrusted text before it enters a prompt: neutralise (don't just
  delete) markers used in injection payloads and that mimic your own prompt
  structure — e.g. fenced code markers, "INSTRUCTIONS:", "ignore previous",
  "SYSTEM:". Neutralising (not removing) keeps the original inspectable in logs.
- Isolate untrusted spans with explicit delimiters and tell the model, in the
  instruction section, to treat everything inside purely as data and ignore any
  instructions found there. Put the real instructions *after* the untrusted
  block and state they take precedence.
- Truncate untrusted input to a sane max length before inclusion.
- This is defence in depth, not a guarantee — still treat the output as untrusted too.

## Structured outputs  [MUST for validation; PREFER for the mechanics]
- [MUST] Validate every model output against a schema (e.g. Pydantic) before
  use. Model responses are untrusted input; never `json.loads` and assume shape.
- [MUST] Handle the parse-failure path explicitly (retry, repair, or fail loudly).
- [PREFER] If asking for JSON, instruct "JSON only, no prose/fences", then strip
  stray fences defensively before parsing.

## Secrets  [MUST]
Never hardcode API keys; read from env/secret store; never log them. A provider
that ignores the key (e.g. vanilla Ollama) still gets a non-empty placeholder
from env, not a literal in source.

## Provider abstraction  [PREFER]
Treat the model provider as a swappable dependency behind an interface
(`Protocol`/ABC) selected by a factory, so a provider/model swap doesn't ripple.
Config selects the provider via a `Literal`, validated at load.

## Don't block the event loop  [MUST]
- [MUST] No blocking call inside `async def` without offloading. A synchronous
  provider SDK (common — many LLM clients are sync) is wrapped in
  `asyncio.to_thread`, not forced into a fake-async shape. "Async-first" means
  "never block the loop", not "the client library must be async".
- [PREFER] Run independent LLM calls concurrently with `asyncio.gather`.

## Resilience for long-running external-API loops  [MUST for the guards; PREFER for tuning]
When looping over an external API (bulk calls, polling), the loop must protect
itself and the remote service:
- [MUST] Timeouts on every call. Retry transient errors (429, 5xx) with
  exponential backoff; do NOT retry 4xx validation errors.
- [MUST] A circuit breaker: stop after N consecutive failures rather than
  hammering a degraded/blocking endpoint.
- [PREFER] Adaptive delay (grow on error, shrink on success) plus random jitter
  to avoid lock-step request patterns. Specific thresholds are tuning, not law.
- [MUST] An explicit stop criterion and a cancellation check for cancellable jobs.

## Idempotency & external memory  [PREFER]
Cache processed item IDs (e.g. Redis with TTL) and filter them out before
reprocessing; design the loop so a re-run doesn't duplicate side effects.

## Cost & observability  [PREFER]
Log token usage and latency per call; cache repeated inputs; set max output
tokens deliberately, never unbounded inside a loop.

## Evaluation  [PREFER]
For anything beyond a one-off, keep a small input→expected set and run it when
prompts change — otherwise you can't tell improvement from regression.

## Russian/non-ASCII prompts and the linter  [MUST-UNLESS]
If prompt strings contain Cyrillic (or other non-ASCII), ruff's RUF001/002/003
("ambiguous character") will fight them. Add a per-file-ignore for those rules
on the specific prompt files (see ruff template) rather than globally disabling
them — local exception with a clear reason, not a blanket off-switch.
