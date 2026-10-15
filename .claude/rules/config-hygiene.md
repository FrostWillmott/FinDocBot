# Configuration hygiene

Apply to any service that reads configuration from the environment. Assumes
`python-core.md`. Rule levels are defined in `_LEVELS.md`.

Why this module exists: agents declare settings "for later" (a `MAX_QUESTION_LENGTH`
nobody reads, an `API_PORT` the Dockerfile overrides) and hand-maintain
`.env.example`. Both drift silently, and every config audit scores exactly that:
"declared option has no effect", "template out of sync", "two defaults for one
value". The rules below are cheap to follow and expensive to retrofit.

## One settings object is the only source of truth  [MUST]
- All environment reads go through one typed settings object (e.g. Pydantic
  `BaseSettings`) constructed once at startup. No `os.environ[...]` / `os.getenv`
  anywhere else — grep for it in review.
- A value is defined in exactly one place. Dockerfile, compose, CI and README
  reference the setting by name or read `.env`; they never restate a default.
  Two defaults for one value is a defect even when they currently agree.

## Declared means wired  [MUST]
- Every field on the settings object is read by code that changes behaviour.
  Don't add a field until the consumer exists in the same change.
- Every request/query parameter in an API schema reaches the code path it
  names. A parameter accepted and ignored is a lie to the client — remove it
  or wire it.
- Constants that are genuinely fixed (a demo collection name, a model id) are
  module-level constants with a comment saying they are intentional, not
  settings fields that happen to be unused.

## `.env.example` is generated or tested, never hand-synced  [MUST]
- `.env.example` lists every settings field with its local-dev default and a
  one-line comment on what it changes. No production secrets, no placeholders
  like `changeme` for values that have a safe local default.
- A test asserts the set of keys in `.env.example` equals the set of settings
  fields. When one changes without the other, CI fails — that is the whole point.
- Frontend variables (`VITE_*`, `NEXT_PUBLIC_*`) live in the same file under
  their own heading; the frontend build reads them from there.

## Fail fast and loud  [MUST]
- Required settings without a safe default (secret keys, external URLs in prod)
  are validated at import/startup. Missing → process exits with the variable
  name in the message. Never "warn and continue" and never a late failure on
  the first request.
- Optional inputs that silently fall back (an unset templates path, a missing
  feature dir) log at WARNING with the resolved value, so "why isn't it
  loading" is answerable from logs.
- Validate shape, not just presence: ports are ints in range, URLs parse,
  enums are `Literal[...]`.

## Environment parity  [MUST-UNLESS]
- The same settings object serves local, test, CI and containers; differences
  are values in `.env`/CI env, not code paths. If a container must override a
  value (DB host inside compose), it overrides the *variable*, not the command.
- Escape hatch: a value that only exists in one environment (e.g. a compose
  healthcheck) is documented in that file with the reason.

## Never print a secret's value into a log or transcript  [MUST]
Agent transcripts get shared, pasted and stored outside the repository, so
anything an agent prints is a candidate for publication. `cat .env`, `env`,
`docker compose config` and `printenv` put live secrets into that record, where
neither `.gitignore` nor gitleaks protects them — those guard the file, not the
transcript.
- To check a secret is set, print its **name and length**, or compare a hash —
  never the value. `grep -oE '^[A-Z_]+' .env` answers "which keys exist".
- To check a value reached the app, assert on behaviour (the service starts, the
  signature verifies), not on the string.
- When masking a match in output, mask **every** occurrence in the line, not just
  the one you matched: trailing context is how the next secret leaks.
- A secret that did reach a transcript is dead the moment it is rotated, so
  rotate it; redact it as well before that transcript is shared.

## Document the knob, not the mechanism  [PREFER]
- README has a short "Configuration" table: variable, default, when you would
  change it. Generated from `.env.example` comments is fine.
- Distinguish deploy-varying values (env) from tuning constants (code) in that
  table; don't expose a knob nobody has a reason to turn.
