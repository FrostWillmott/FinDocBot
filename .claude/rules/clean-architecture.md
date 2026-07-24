# Clean Architecture (full layered)

Apply ONLY to projects that deliberately want the full layered split. Many
projects are fine with the lighter 3-layer split in `backend-fastapi.md` — do
not impose this one by default. If a project's `CLAUDE.md` says it diverges,
follow the `CLAUDE.md`.

## Layers (dependencies point inward only)
- **Domain** — business entities, value objects, domain rules. No framework or
  infrastructure imports (no FastAPI, SQLAlchemy, Django). Standard library only
  (`datetime`, `decimal`, `uuid`). Entities are synchronous.
- **Use cases** — application business rules; orchestrate domain entities.
  Accept/return domain objects or DTOs. Depend on interfaces (`Protocol`/ABC),
  never on concrete infrastructure. May be async if needed.
- **Interface adapters** — controllers, presenters, gateways. Convert between
  use-case data and external formats. Repository interfaces are implemented here.
- **Infrastructure** — DB implementations, external API clients, framework code.
  All external dependencies live here. Keep async/await at this layer and adapters.

## Rules to enforce
- Flag any framework/infrastructure import appearing in domain or use-case layers.
- Use constructor injection for dependencies; DI containers optional, only for
  complex apps.
- Propose `Protocol`/ABC at boundaries for dependency inversion; DTOs to cross
  layer boundaries.

## Errors
- Domain exceptions in the domain layer; use-case exceptions for business-rule
  violations; adapter exceptions for infrastructure failures. Don't leak
  implementation details across boundaries.

## Testing
- Domain: pure unit tests, nothing to mock.
- Use cases: unit tests with mocked repositories/services.
- Infrastructure/adapters: integration tests against real implementations.

## Pragmatism
Balance purity against effort — perfect is the enemy of good. If a layer adds
ceremony without protecting anything, note it rather than adding it silently.
