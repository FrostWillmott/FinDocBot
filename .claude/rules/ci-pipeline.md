# CI pipeline

Apply to any repository with a CI workflow. Rule levels are in `_LEVELS.md`.

Why this module exists: every rule below is written from an incident in a
project built on this library, where `ci.yml` failed **33 consecutive times
without anyone noticing**. Two of the three root causes were invisible to every
local command, and the third hid behind a tool that happened to be on one
machine's PATH. CI that is never observed is not a gate — it is decoration that
costs minutes per push. The last rule is the one that makes the other five enforceable.

## 1. CI calls the project's commands, it does not restate them  [MUST]
- A job step runs `make check`, `make audit`, `make docker-build` — not a
  hand-copied `cd frontend && npm run lint && npm run format:check && ...`.
  A restated command drifts: the Makefile gains a step, CI keeps running the old
  list, and CI goes green on a check that no longer exists.
- If a command is worth running in CI it is worth running locally, so it belongs
  in the Makefile (or equivalent) first. "What does CI actually run" must be
  answerable by reading one file.
- The exception is *environment setup* — `uv sync --locked`, `npm ci`,
  `actions/setup-*`. Those provision the environment the project command then
  runs in; they are not reworded project commands.

## 2. A job's environment satisfies everything its command runs  [MUST]
- Before adding a step, expand the target. A job that calls a composite target
  installs the dependencies of **every** part of it, or calls a narrower target
  that matches what it installed.
- Concretely: when `make check` means `lint format typecheck test frontend-check`,
  a backend job that sets up only Python and calls `make check` fails on the
  frontend half — it must either add Node and `npm ci`, or call
  `make lint format typecheck test`.
- Every tool a target invokes through a runner (`uv run ruff`, `npx tsc`) is a
  **declared dependency**, pinned in the lockfile — never merely present on a
  developer's PATH. `uv run` silently falls back to PATH, so an undeclared tool
  works on the machine that has it and dies in CI with `Failed to spawn`.
- Pin a linter to the same version the pre-commit hook uses. A floating linter
  turns an unrelated push red on the day a new rule ships.

## 3. Job-level conditions use no working-directory functions  [MUST]
- `hashFiles()` reads the checked-out workspace, which does not exist when
  job-level expressions are evaluated. At `jobs.<id>.if` it is not a runtime
  error but a **workflow-file** error: GitHub rejects the whole file, the run
  ends in 0s with no jobs and no logs, and `gh run list` shows a plain
  `failure` indistinguishable from a failed test. That is the 33-run incident.
- Available at job level: `github`, `needs`, `vars`, `inputs`. Anything about
  file contents belongs in a step-level `if`, or in a `needs` dependency on a
  job that computed it.
- Do not guard a job on a file the repository actually contains. A conditional
  that is always true is dead weight that hides a real typo.
- YAML parsing does not catch this class of error. Lint the workflow:
  `actionlint .github/workflows/*.yml` (`brew install actionlint`).

## 4. Every tool version comes from a single source  [MUST]
- Node: `node-version-file: .nvmrc` in every job. Never `node-version: <n>`
  alongside an `.nvmrc` — that is two defaults for one value, a defect even
  while they agree.
- uv: `[tool.uv] required-version` in `pyproject.toml` is the source; CI reads
  it with `version-file: pyproject.toml` and uv itself enforces it locally.
- Actions are pinned by commit SHA, never a moving tag — a tag can be
  re-pointed, a SHA cannot. Keep the human-readable version in a trailing
  comment, and bump SHA and comment together.
- A version a build step cannot read from that source (a Docker `FROM` tag, for
  instance) restates it only with a comment naming the real source, so the next
  reader knows which one leads. Two copies with no cross-reference is the defect.

## 5. Bounded and non-redundant  [MUST]
- A top-level `concurrency` group keyed on the ref, with
  `cancel-in-progress: true`, so a second push does not leave a stale run racing
  the new one to report a status.
- `timeout-minutes` on every job. The default is 6 hours: one hung step burns a
  day of minutes and the run never reports.

## 6. A green run, confirmed by command — this outranks rules 1-5  [MUST]
The five rules above are structure; this one is evidence, and where they
conflict this wins. A structurally perfect workflow that nobody observed is
what produced the incident.

**The task is not done until a pushed commit has produced a green run, and the
green is confirmed by running a command — never by assuming.**

```bash
gh run watch "$(gh run list -L1 --json databaseId --jq '.[0].databaseId')" --exit-status
gh run view --log-failed          # on a failure
gh run view --json jobs --jq '.jobs[].name'   # which jobs actually ran
```

- `make check` passing locally is not evidence about CI. It does not execute the
  workflow file, the runner image, or the job's environment.
- **A job missing from the run counts as failed, not passed.** Check the job
  *names* against the workflow, not the run's overall colour: a skipped job, a
  job dropped by a bad `if`, and a job whose name you misremembered all present
  as "nothing red".
- A run with zero jobs is the worst case, because it reports as an ordinary
  failure. `gh run view` saying *"likely failed because of a workflow file
  issue"* means rule 3 — there are no logs to read.
- Green on the *pushed* commit. A local amend, a rebase, or a dirty tree means
  the green belongs to different content than what is on the branch.
