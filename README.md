# GVC Executive — PG Analytics

An internal occupancy and rent-tally portal for a multi-site paying-guest
business. It replaces the spreadsheets and the notebook: enter a resident, a
bed and a payment once, and the application answers who is living where, who
has paid, what is empty, and what the month came to.

> Not an accounting system, not a payment gateway, not a property-management
> suite. It collects no money and has no resident login — deliberately. See
> [`Project.md`](Project.md) for the scope, including what is excluded.

---

## What it does

| Screen | For | What it answers |
|---|---|---|
| **Sign in** | owner, managers | No public sign-up; accounts are issued by the owner |
| **Site picker** | owner | Which building to open, with live occupancy and rent outstanding on each card |
| **Dashboard** | both | Occupancy, rent collected, vacancy loss, who has not paid, who is leaving |
| **Revenue analysis** | owner only | Yield decomposed into empty beds vs under-pricing vs non-payment, cut six ways |
| **Occupancy board** | both | A cinema-style seat map of every bed, filterable |
| **Vehicle lookup** | both | "Whose bike is this?" — partial plate search |
| **Expenses** | both | Record spend per site; recurring costs are one tap |

### Two roles

* **Super Admin (owner)** — every building, every figure, creates staff accounts.
* **Manager** — one building, operational data only. No deposit totals, no
  revenue analysis, and no way to discover that other buildings exist: a
  cross-tenant request answers **404, not 403**.
* **Residents are records, not users.** There is no resident portal.

---

## Architecture

```
Browser ──► Vercel (Next.js 15)  ──►  Render (FastAPI)  ──►  Supabase Postgres
         first-party httpOnly       Bearer token             pooled, port 6543
              cookie
```

The browser never holds the access token and never learns the backend's
address. It talks only to the Vercel origin; Next.js route handlers keep the
JWT in a first-party httpOnly cookie and forward it server-side. That sidesteps
third-party cookie blocking between two origins, and an XSS bug on the frontend
cannot exfiltrate the session.

| | |
|---|---|
| **Backend** | FastAPI · SQLAlchemy 2.0 · Pydantic v2 · PyJWT — 8 runtime dependencies, **105 MB** installed |
| **Frontend** | Next.js 15 App Router · React 19 · Tailwind v4 — 103 kB shared JS |
| **Database** | Supabase PostgreSQL 17 in production, SQLite locally, from one set of models |
| **Auth** | Own `users` table, PBKDF2-HMAC-SHA256 at 600k iterations (OWASP) |

Full detail: [`backend_architecure.md`](backend_architecure.md) — every table,
field, constraint and index, and how each figure is computed.
Every decision, what was rejected and what it costs:
[`backend_Architectural_Decisions.md`](backend_Architectural_Decisions.md).

---

## Deploying

Step-by-step, with the exact environment variables:
**[`DEPLOYMENT.md`](DEPLOYMENT.md)**.

The short version:

**1. Supabase** — create the schema and load data:

```bash
cd backend
SUPABASE_DB_URL='postgresql+psycopg://postgres.<ref>:<url-encoded-pw>@aws-0-<region>.pooler.supabase.com:6543/postgres' \
  python -m scripts.deploy_supabase --demo     # omit --demo for a clean start
```

It prints freshly generated credentials once. The seed's development passwords
are published in this repository, so `--demo` replaces every one of them before
the database is reachable from the web.

**2. Render** — `backend/render.yaml` is ready. Set in the dashboard:

| Variable | Value |
|---|---|
| `DATABASE_URL` | the Supabase pooler URL |
| `JWT_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `CORS_ORIGINS` | `https://<your-app>.vercel.app` |
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |

The app **refuses to boot** if `DATABASE_URL` is missing, `JWT_SECRET` is the
published default, or `DEBUG` is on. Without that check the worst failure is
silent: Render would fall back to SQLite on an ephemeral disk, look healthy,
and lose every record on the next deploy.

**3. Vercel** — root directory `frontend`, one variable:

| Variable | Value |
|---|---|
| `API_BASE_URL` | `https://<your-api>.onrender.com` |

Deliberately **not** `NEXT_PUBLIC_` — the backend address never reaches the
browser.

Deploy Render first to get its URL, then Vercel, then set `CORS_ORIGINS` on
Render to the Vercel domain.

---

## Running locally

```bash
# terminal 1 — API on :8000
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.init_db --reset      # schema + 1,663 seed rows
.venv/bin/python -m uvicorn app.main:app --port 8000

# terminal 2 — web on :3000
cd frontend
npm install
echo 'API_BASE_URL=http://127.0.0.1:8000' > .env.local
npm run dev
```

Local seed logins — SQLite only, never created on Supabase by `init_db`:

| Account | Email | Password |
|---|---|---|
| Owner | `owner@gvcexecutive.in` | `owner@123` |
| Owner (second) | `admin@gvcexecutive.in` | `admin@123` |
| Manager (Kothrud) | `manager.ktd@gvcexecutive.in` | `ktd@123` |

> **Pin `typescript@5.x`.** `npm i -D typescript` now installs TypeScript 7,
> which Next 15 silently fails to read `tsconfig.json` path aliases from —
> the build dies with `Can't resolve '@/lib/...'`.

> **Never run `rm -rf .next && next build` while the dev server is live.** It
> wipes the cache from under the running process, which then serves HTML
> referencing chunks that no longer exist: every page returns 200 while being
> completely unstyled and inert.

---

## Verification

```bash
cd backend
.venv/bin/python -m scripts.verify        # 25 schema + access-control checks
.venv/bin/python -m scripts.crosscheck    # 258 figure-by-figure cross-checks

cd ../frontend
python3 tests/test_ui.py                  # 189 Selenium UI checks (needs both servers)
```

**`crosscheck` recomputes every figure a second way** — pulling raw rows and
totalling them in Python — and asserts it matches the SQL aggregate. An
aggregate and a hand count that disagree mean one of them is wrong; agreeing
across every building and every month is what makes the numbers trustworthy.
It also refuses states that would quietly corrupt a tally: rent billed after a
resident left, a PAID record with no payment row, a bed status that disagrees
with the live stay, anything crossing a location boundary.

**The UI tests assert on computed styles and real interaction, not markup.**
They exist because a page can return HTTP 200 and still be completely broken —
that exact bug is what prompted them.

---

## Security

* **Three independent layers of tenant isolation** — `location_id` on every
  operational row, a service-layer predicate on every query, and Supabase RLS.
  ⚠️ **The RLS policies are not yet written** — the one item outstanding before
  real resident data goes in. Keep the service-role key server-side.
* **Owners cannot create owners.** The role is hard-coded in the handler, not a
  request field, so a stolen session cannot mint a permanent backdoor account.
* **No user enumeration** — one error message, and unknown accounts are checked
  against a dummy hash so a miss costs the same 284 ms as a hit.
* **Lockout** after 5 failed attempts per email+IP for 15 minutes.
* **ORM rows never reach the UI.** Every response is a Pydantic DTO; a field
  that is not declared there cannot be serialised, so `password_hash` is absent
  by construction rather than by vigilance.
* **Money rules are database constraints**, not conventions: one payment per
  month, one bill per stay per month, one recurring expense per month, and
  CHECKs that deposit refunds add up and that a void states its reason.
* **Writes are idempotent.** Every expense carries a key; a replay returns the
  original row rather than booking the money twice.
* **CSRF origin checks** on the write proxies, on top of `SameSite=Lax`.

---

## Repository layout

```
backend/
  app/
    core/        config, portable column types, enums, auth, hashing
    db/          declarative base, session, seed
    models/      17 tables
    schemas/     response DTOs
    services/    access control, queries, revenue analysis, occupancy board
    api/         routers and dependencies
  scripts/       init_db · verify · crosscheck · deploy_supabase
frontend/
  app/           routes (App Router)
  components/    seat map, analysis tables, chrome
  lib/           server-side API client, session, formatting
  tests/         Selenium suite
skills/          reference material used while building
```

## Not yet built

The remaining write actions (mark rent paid, assign a bed, serve notice), a
financial dashboard combining revenue with expenses, the Residents and
Move-Outs screens, per-floor occupancy statistics, an Alembic baseline, and the
Supabase RLS policies.
