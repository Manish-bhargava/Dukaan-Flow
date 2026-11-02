# DukaanFlow — Backend

FastAPI backend for DukaanFlow (modular monolith, Python 3.13).

## Setup

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit values as needed
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

- Health check: http://localhost:8000/api/v1/health
- OpenAPI docs: http://localhost:8000/docs

## Test

```bash
pytest                                   # all tests
pytest tests/test_health.py              # one file
pytest tests/test_health.py::test_health_returns_standard_success_response   # one test
```

## Layout

```text
app/
├── main.py         # FastAPI app, CORS, exception handlers, /api/v1 router
├── core/           # settings (config.py), constants, shared dependencies, security
├── database/       # SQLAlchemy engine (connection.py), Base (base.py), sessions (session.py)
├── models/         # SQLAlchemy models (Milestone 2+)
├── schemas/        # shared Pydantic schemas
├── modules/        # business modules: router → controller → service → repository
├── middleware/     # cross-cutting request processing
├── exceptions/     # AppException + centralized handlers
└── utils/          # response envelope helpers
migrations/         # Alembic (Milestone 2)
seed/               # demo seed data (Milestone 2)
tests/
```

All responses use the standard envelope from `docs/API_DESIGN.MD`:
success → `{success, message, data}`, error → `{success, message, error_code, details}`.
Raise `app.exceptions.base.AppException` for expected errors; the handlers in
`app/exceptions/handlers.py` format it (and HTTP/validation/unhandled errors) consistently.
