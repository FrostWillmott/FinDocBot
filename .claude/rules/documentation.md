# Documentation upkeep

Two files are the project's memory across sessions. Unless the project's own
CLAUDE.md (or the user, for the current task) explicitly says otherwise, the
agent keeps both current — this is ongoing maintenance, not a one-time setup
step.

## `README.md`  [MUST-UNLESS]
- Create it if missing; every repo needs one.
- Keep it accurate after any change that affects what a new reader needs to
  know: what the project is, the stack, setup/install steps, how to run it,
  how to run checks/tests.
- Update it in the same change that makes it stale — not as separate cleanup
  work later. A README describing a removed feature or an old command is
  worse than no README.
- Keep it for humans: no walls of prose. Prefer short sections, code blocks
  for commands, tables for reference data.

## `DECISIONS.md`  [MUST-UNLESS]
- Create it if missing; every repo needs one.
- Append-only log of non-obvious choices an agent (or a future contributor)
  would otherwise re-litigate: why this library over that one, why this data
  model, why this trade-off. Not a changelog of every commit.
- Add an entry whenever a decision like that gets made — same change, not
  later. Each entry: date, the decision, the one-line reason. Don't rewrite
  history; if a decision is later reversed, add a new entry that supersedes
  the old one rather than editing it away.
- If the project's CLAUDE.md already has an inline "Key design decisions"
  section, treat `DECISIONS.md` as the durable log and the CLAUDE.md section
  as at most a short pointer to it — don't maintain the same information in
  both places.

## Escape hatch
- "Unless stated otherwise" means: a line in the project's CLAUDE.md opting
  out (e.g. "no DECISIONS.md — decisions live in ADRs under `docs/adr/`"), or
  an explicit instruction for the current task. Absence of instructions is
  not an opt-out — it's the default this module exists to cover.
- A genuine substitute (e.g. an existing ADR directory, a wiki the project
  already uses) satisfies the intent; duplicate tracking in two places does not.
