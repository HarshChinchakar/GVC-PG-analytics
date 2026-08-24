# Deployment

Two services. The browser only ever talks to Vercel; Vercel talks to Render.

```
Browser ──► Vercel (Next.js)  ──► Render (FastAPI) ──► Supabase Postgres
         first-party cookie      Bearer token         pooled, port 6543
```

## Before anything else — rotate the database password

The Supabase password was shared in plain text, so treat it as compromised.
**Supabase → Settings → Database → Reset database password.** Then update it in
`backend/.env` (local) and in the Render dashboard (production).

When you paste the new password into a connection string, percent-encode any
special characters: `*` → `%2A`, `@` → `%40`, `#` → `%23`, `$` → `%24`.

---

## 1. Supabase

Connection details already confirmed working against this schema:

| | |
|---|---|
| Host | `aws-0-<region>.pooler.supabase.com` |
| Port | **6543** (transaction pooler — not 5432) |
| Database | `postgres` |
| User | `postgres.<project-ref>` |
| Server | PostgreSQL 17.6 (verified) |

Find these under **Supabase → Project Settings → Database → Connection string →
Shared pooler**. The project ref and password are deliberately not committed.

SQLAlchemy URL form:

```
postgresql+psycopg://postgres.<project-ref>:<ENCODED-PW>@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres
```

Port 6543 is PgBouncer in transaction mode, so the backend disables psycopg's
automatic prepared statements (`app/db/session.py`). Without that you get
intermittent *"prepared statement does not exist"* errors under load.

Create the schema and the first owner account:

```bash
cd backend
SUPABASE_DB_URL='postgresql+psycopg://...' .venv/bin/python -m scripts.migrate_to_supabase
```

It prompts for the owner's email, name and password (minimum 12 characters). It
creates tables only — no development data is copied.

> **Still outstanding:** Row Level Security policies on `location_id`. Until
> those exist, isolation rests on the application layer alone, and anything
> holding the Supabase service-role key bypasses it. Keep that key server-side.

## 2. Render (backend)

`backend/render.yaml` is ready. Set these in the dashboard:

| Variable | Value |
|---|---|
| `DATABASE_URL` | the Supabase URL above |
| `JWT_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `CORS_ORIGINS` | `https://<your-app>.vercel.app` (no trailing slash) |
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |

Setting `DEBUG=false` also turns off `/docs` and `/openapi.json`.

**Footprint:** all dependencies installed measure **101 MB** — about 20 % of the
500 MB cap. `--workers 1` is deliberate: the login lockout counter lives in
process memory, so a second worker would keep its own counter and halve the
effective limit.

The free instance sleeps when idle; the first request after a sleep takes a few
seconds. `/health` exists if you want to keep it warm.

## 3. Vercel (frontend)

Root directory: `frontend`. One environment variable:

| Variable | Value |
|---|---|
| `API_BASE_URL` | `https://<your-api>.onrender.com` |

Deliberately **not** `NEXT_PUBLIC_`. The backend address never reaches the
browser, and the API cannot be called from client-side code.

Deploy Render first so you have the URL, then set `CORS_ORIGINS` on Render to
the Vercel domain once that exists.

---

## Running locally

```bash
# terminal 1 — API on :8000
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.init_db --reset     # schema + 925 seed rows
.venv/bin/python -m uvicorn app.main:app --port 8000

# terminal 2 — web on :3000
cd frontend
npm install
echo 'API_BASE_URL=http://127.0.0.1:8000' > .env.local
npm run dev
```

Seeded development logins — **these exist only in the local SQLite file.**
`deploy_supabase.py --demo` replaces every one of them with a generated
password before the data reaches Supabase, so they are safe to publish here:

| Account | Email | Password |
|---|---|---|
| Owner | `owner@gvcexecutive.in` | `owner@123` |
| Manager (Kothrud) | `manager.ktd@gvcexecutive.in` | `ktd@123` |
| Manager (Baner) | `manager.bnr@gvcexecutive.in` | `bnr@123` |
| Manager (Hinjewadi) | `manager.hjw@gvcexecutive.in` | `hjw@123` |



## Checks

```bash
cd backend
.venv/bin/python -m scripts.verify       # 25 schema + access-control checks
.venv/bin/python -m scripts.crosscheck   # 188 figure-by-figure cross-checks
```

`crosscheck` recomputes every dashboard number a second way — pulling raw rows
and totalling them in Python — and asserts it matches the SQL aggregate.

## Frontend note

Pin `typescript@5.x`. TypeScript 7 is installed by default by `npm i -D
typescript`, and Next 15 silently fails to read `tsconfig.json` path aliases
with it — the build fails with `Can't resolve '@/lib/...'`.
