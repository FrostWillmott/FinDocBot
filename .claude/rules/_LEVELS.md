# Rule levels (applies to every module in this directory)

Each rule is tagged with one of three levels. The tag tells the agent how much
latitude it has — it does not need to guess from tone.

## [MUST] — hard imperative
Non-negotiable. The agent does not relax these for convenience, speed, or
"it's simpler this way". Covers:
- All security rules (untrusted input handling, secret isolation, injection defence).
- Existence of control infrastructure: linter + formatter + type checking wired
  to run at pre-commit; at least critical-path tests present and runnable.
A [MUST] about *infrastructure existence* means the mechanism must be there and
must run — not that every optional rule inside it is sacred.

## [MUST-UNLESS] — imperative with a documented escape hatch
The default is mandatory, but a genuine technical reason permits deviation.
When deviating, the agent does it locally and explains it inline (e.g.
`# type: ignore[arg-type]  # reason`), never by globally disabling the check.
Silently weakening one of these "because it was easier" is a violation; deviating
with a stated technical cause is allowed. Strict typing lives here: strict by
default, local documented exceptions permitted (e.g. third-party libs without stubs).

## [PREFER] — preference / default
The agent follows these by default but may let project context override. Covers
specific implementations: which ruff rule set, how layers are split, which DI
pattern. If the agent diverges, a one-line note is courteous but not required.

When a project's own CLAUDE.md conflicts with a [PREFER] rule, the project wins
silently. When it conflicts with a [MUST], the agent surfaces the conflict
rather than quietly following either.
