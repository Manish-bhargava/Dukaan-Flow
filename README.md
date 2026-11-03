# DukaanFlow

Mobile-first FMCG distribution and retailer ordering platform with AI-assisted order capture,
built for a distributor in Jabalpur. See `PROJECT.md` and `docs/` for requirements and design.

| Part | Stack |
|---|---|
| Frontend (`frontend/`) | React, TypeScript, Vite, Tailwind CSS |
| Backend (`backend/`) | Python 3.13, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Database | PostgreSQL |

## Prerequisites

- Python 3.13 (3.12+ should work)
- Node.js 20.19+ / 22.12+ and npm
- PostgreSQL 14+ with an empty database for DukaanFlow

## Backend

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # set DATABASE_URL
alembic upgrade head               # create tables
python -m seed.run_seed            # load demo data
uvicorn app.main:app --reload --port 8000
```

Verify the database: `curl http://localhost:8000/api/v1/dev/db-status` (development only).
See `backend/README.md` for all database commands and dev endpoints.

Check: `curl http://localhost:8000/api/v1/health`

```json
{"success": true, "message": "DukaanFlow API is running", "data": {"status": "healthy"}}
```

Tests: `pytest` (from `backend/` with the venv active).

## Frontend

```bash
cd frontend
npm install
cp .env.example .env               # VITE_API_BASE_URL=http://localhost:8000/api/v1
npm run dev                        # http://localhost:5173
```

The home screen calls the health endpoint and shows "Backend connected" or "Backend unreachable".

Other scripts: `npm run lint` (oxlint), `npm run build` (type-check + production build).

## Environment variables

| File | Variable | Purpose |
|---|---|---|
| `backend/.env` | `APP_NAME`, `ENVIRONMENT`, `DEBUG` | App metadata / debug mode |
| `backend/.env` | `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `backend/.env` | `DATABASE_URL` | PostgreSQL URL (`postgresql+psycopg://…`); percent-encode password special characters |
| `backend/.env` | `TEST_DATABASE_URL` | Optional; database wiped and rebuilt by `pytest` (default `<db>_test`) |
| `frontend/.env` | `VITE_API_BASE_URL` | Backend base URL including `/api/v1` |

Never commit `.env` files; only the `.env.example` templates are tracked.
