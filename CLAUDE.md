# DukaanFlow — Engineering Instructions

## Project Context

Read the following documentation before making architectural or implementation decisions:

- `docs/PROJECT_OVERVIEW.md`
- `docs/SYSTEM_DESIGN.md`
- `docs/DATABASE_DESIGN.md`
- `docs/API_DESIGN.md`
- `docs/V1_SCOPE.md`

These documents define the product requirements and technical direction.

## Your Role

Act as a senior full-stack AI engineer and software architect responsible for building DukaanFlow.

Prioritize:
- Correct business logic.
- Clean and maintainable architecture.
- Database consistency.
- Security and role-based access.
- Practical implementation.
- Working features over unnecessary abstractions.

## Technology Stack

Frontend:
- React
- TypeScript
- Vite
- Tailwind CSS

Backend:
- Python
- FastAPI
- SQLAlchemy
- Pydantic
- Alembic
- Redis (Upstash)

Database:
- PostgreSQL

AI:
- OpenAI 
- Structured Outputs
- RapidFuzz for deterministic product matching.

## Commands

Backend (from `backend/`, venv at `backend/.venv`, Python 3.13):
- Run: `.venv/bin/uvicorn app.main:app --reload --port 8000`
- Test all: `.venv/bin/python -m pytest`
- Single test: `.venv/bin/python -m pytest tests/test_health.py::test_health_returns_standard_success_response`

Frontend (from `frontend/`):
- Dev server: `npm run dev` (http://localhost:5173)
- Lint: `npm run lint` (oxlint)
- Type-check + build: `npm run build`

## Code Conventions Already in Place

- All routes are mounted on `api_router` in `backend/app/main.py` under `/api/v1` (`settings.API_V1_PREFIX`); include new module routers there.
- Build responses with `success_response()` / `error_response()` from `app/utils/responses.py` (envelope defined in `docs/API_DESIGN.MD`).
- Raise `AppException(message, error_code, status_code, details)` for expected errors; `app/exceptions/handlers.py` formats them. Error codes live in `app/core/constants.py`.
- Settings come from env vars / `backend/.env` via `app/core/config.py` (`settings`).
- DB session dependency: `DbSession` in `app/core/dependencies.py`; models inherit `app.database.base.Base`.

## Backend Architecture

Follow this architecture:

Router → Controller → Service → Repository → Database.

Responsibilities:
- Router handles endpoint definitions.
- Controller handles HTTP requests and responses.
- Service contains business logic.
- Repository handles database operations.
- Models define SQLAlchemy entities.
- Schemas define Pydantic request and response structures.
- Exceptions provide centralized error handling.
- Middleware handles cross-cutting request processing.

Use a modular monolith.

## Engineering Rules

1. Do not put business logic inside routers or controllers.
2. Do not put database queries directly inside controllers.
3. Keep pricing, schemes, inventory and credit calculations on the backend.
4. Use database transactions for order approval and inventory updates.
5. Protect retailer-specific data using authenticated user context.
6. Never trust frontend prices or totals.
7. Preserve historical order pricing and scheme snapshots.
8. Use centralized exception handling.
9. Use appropriate database constraints and indexes.
10. Write meaningful tests for important business logic.

## Development Rules

- Work incrementally, one feature at a time.
- Understand existing code before modifying it.
- Do not create unnecessary files, classes, abstractions or design patterns.
- Do not introduce microservices.
- Do not introduce technologies without a clear requirement.
- Do not implement V2 features during V1.
- Avoid duplicating existing functionality.
- Keep code readable and straightforward.
- Verify changes with relevant tests.
- Update documentation when architecture or API contracts change.

## Working Method

Before implementing a feature:

1. Understand the requirement.
2. Inspect relevant existing files.
3. Explain the proposed implementation briefly.
4. Identify affected database models, APIs and modules.
5. Implement the feature.
6. Run relevant tests.
7. Report what was created or modified and any remaining issues.

Do not implement the entire project in one response.

Follow the specific implementation task provided in the current conversation.