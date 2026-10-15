# Testing conventions

Apply to Python projects using pytest. Assumes `python-core.md`.
Rule levels are defined in `_LEVELS.md`.

## Structure  [MUST]
- Three layers, three directories: `tests/unit/` (no I/O), `tests/integration/`
  (real DB and other real infrastructure), `tests/e2e/` (API or browser
  through the public surface). A reader must be able to tell what a test
  needs by its path.
- Inside each layer, mirror the source tree: `app/services/user.py` →
  `tests/unit/services/test_user.py`.
- Test names: `test_{what}_{condition}_{expected_outcome}`.
- One `conftest.py` per directory level; put shared fixtures at the highest
  level they're needed, not all in the root conftest.

## Assertions  [MUST]
- Assert specific values, not just "no exception raised" or truthiness.
- One logical assertion per test — if it fails, the name should tell you what broke.
- Test behaviour, not implementation: call the public interface, assert the
  observable output. Don't assert that a private method was called unless the
  side effect is invisible otherwise.

## Acceptance criteria are tests  [MUST]
- Every "expected behaviour" bullet in the task brief or spec maps to exactly
  one named test. Keep the mapping visible: a table in README ("State") or
  `docs/acceptance.md` with bullet → test name → status.
- Concurrency bullets ("two users at once", "double click") are integration
  tests that actually run two clients against the real database — not unit
  tests of a lock helper.
- A bullet without a test is reported as "not proven" in README, not omitted.

## Fixtures and factories  [PREFER]
- Use factory functions or `factory_boy` for model creation; don't repeat field
  defaults in every test.
- Scope fixtures to the narrowest lifetime needed: `function` by default,
  `session` only for expensive read-only setup (e.g. shared DB schema).
- Name fixtures for what they represent, not how they're built
  (`user_with_orders`, not `make_user_factory`).

## Mocking  [MUST]
- Mock at system boundaries only — external HTTP APIs, the clock, randomness,
  email/SMS; the code under test's own functions stay real.
- Prefer dependency injection over `unittest.mock.patch` — injecting a fake is
  explicit; patch is invisible and breaks on rename.
- Integration tests hit the real database — a mock that passes while the real
  DB fails is worse than no test.
- Fakes for the clock and the mail provider are first-class fixtures
  (`frozen_clock`, `outbox`), because time and email are where every
  scheduler/notification bug lives.

## Async  [MUST-UNLESS]
- Use `pytest-asyncio` with `asyncio_mode = "auto"` in `pyproject.toml`; don't
  manually run event loops in tests.
- Async test fixtures must be `async def` too.
- Use `anyio` markers only if the codebase needs to be backend-agnostic.

## Test pyramid  [PREFER]
- Many fast unit tests (pure functions, domain logic) — no I/O, milliseconds.
- Fewer integration tests hitting real infrastructure (DB, Redis, external
  services with test credentials).
- Minimal end-to-end tests: critical happy paths only.
- Keep the full suite runnable locally under 2 minutes; if it grows past that,
  split slow tests into a separate `make test-integration` target.

## Coverage  [MUST-UNLESS]
- A threshold is enforced in CI (`--cov-fail-under` in `pyproject.toml`). Start
  at the number the first
  real suite reaches, raise it as coverage grows, never lower it to go green.
  Escape hatch: a documented reason in `pyproject.toml` next to the number.
- Coverage is still a signal, not the goal: 100% with decorative assertions is
  worthless. Focus on domain logic and error paths; that's where bugs are
  expensive.
- Exclude generated code, migrations, and `__init__.py` re-exports from reports.

## Runnable and documented  [MUST]
- README has a "Testing" section: the one command for everything (`make
  check`), what each layer needs (integration needs `make up`), and how to run
  one layer alone. An undocumented test command counts as no tests to an
  outside reader.
- No committed `skip`/`xfail` without a linked reason; a suite that is skipped
  in CI is not a suite.
- The suite is deterministic: no `time.sleep`, no real network, no dependence
  on wall-clock date; failures reproduce on rerun.
