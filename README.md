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
pip install -r requirements-dev.txt   # runtime + test tools (production images use requirements.txt)
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

## Production (Docker)

Runs the production build in three containers: `db` (PostgreSQL), `api` (FastAPI; applies the migrations on
start) and `web` (nginx with the React app; passes `/api/` to the API). Only Docker is needed.

```bash
cp backend/.env.production.example backend/.env.production   # fill in the keys (see below)
docker compose up -d --build                                  # build and start
docker compose ps                                             # api and web "healthy"
docker compose run --rm api python -m app.cli create-admin --name "Owner Name" --phone 9876543210
```

Open <http://localhost:8080>, sign in on the **Staff** tab as that admin, then add staff, products and
retailers in the Admin portal.

**Demo data instead (for a demo server, not for real business data):** load the fictional demo shops,
products, staff and 30 days of orders. Every staff account gets the password you pass:

```bash
docker compose run --rm api python -m seed.run_seed --staff-password 'choose-a-password'
docker compose run --rm api python -m seed.bulk_demo --staff-password 'choose-a-password'
```

Demo logins (phone): admin `9000000001`, order desk `9000000002` (also `9000000008`, `9000000009`),
salesmen `9000000003`–`9000000006`, all on the **Staff** tab with that password. Retailer `9000000103`
(Jain Provision Store) signs in with an OTP emailed to `testemail4dukaanflow@gmail.com` (needs Brevo).

Other commands: `docker compose logs -f api` (logs), `docker compose down` (stop; data stays in the
`pgdata` volume), `docker compose down -v` (stop and delete the data).

`backend/.env.production` needs a random `JWT_SECRET_KEY` (32+ characters), Upstash Redis
(`UPSTASH_REDIS_REST_URL` / `_TOKEN`, used by every login), Brevo (`BREVO_API_KEY`, verified
`BREVO_SENDER_EMAIL`, for retailer OTP email), optionally `OPENAI_API_KEY` (AI orders) and the Cloudinary keys.
The API refuses to start with development secrets, `EMAIL_PROVIDER=mock` or `DEBUG=true`, and shows the
reason in `docker compose logs api`. Health: `GET /api/v1/health` and `/api/v1/health/ready` (database);
`/docs` is served in development only. On a public server, put HTTPS (a reverse proxy) in front of
port 8080 and set `CORS_ORIGINS` to that address.
