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
- Redis (Upstash) — OTP storage only

Database:
- PostgreSQL

AI:
- OpenAI 
- Structured Outputs
- RapidFuzz for deterministic product matching.

## Commands

Backend (from `backend/`, venv at `backend/.venv`, Python 3.13):
- Run: `.venv/bin/uvicorn app.main:app --reload --port 8000`
- Migrate: `.venv/bin/alembic upgrade head`; new migration: `.venv/bin/alembic revision --autogenerate -m "..."` (review it; `alembic check` verifies models match)
- Seed demo data (idempotent): `.venv/bin/python -m seed.run_seed` (master data from `seed/demo_data.py`, then order/AI activity from `seed/demo_activity.py` created via the services in one transaction)
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
- Models live in `app/models/<domain>.py` and must be imported in `app/models/__init__.py` (Alembic reads `Base.metadata`). Status/role/type columns are VARCHAR + CHECK constraints built from the StrEnums in `app/core/constants.py`. `users` ↔ `retailers` reference each other, so that FK is added separately in migrations.
- `stock_movements.quantity` and `credit_ledger.amount` are signed (positive = adds stock / increases outstanding).
- Tests: DB tests use a separate `<db>_test` database that `tests/conftest.py` rebuilds with Alembic and seeds each run; use the `db_session` / `client` fixtures. Seed records have deterministic IDs via `seed.run_seed.seed_id(...)`.
- `app/modules/dev/` is temporary, unauthenticated, and mounted only when `ENVIRONMENT=development`.
- Auth: protect routes with `CurrentUser` or `Depends(require_roles(...))` from `app/core/dependencies.py`; the dependency reloads the user from PostgreSQL (active + role must match the token). Pass that user to services, which enforce resource ownership via `app/core/permissions.py`. One token format from `create_access_token` (`app/core/security.py`).
- Auth state lives only in Upstash Redis (`app/modules/auth/auth_store.py`, one atomic Lua script per operation), keyed by the 10-digit phone: `otp:`, `otp_attempts:`, `otp_cooldown:`, `otp_requests:`, `login_attempts:`. Rate limits run for every number before any user lookup, and `send-otp` returns the same generic response for unknown/non-retailer numbers; the OTP is emailed to the retailer's `users.email`, and if there is no email or Brevo rejects it, no usable OTP is left and 503 `OTP_DELIVERY_FAILED` is returned. OTP login is RETAILER-only; password login is SALESMAN/ORDER_DESK/ADMIN-only. Redis down → 503 (fail closed). The `otp_verifications` table is unused; `users.email` (unique, lower case) is where retailer OTPs are sent.
- OTP email goes through `send_otp_email` (async) → `auth/mailer.py`: `brevo` (Brevo transactional email `POST /v3/smtp/email` via `httpx.AsyncClient`) or `mock` (dev-only; config refuses mock outside development). The sync service awaits it with `anyio.from_thread.run`, so it must be called from a request (worker thread). Auth logs each step (generated, stored, emailed, verified) and never the OTP, API key or JWT; emails are masked. Tests replace Upstash with fakeredis (`FakeUpstash` in `tests/test_auth.py`), capture email by monkeypatching `auth.service.send_otp_email` with an async function, and fake Brevo with `httpx.MockTransport` (`tests/test_email.py`). An autouse fixture in `tests/conftest.py` forces `EMAIL_PROVIDER=mock` and makes any un-faked Brevo call fail, so tests never depend on `backend/.env` or send real email; build `Settings(_env_file=None, ...)` in tests.
- Order workflow lives in services that take the acting `User` and enforce access via `app/core/permissions.py` (RETAILER: own shop; SALESMAN: assigned shops; ORDER_DESK/ADMIN: all). Services commit on success and roll back on failure. Modules: `pricing` (pure `calculate_line`), `orders` (create, `correct_order_item`, `approve_order`, `reject_order`), `ai_orders` (`record_extraction`, `confirm_extraction`), `inventory`, `retailers` (credit). No HTTP endpoints for the order workflow yet. The only catalogue endpoints are `GET /products` and `GET /products/categories` (`app/modules/products/`, RETAILER only: the retailer's current prices, stock and active schemes).
- `approve_order` follows DATABASE_DESIGN.MD §7 in one transaction: locks order, inventory rows (sorted by product_id) and credit account with `SELECT … FOR UPDATE` + `populate_existing`. Over-limit orders sit in CREDIT_HOLD; Order Desk may approve only with `credit_override_reason`, which is stored in the ledger entry. Credit is debited (ORDER_DEBIT, full grand total) at approval.
- Frontend (`frontend/src`): no router library; `router.ts` (`navigate`, `usePathname`) + `components/Link.tsx` (`Link`, `Redirect`), routes and guards in `App.tsx` (`/` landing, `/login`, `/home` by role; signed-in users never see `/` or `/login`). API calls go through `api/client.ts` (`apiRequest`, throws `ApiError` with the backend `error_code`/`details`); show backend error messages rather than re-wording them. `auth/AuthContext.tsx` holds the session: JWT in `sessionStorage` (`auth/session.ts`), checked with `GET /auth/me` on load, cleared on 401/expiry. Palette (cream/leaf/mango) and animations are Tailwind v4 `@theme` tokens in `index.css`; product visuals are SVGs in `components/ProductArt.tsx` (no product photos in seed data).
- Order quantities are in the product's `order_unit`; any other unit is refused, never converted. Corrections re-price at `order.created_at`. `orders.subtotal` = Σ(taxable_amount + discount_amount).
- Workflow tests use the `tx` fixture (savepoint session rolled back after each test); `tests/test_concurrency.py` commits for real across threads and restores the data it changed.

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