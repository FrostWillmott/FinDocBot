# Python conventions

The mechanical half (line length, import order, quote style) is enforced by
`ruff.toml` — not restated here. This file covers what the linter does NOT
catch but agents get wrong by default.

## Type hints  [MUST]
- Annotate every function signature, including return types.
- Modern syntax: `X | None` not `Optional[X]`; `list[str]` not `List[str]`;
  `dict[str, int]` not `Dict`.
- `from __future__ import annotations` at the top of each module (defers
  evaluation; lets you use modern syntax on older runtimes and avoids import cycles).
- `TypedDict` / Pydantic models for structured dict shapes; `Protocol` for
  structural typing and dependency inversion rather than concrete base classes.
- Type checking is part of done: code must pass `mypy --strict` (or the
  project's configured strictness). Don't silence with `# type: ignore` without
  a reason comment.

## Error handling  [MUST]
- Never `except:` or `except Exception:` bare — catch the specific exception.
- Raise specific, named exceptions; define domain exceptions where a layer has
  its own failure modes. Don't leak implementation details (e.g. raw DB errors)
  across a layer boundary.
- Don't swallow exceptions silently. If you catch and continue, log why.

## Must-avoid defaults  [MUST]
- No mutable default arguments (`def f(x=[])`); use `None` + assign inside.
- No `time.sleep()` in tests — control time or mock it.

## Preferred defaults  [PREFER]
- `pathlib.Path`, not `os.path`.
- `logging`, not `print()`, for anything that isn't CLI user output.
- f-strings, not `%` or `.format()`.
- Prefer composition over inheritance. Use `@dataclass` or Pydantic for DTOs.

## Async  [MUST]
- Don't mix blocking I/O into async code paths. No blocking DB/network/file
  calls inside `async def` without offloading (e.g. `asyncio.to_thread`).
- Don't create event loops manually in library code; accept being awaited.

## Testing  [PREFER]
- pytest. Test names: `test_{what}_{condition}_{expected}`.
- Assert specific values, not just "no exception".
- Mock at system boundaries (external APIs, clock, randomness), not internals.
- Test pyramid: many fast unit tests, fewer integration tests.
- Full conventions in `testing.md`.

## Packaging / environment  [PREFER]
- `uv` for dependency and environment management; commands go through it.
- Pin versions in the lockfile, not from memory.
- Absolute imports, not relative.
