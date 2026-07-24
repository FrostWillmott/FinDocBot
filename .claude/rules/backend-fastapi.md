# Backend conventions (FastAPI + async SQLAlchemy)

Apply when the project is a FastAPI service. Assumes `python-core.md` is also present.

## Layering (lightweight, not full Clean Architecture)
- `routers/` — HTTP only: parse request, call a service, shape the response.
  No business logic here.
- `services/` — business logic, validation, orchestration. No knowledge of HTTP.
  Services raise domain exceptions; routers catch them and map to HTTP responses.
- DB access layer (session factory via a `get_db()` dependency).
- If the project wants the full domain/use-case/adapter split, that's the
  `clean-architecture.md` module instead — don't impose it here.

## Pydantic
- Separate request, response, and internal DTOs — don't reuse one model for all.
- Validate and normalize at the boundary: strip whitespace, coerce, constrain
  with field validators (`mode="before"` for normalization).
- Use `model_fields_set` to distinguish "field omitted" from "explicitly null"
  in PATCH semantics.

## Async SQLAlchemy
- All DB access via `AsyncSession`.
- Never rely on lazy loading. Load relationships explicitly with `selectinload`
  in the query — lazy loads fail or surprise under async.
- Transaction management lives in the service or adapter layer, not in domain logic.

## API design
- Validate input with Pydantic before touching business logic.
- Return typed response models; let FastAPI generate the OpenAPI schema.
- Use dependency injection (`Depends`) for sessions, auth, config.

## Migrations
- Alembic. Autogenerate, then review the migration by hand before applying.

## Don't duplicate services  [PREFER]
If two service classes are near-identical in structure (shared lifecycle,
initialization, error-handling patterns), extract a shared base before writing
a third. Two is the warning sign; different config or trigger types justify
subclasses, not separate copies.

## Isolate fragile external integrations  [PREFER]
Code that depends on undocumented or unofficial behavior of an external platform
has a built-in expiry date — a platform change can break it overnight. Keep it
isolated, mark it as deliberately fragile, and don't generalize it into a shared
abstraction that other code depends on.
