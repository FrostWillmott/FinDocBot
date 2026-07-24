# Testing conventions

Apply to Python projects using pytest. Assumes `python-core.md`.
Rule levels are defined in `_LEVELS.md`.

## Structure  [MUST]
- Test names: `test_{what}_{condition}_{expected_outcome}`.
- Mirror the source tree under `tests/`: `app/services/user.py` →
  `tests/services/test_user.py`.
- One `conftest.py` per directory level; put shared fixtures at the highest
  level they're needed, not all in the root conftest.

## Assertions  [MUST]
- Assert specific values, not just "no exception raised" or truthiness.
- One logical assertion per test — if it fails, the name should tell you what broke.
- Test behaviour, not implementation: call the public interface, assert the
  observable output. Don't assert that a private method was called unless the
  side effect is invisible otherwise.

## Fixtures and factories  [PREFER]
- Use factory functions or `factory_boy` for model creation; don't repeat field
  defaults in every test.
- Scope fixtures to the narrowest lifetime needed: `function` by default,
  `session` only for expensive read-only setup (e.g. shared DB schema).
- Name fixtures for what they represent, not how they're built
  (`user_with_orders`, not `make_user_factory`).

## Mocking  [MUST]
- Mock at system boundaries only: external HTTP APIs, the clock, randomness,
  email/SMS. Don't mock internal functions or classes you own.
- Prefer dependency injection over `unittest.mock.patch` — injecting a fake is
  explicit; patch is invisible and breaks on rename.
- Never mock the database in integration tests — a mock that passes while the
  real DB fails is worse than no test.

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

## Coverage  [PREFER]
- Track coverage as a signal, not a target — 100% with bad assertions is worthless.
- Focus on domain logic and error paths; that's where bugs are expensive.
- Exclude generated code, migrations, and `__init__.py` re-exports from reports.
