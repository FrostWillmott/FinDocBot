# Documentation upkeep

Two files are the project's memory across sessions. Unless the project's own
AGENTS.md (or the user, for the current task) explicitly says otherwise, the
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
- Required sections (a reviewer or auditor looks for each by name):
  1. **What it is** — one paragraph, the product and the stack.
  2. **Prerequisites** — every global tool with a version (Docker, uv, Node).
  3. **Run locally** — the exact commands from clone to a working app.
  4. **Configuration** — table of env variables (see `config-hygiene.md`).
  5. **Testing** — the one command, what each layer needs (see `testing.md`).
  6. **State** — honest table: what works, what doesn't, what was skipped and
     why. For a spec with "expected behaviour" bullets, one row per bullet
     with the proving test's name and its status.
  7. **Decisions worth knowing** — three to five lines, pointer to `DECISIONS.md`.
  8. **Next steps** — what a following iteration would do and why it was cut.

## `DECISIONS.md`  [MUST-UNLESS]
- Create it if missing; every repo needs one.
- Append-only log of non-obvious choices an agent (or a future contributor)
  would otherwise re-litigate: why this library over that one, why this data
  model, why this trade-off. Not a changelog of every commit.
- Add an entry whenever a decision like that gets made — same change, not
  later. Each entry: date, the decision, the one-line reason. Don't rewrite
  history; if a decision is later reversed, add a new entry that supersedes
  the old one rather than editing it away.
- If the project's AGENTS.md already has an inline "Key design decisions"
  section, treat `DECISIONS.md` as the durable log and the AGENTS.md section
  as at most a short pointer to it — don't maintain the same information in
  both places.

## Proof of work  [PREFER]
- When the project has acceptance criteria (a spec, a task with "expected
  behaviour" bullets), the README "State" table is the proof: one row per
  criterion with the proving test's name and its status, and "not proven" for
  a criterion without a test — never a dropped row.
- A runtime check of a change (the `verify` skill) is recorded as a dated
  report, `docs/verification-<date>.md`, with the PASS / FAIL / BLOCKED / SKIP
  verdict per flow and the captured output; the next run starts from it.
- When the work is handed over (to a reviewer, a client, the next iteration),
  write `docs/handover.md`: what is done, what is not, where each deliverable
  lives, and how to reproduce the checks. A reader should not need the chat.

## Escape hatch
- "Unless stated otherwise" means: a line in the project's AGENTS.md opting
  out (e.g. "no DECISIONS.md — decisions live in ADRs under `docs/adr/`"), or
  an explicit instruction for the current task. Absence of instructions is
  not an opt-out — it's the default this module exists to cover.
- A genuine substitute (e.g. an existing ADR directory, a wiki the project
  already uses) satisfies the intent; duplicate tracking in two places does not.
