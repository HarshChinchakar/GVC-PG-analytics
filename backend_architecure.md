# Backend Architecture — PG Logistics & Rent Tally Portal

**Status:** implemented and verified
**Scope:** backend, database, roles/access model, authentication, and the
sign-in + site-picker + dashboard screens.
**Development DB:** SQLite (`backend/pg_portal.db`)
**Production DB:** Supabase PostgreSQL

---

## 1. Overview

The backend is a FastAPI application over a single relational database, designed
so the same schema and the same code run on SQLite today and Supabase Postgres
later. Nothing in the application knows which database it is talking to.

```
 Next.js (Vercel)
        │  HTTPS, JSON, DTOs only
        ▼
 FastAPI (Render)  ── routers → services → repositories
        │              (access control lives in services)
        ▼
 SQLAlchemy 2.0 ORM
        │
        ├── development → SQLite  (file, zero setup)
        └── production  → Supabase PostgreSQL (+ Row Level Security)
```

### Layers

| Layer | Directory | Responsibility |
|---|---|---|
| Config | `app/core/config.py` | Environment settings; the only place a DB URL appears |
| Types | `app/core/types.py` | Portable column types (`GUID`, `TZDateTime`, `Rupees`) |
| Enums | `app/core/enums.py` | Domain vocabulary + `CHECK` constraint generation |
| Security | `app/core/security.py` | Password hashing (PBKDF2, 600k iterations) |
| Base | `app/db/base.py` | Declarative base, naming convention, shared mixins |
| Session | `app/db/session.py` | Engine, per-request session, SQLite pragmas |
| Models | `app/models/` | 15 tables, all constraints and indexes |
| Auth | `app/core/auth.py` | JWT issuing, brute-force lockout |
| API deps | `app/api/deps.py` | Bearer resolution, role gates |
| Routes | `app/api/routes/` | `auth`, `dashboard`, `users` |
| Access | `app/services/access.py` | **The tenant isolation boundary** |
| Queries | `app/services/queries.py` | Dashboard, rent, ledger, occupancy reads |
| DTOs | `app/schemas/dto.py` | Response shapes; ORM rows never leave the service layer |
| Seed | `app/db/seed.py` | Deterministic development dataset |

---

## 2. Roles and access model

Three kinds of actor, but only **two** of them log in.

### 2.1 Super Admin (the owner)

* Access to **all** locations, including ones created after they logged in.
* Full read and write on every entity.
* Exclusive rights (`SUPER_ADMIN_ONLY` in `access.py`): manage locations, manage
  users, cross-location analytics, deposit totals, waive rent, edit a rent
  amount, delete a resident, read the audit log.
* Needs **no rows** in `user_locations` — access is implied by the role.

### 2.2 Manager (per-PG)

* Access only to locations explicitly granted in `user_locations`.
* Day-to-day operations: view residents, view rooms and beds, assign a bed, mark
  rent paid, record a notice, complete a move-out.
* **Cannot** see deposit totals, portfolio analytics, the audit log, or any other
  building — those are withheld by the service, not hidden by the UI.
* A manager with **no** grant sees nothing, not everything (fail-closed).

### 2.3 Residents

Residents are **records, not users**. There is no resident login, no resident
portal, and no credential of any kind on the `residents` table. This matches
Project.md §46 and removes an entire class of authentication surface.

### 2.4 How isolation is enforced — three independent layers

Isolation is not left to a single mechanism, because a single mistake would then
be a data breach.

| Layer | Mechanism | Where | Active on |
|---|---|---|---|
| 1. Schema | Every operational table carries `location_id` | `app/models/` | SQLite + Postgres |
| 2. Service | `scope()` adds the tenant predicate to every SELECT; `require()` guards every write | `app/services/access.py` | SQLite + Postgres |
| 3. Database | Supabase Row Level Security policies on `location_id` | Supabase | Postgres only |

Layer 3 does not exist on SQLite, which is precisely why layer 2 is written as a
**hard failure** (`AccessDenied`) rather than a filter that quietly returns
nothing.

`AccessDenied` maps to **HTTP 404, not 403**. Telling a manager that "location X
exists but is not yours" leaks the owner's portfolio. As far as a manager is
concerned, other buildings do not exist.

---

## 3. Data model

### 3.1 Physical hierarchy

```
Location  (one PG building — the isolation boundary)
  └── Floor
        └── Flat            (2BHK / 3BHK / RK)
              └── Room      (Hall / Bedroom, attached or not)
                    └── Bed (one sleeping position — the rentable unit)
```

### 3.2 Full relationship map

```
USER ─┬─< USER_LOCATIONS >─┬─ LOCATION
      │  (managers only)   │
      │                    ├─< FLOOR ─< FLAT ─< ROOM ─< BED
      │                    │                            │
      │                    └─< RESIDENT                 │
      │                          │                      │
      │                          └─< RESIDENT_STAY >────┘
      │                                 │
      │                                 ├─< RENT_RECORD ──< PAYMENT ─┐
      │                                 ├─── DEPOSIT ──< DEPOSIT_REFUND
      │                                 └─< MOVE_OUT_NOTICE          │
      └──────────────── marked_by / processed_by ────────────────────┘

AUDIT_LOG ─── user_id (nullable), location_id (nullable)
```

Every table below `Location` also stores `location_id` **directly**, even where
it is reachable by joining upward. This is deliberate — see ADR-004.

### 3.3 Table reference

Every table has `id UUID PK`, `created_at`, `updated_at` unless noted.

---

#### `users` — people who log in

| Field | Type | Null | Notes |
|---|---|---|---|
| email | VARCHAR(255) | NOT NULL | UNIQUE |
| full_name | VARCHAR(120) | NOT NULL | |
| phone | VARCHAR(20) | NULL | |
| role | VARCHAR(20) | NOT NULL | CHECK ∈ {super_admin, manager}, indexed |
| password_hash | VARCHAR(255) | NULL | PBKDF2 hash; this is the production credential |
| auth_user_id | UUID | NULL | UNIQUE; reserved for Supabase Auth, unused (ADR-023) |
| is_active | BOOLEAN | NOT NULL | |
| last_login_at | TIMESTAMPTZ | NULL | |

**Constraints:** `role` valid; email not blank.
**Note:** no `location_id` — a user is not owned by a building.

---

#### `user_locations` — which manager runs which PG

| Field | Type | Null | Notes |
|---|---|---|---|
| user_id | UUID | NOT NULL | FK → users, CASCADE, indexed |
| location_id | UUID | NOT NULL | FK → locations, CASCADE, indexed |

**Constraints:** UNIQUE(user_id, location_id).
A join table rather than a column on `users`, so one manager can cover two
buildings during a handover without a schema change.

---

#### `locations` — one PG building

| Field | Type | Null | Notes |
|---|---|---|---|
| name | VARCHAR(120) | NOT NULL | e.g. "Kothrud PG" |
| code | VARCHAR(20) | NOT NULL | UNIQUE, e.g. "KTD" |
| address_line / city / contact_phone | VARCHAR | NULL | |
| notice_period_days | INTEGER | NOT NULL | default 30 |
| deposit_deduction | INTEGER (₹) | NOT NULL | default 1000 |
| is_active | BOOLEAN | NOT NULL | |
| notes | TEXT | NULL | |

**Constraints:** notice period > 0; deduction ≥ 0; name not blank.
House rules live **per building** so the owner can vary them without a deploy.

---

#### `floors`

| Field | Type | Null | Notes |
|---|---|---|---|
| location_id | UUID | NOT NULL | FK → locations, RESTRICT, indexed |
| floor_number | INTEGER | NOT NULL | |
| name | VARCHAR(60) | NOT NULL | |
| sort_order | INTEGER | NOT NULL | |

**Constraints:** UNIQUE(location_id, floor_number).
A real table because Project.md §17 asks to filter the pending list by floor.

---

#### `flats`

| Field | Type | Null | Notes |
|---|---|---|---|
| location_id | UUID | NOT NULL | FK → locations, indexed |
| floor_id | UUID | NOT NULL | FK → floors, RESTRICT, indexed |
| flat_number | VARCHAR(20) | NOT NULL | "101" — what people say out loud |
| flat_type | VARCHAR(10) | NOT NULL | CHECK ∈ {rk, 1bhk, 2bhk, 3bhk, other} |
| is_active | BOOLEAN | NOT NULL | |
| notes | TEXT | NULL | |

**Constraints:** UNIQUE(location_id, flat_number).

---

#### `rooms`

| Field | Type | Null | Notes |
|---|---|---|---|
| location_id | UUID | NOT NULL | FK → locations, indexed |
| flat_id | UUID | NOT NULL | FK → flats, RESTRICT, indexed |
| name | VARCHAR(60) | NOT NULL | "Hall", "Bedroom 2" |
| room_kind | VARCHAR(20) | NOT NULL | CHECK ∈ {hall, bedroom} |
| is_attached | BOOLEAN | NOT NULL | washroom belongs to the room, not the bed |
| capacity | INTEGER | NOT NULL | planned beds; real count is `len(beds)` |
| sort_order, is_active | | NOT NULL | |

**Constraints:** UNIQUE(flat_id, name); capacity ≥ 0.

---

#### `beds` — the rentable unit

| Field | Type | Null | Notes |
|---|---|---|---|
| location_id | UUID | NOT NULL | FK → locations, indexed |
| room_id | UUID | NOT NULL | FK → rooms, RESTRICT, indexed |
| bed_number | INTEGER | NOT NULL | |
| label | VARCHAR(40) | NOT NULL | **"101-1NA"** — what every screen shows |
| default_rent | INTEGER (₹) | NOT NULL | rent this bed fetches when empty |
| status | VARCHAR(20) | NOT NULL | CHECK ∈ {available, occupied, notice, blocked} |
| is_active | BOOLEAN | NOT NULL | |
| notes | TEXT | NULL | e.g. "bathroom repair" |

**Constraints:** UNIQUE(room_id, bed_number); UNIQUE(location_id, label);
default_rent ≥ 0; bed_number > 0.
**Index:** `(location_id, status)` — drives every occupancy count.

`default_rent` exists because vacancy loss must sum **the actual rent of each
empty bed**; a vacant bed has no resident to read a rent from (ADR-006).

---

#### `residents` — a person (never a user)

| Field | Type | Null | Notes |
|---|---|---|---|
| location_id | UUID | NOT NULL | FK → locations, indexed |
| full_name | VARCHAR(120) | NOT NULL | |
| phone | VARCHAR(20) | NOT NULL | indexed |
| alt_phone / email | | NULL | |
| id_proof_type / id_proof_number | | NULL | enough to identify at move-in |
| permanent_address | TEXT | NULL | |
| emergency_contact_name / _phone | | NULL | |
| status | VARCHAR(20) | NOT NULL | CHECK ∈ {active, notice, left}, indexed |
| joined_on | DATE | NOT NULL | first arrival across all stays |
| left_on | DATE | NULL | final departure |
| notes | TEXT | NULL | |

**Constraints:** UNIQUE(location_id, phone) — a number identifies someone within
a building, and may legitimately recur in another; name and phone not blank;
`left_on >= joined_on`.
**Index:** `(location_id, status)` — the residents screen.

---

#### `resident_stays` — one occupation of one bed at one rent ★

The pivot of the whole model.

| Field | Type | Null | Notes |
|---|---|---|---|
| location_id | UUID | NOT NULL | FK → locations, indexed |
| resident_id | UUID | NOT NULL | FK → residents, CASCADE, indexed |
| bed_id | UUID | NOT NULL | FK → beds, RESTRICT, indexed |
| start_date | DATE | NOT NULL | |
| end_date | DATE | NULL | **NULL = currently living here** |
| monthly_rent | INTEGER (₹) | NOT NULL | frozen for this stay |
| rent_due_day | INTEGER | NOT NULL | CHECK 1–28 |
| is_current | BOOLEAN | NOT NULL | cache of `end_date IS NULL` |
| end_reason | VARCHAR(120) | NULL | |

**Constraints:**
* rent ≥ 0; `end_date >= start_date`; due day 1–28 (28 so every month has one).
* `(is_current AND end_date IS NULL) OR (NOT is_current AND end_date IS NOT NULL)`
  — the cache cannot disagree with the date.

**Partial unique indexes — the two rules that make double-booking impossible:**
* `uq_bed_single_current_occupant` on `bed_id WHERE is_current` — one bed, one
  current resident.
* `uq_resident_single_current_stay` on `resident_id WHERE is_current` — one
  resident, one current bed.

Both are enforced by the **database**, verified in `scripts/verify.py`.

---

#### `rent_records` — what one resident owes for one month

| Field | Type | Null | Notes |
|---|---|---|---|
| location_id | UUID | NOT NULL | FK → locations, indexed |
| resident_id | UUID | NOT NULL | FK → residents, CASCADE, indexed |
| stay_id | UUID | NOT NULL | FK → resident_stays, CASCADE, indexed |
| period_year | INTEGER | NOT NULL | CHECK 2000–2200 |
| period_month | INTEGER | NOT NULL | CHECK 1–12 |
| amount_due | INTEGER (₹) | NOT NULL | copied from the stay at generation |
| due_date | DATE | NOT NULL | |
| status | VARCHAR(20) | NOT NULL | CHECK ∈ {pending, paid, waived}, indexed |
| waiver_reason | TEXT | NULL | required when waived |
| notes | TEXT | NULL | |

**Constraints:** UNIQUE(stay_id, period_year, period_month) — one bill per stay
per month, making double-billing structurally impossible; a waiver must state a
reason.
**Index:** `(location_id, period_year, period_month, status)` — the most-run
query in the application.

A month is stored as **two integers, not a date** (ADR-007).

---

#### `payments` — settling one month's rent

| Field | Type | Null | Notes |
|---|---|---|---|
| location_id | UUID | NOT NULL | FK → locations, indexed |
| rent_record_id | UUID | NOT NULL | FK → rent_records, CASCADE, **UNIQUE** |
| amount | INTEGER (₹) | NOT NULL | CHECK > 0 |
| paid_on | DATE | NOT NULL | |
| method | VARCHAR(20) | NOT NULL | CHECK ∈ {cash, upi, bank_transfer, other} |
| reference | VARCHAR(80) | NULL | |
| marked_by_user_id | UUID | NOT NULL | FK → users, **RESTRICT**, indexed |
| notes | TEXT | NULL | |

`rent_record_id` is UNIQUE — **one payment per month, no partial payments**.
That single constraint deletes allocation logic, running balances, installment
schedules and receivables from the system entirely (Project.md §12).

`marked_by_user_id` is RESTRICT so a user cannot be deleted out from under the
audit trail.

---

#### `deposits` — money held on the resident's behalf

| Field | Type | Null | Notes |
|---|---|---|---|
| location_id | UUID | NOT NULL | FK → locations, indexed |
| resident_id | UUID | NOT NULL | FK → residents, CASCADE, indexed |
| stay_id | UUID | NOT NULL | FK → resident_stays, CASCADE, **UNIQUE** |
| amount | INTEGER (₹) | NOT NULL | CHECK ≥ 0 |
| received_on | DATE | NOT NULL | |
| method | VARCHAR(20) | NOT NULL | CHECK valid |
| status | VARCHAR(20) | NOT NULL | CHECK ∈ {held, refunded, forfeited}, indexed |
| received_by_user_id | UUID | NOT NULL | FK → users, RESTRICT |
| notes | TEXT | NULL | |

**Index:** `(location_id, status)` — the "deposits held" figure.
Deposits live in their own tables so they can never be summed into rental
revenue by accident (Project.md §27).

---

#### `deposit_refunds` — settlement at move-out

| Field | Type | Null | Notes |
|---|---|---|---|
| location_id | UUID | NOT NULL | FK → locations, indexed |
| deposit_id | UUID | NOT NULL | FK → deposits, CASCADE, **UNIQUE** |
| gross_amount | INTEGER (₹) | NOT NULL | |
| mandatory_deduction | INTEGER (₹) | NOT NULL | copied from the location's rule |
| other_deduction | INTEGER (₹) | NOT NULL | default 0 |
| other_deduction_reason | TEXT | NULL | required when other_deduction > 0 |
| refund_amount | INTEGER (₹) | NOT NULL | |
| refunded_on | DATE | NULL | NULL = approved but not yet paid out |
| method | VARCHAR(20) | NOT NULL | |
| processed_by_user_id | UUID | NOT NULL | FK → users, RESTRICT |

**The arithmetic is a database constraint, not a convention:**

```sql
CHECK (refund_amount = gross_amount - mandatory_deduction - other_deduction)
```

A refund that does not add up **cannot be stored**. Verified in `verify.py`.

---

#### `move_out_notices`

| Field | Type | Null | Notes |
|---|---|---|---|
| location_id | UUID | NOT NULL | FK → locations, indexed |
| resident_id | UUID | NOT NULL | FK → residents, CASCADE, indexed |
| stay_id | UUID | NOT NULL | FK → resident_stays, CASCADE, indexed |
| notice_date | DATE | NOT NULL | |
| expected_move_out_date | DATE | NOT NULL | notice_date + location's period, indexed |
| actual_move_out_date | DATE | NULL | |
| status | VARCHAR(20) | NOT NULL | CHECK ∈ {active, completed, cancelled}, indexed |
| reason / cancelled_reason | TEXT | NULL | |
| created_by_user_id | UUID | NOT NULL | FK → users, RESTRICT |

**Constraints:** expected ≥ notice; actual ≥ notice; a `completed` notice must
carry an actual date.
**Partial unique index:** one **active** notice per stay.
**Index:** `(location_id, status, expected_move_out_date)` — the upcoming
move-outs card.

`expected_move_out_date` is computed then **stored**, so an agreed exception
("she is leaving on the 5th instead") can be recorded without bending the house
rule for everyone.

---

#### `audit_logs`

| Field | Type | Null | Notes |
|---|---|---|---|
| user_id | UUID | NULL | FK → users, SET NULL, indexed |
| location_id | UUID | NULL | FK → locations, SET NULL, indexed |
| action | VARCHAR(30) | NOT NULL | CHECK ∈ AuditAction |
| entity_type | VARCHAR(50) | NOT NULL | |
| entity_id | UUID | NULL | |
| summary | VARCHAR(255) | NULL | |
| changes | JSON | NULL | TEXT on SQLite, JSONB on Postgres |

Both FKs are nullable: a super admin logging in or creating a location belongs
to no single building.

---

## 4. Bed and resident state machines

### Bed status

```
        assign resident
AVAILABLE ──────────────► OCCUPIED
    ▲                        │ resident serves notice
    │                        ▼
    │                     NOTICE          (still occupied, still paying)
    │                        │ resident actually leaves
    └────────────────────────┘

AVAILABLE ◄──► BLOCKED   (repair / storage — not rentable, not "lost revenue")
```

**Resolved ambiguity.** Project.md lists "Available / Vacant / Occupied" in §7
but explains "Occupied / To-be Vacant / Available". We treat **Available and
Vacant as the same thing** (an empty, rentable bed) and keep **NOTICE** for the
genuinely distinct "frees up on a known date" state. `BLOCKED` was added because
a bed under repair is neither occupied nor a vacancy the owner can sell.

### Resident status

```
ACTIVE ──serve notice──► NOTICE ──move out──► LEFT
   ▲                        │
   └──── notice cancelled ──┘
```

Bed and resident statuses are kept in step by the service layer; the underlying
truth is always `resident_stays.end_date IS NULL`.

---

## 5. How each required figure is computed

All in `app/services/queries.py`, all verified against seed data.

| Figure | Source |
|---|---|
| Total / occupied / vacant beds | `GROUP BY beds.status` for the location |
| Occupancy % | `(occupied + notice) / (occupied + notice + available)`; **blocked excluded** |
| Expected rent | `SUM(amount_due) WHERE status <> 'waived'` for the period |
| Collected rent | `SUM(amount_due) WHERE status = 'paid'` |
| Pending rent | expected − collected |
| Collection % | collected / expected |
| Defaulters list | `rent_records` ⋈ residents ⋈ beds ⋈ flats `WHERE status='pending'` — one query, with phone numbers |
| Vacancy revenue loss | `SUM(beds.default_rent) WHERE status='available'` — real per-bed rents, not count × average |
| Upcoming move-outs | active notices with `expected_move_out_date <= today + 30` |
| Deposits held | `SUM(deposits.amount) WHERE status='held'` — **owner only** |
| Resident ledger | `rent_records` ⋈ payments ⋈ users, ordered by period |
| Month-end summary | the above, composed for one period |

A resident under notice **counts as occupied** — they still live there and still
pay. That is why `occupancy_rate` uses `occupied + notice`.

---

## 6. Security boundaries

1. **No ORM object ever reaches the UI.** Every response is a Pydantic DTO in
   `app/schemas/dto.py`. A field that is not declared there cannot be
   serialised — `password_hash` and `auth_user_id` are absent by construction.
2. **Role-based withholding happens in the service, not the UI.** A manager's
   `DashboardView` comes back with `deposits_held = None`; the number is never
   fetched, never sent, never merely hidden.
3. **Fail closed.** A manager with no grants gets an always-false predicate, not
   an unfiltered query.
4. **Fetch-by-id is re-checked.** `assert_owned()` exists because loading a row
   by primary key bypasses `scope()`.
5. **404, not 403,** for cross-tenant access.
6. **The audit trail cannot be orphaned.** `marked_by_user_id`,
   `processed_by_user_id` and `created_by_user_id` are all `RESTRICT`.
7. **Money rules are database constraints**, not application conventions:
   refund arithmetic, one payment per month, one bill per stay per month.

---

## 7. Development data

`python -m scripts.init_db --reset` builds the schema and loads a deterministic
dataset (fixed seed, fixed "today" of 2026-08-20):

| Table | Rows |
|---|---|
| users | 4 (1 owner + 3 managers) |
| user_locations | 3 |
| locations | 3 (Kothrud, Baner, Hinjewadi) |
| floors / flats / rooms | 7 / 14 / 49 |
| beds | 112 |
| residents | 82 |
| resident_stays | 82 |
| rent_records | 239 |
| payments | 219 |
| deposits | 82 |
| deposit_refunds | 4 |
| move_out_notices | 12 |
| audit_logs | 13 |
| **Total** | **925** |

Every operational state has a live example: residents paid up, one-month
defaulters, two-month defaulters, residents under notice, residents who have
left with settled deposits, a bed blocked for repair, and three months of rent
history so the ledger screen is never empty.

**Login credentials (development only):**
`owner@gvcexecutive.in` / `owner@123`, and
`manager.ktd@gvcexecutive.in` / `ktd@123` (likewise `bnr`, `hjw`).

---

## 8. Verification

Two suites, both passing.

### `python -m scripts.crosscheck` — 188 checks, 0 disagreements

Every dashboard figure is recomputed by a **second, different method** — raw
rows pulled and totalled in Python — and compared against the SQL aggregate.
An aggregate and a hand count that disagree mean one of them is wrong; agreeing
across every building and every month is what makes the numbers trustworthy.

It covers, per building and per month with data:

* bed counts by status, and that the cached `beds.status` matches live stays
* occupancy %, computed both ways
* expected / collected / pending rent, and the identity `expected = collected + pending`
* that `SUM(payments.amount)` equals collected rent
* that no PAID record lacks a payment row, and no PENDING record has one
* the defaulters list length and sum against the pending count and pending rent
* deposits held, refunds paid, and that refund arithmetic holds on every row
* resident head-counts against filled beds and against current stays
* notice counts, the one-month notice period, and beds-on-notice
* that no stay, and no rent record, crosses a location boundary
* that every current stay has a rent record for the current month

### `python -m scripts.verify` — 25 checks, all passing

* Dashboard figures reconcile for all three buildings
  (expected = collected + pending; bed counts sum to the total).
* The owner sees all 3 buildings (82 residents); a manager sees 1 (38).
* A manager is denied another building's dashboard **and** resident ledger.
* A manager with no grant sees zero rows.
* The owner receives deposit totals; the manager receives `None`.
* No `password_hash` appears in any serialised response.
* The database rejects double-booking a bed.
* The database rejects a resident holding two beds.
* The database rejects refund arithmetic that does not add up.
* The defaulters list is populated and carries phone numbers.
* The resident ledger shows month-by-month history.

---

## 9. Supabase Postgres

**Verified against the live database.** The full schema was created on the
project's PostgreSQL 17.6 instance inside a transaction and rolled back, which
confirmed the portability claims are real rather than theoretical:

* all 15 tables create cleanly
* both partial unique indexes translate to `WHERE is_current`
* `GUID` becomes a native `UUID` column
* the audit `changes` column becomes `JSONB`
* CHECK constraints carry over
* Supabase was left untouched — 0 tables remaining afterwards

The change is **one environment variable**:

```bash
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

What makes that possible:

| Concern | How it is handled |
|---|---|
| UUIDs | `GUID` type → native `UUID` on PG, `CHAR(36)` on SQLite |
| Timestamps | `TZDateTime` normalises to aware UTC on both |
| Money | plain `INTEGER` — identical everywhere |
| Enums | `VARCHAR` + `CHECK`, never a native PG ENUM |
| Booleans | expressed as `AND`/`NOT`, never `= 1` |
| Partial indexes | both `sqlite_where` and `postgresql_where` declared |
| JSON | `JSON().with_variant(JSONB, "postgresql")` → JSONB on PG, TEXT on SQLite |
| Pooler | prepared statements disabled on port 6543 (PgBouncer transaction mode) |
| Constraint names | explicit naming convention, so Alembic can alter them later |
| FK enforcement | `PRAGMA foreign_keys=ON` makes SQLite behave like PG |
| Connection pool | pooled endpoint, small pool, `pool_pre_ping` |

**Remaining manual steps at cutover:**
1. Run `scripts/migrate_to_supabase.py` to create the schema and the owner account.
2. Add RLS policies on `location_id` (layer 3) — **SQL not yet written**.

Authentication stays in this application's `users` table rather than moving to
Supabase Auth (see ADR-023), so `auth_user_id` remains unused for now.

---

## 10. Render 500 MB constraint

| Decision | Effect |
|---|---|
| stdlib PBKDF2 instead of bcrypt/argon2 | no compiled crypto wheels |
| `psycopg[binary]` | pure wheel; no local libpq or build toolchain |
| No pandas / numpy / celery / redis | aggregation is done in SQL, where it belongs |
| No background worker | rent generation is a request-triggered idempotent operation |
| SQLAlchemy Core aggregates | totals computed by the database, not in Python |
| PyJWT instead of python-jose[cryptography] | no rust-built crypto wheel |
| No `email-validator` / `dnspython` | email shape checked with a pattern |
| 8 runtime dependencies total | see `requirements.txt` |

**Measured, not estimated: 101 MB installed** — roughly 20 % of the 500 MB cap.
`psycopg[binary]` accounts for 20 MB of that.

`--workers 1` is required, not just economical: the login lockout counter lives
in process memory, so a second worker would keep a separate counter and halve
the effective attempt limit.

---

## 11. Deliberately out of scope

Per Project.md §46, and absent from this schema by design: payment gateway, UPI
integration, online collection, bank reconciliation, expenses, profit & loss,
tax, payroll, vendor management, electricity billing, partial payments,
installment schedules, resident login, complex historical tenancy management,
and any room-allocation engine.

---

## 12. Running it

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python -m scripts.init_db --reset   # schema + 925 seed rows
.venv/bin/python -m scripts.verify            # 25 checks
```

## 13. Authentication and the API surface

### Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/login` | public | exchange credentials for a token |
| GET | `/api/v1/auth/me` | any user | identity + accessible locations |
| GET | `/api/v1/locations` | any user | site picker, with live summaries |
| GET | `/api/v1/locations/{id}/dashboard` | any user | the whole dashboard, one snapshot |
| GET | `/api/v1/locations/{id}/analysis` | **owner** | revenue drill-down behind the rent card |
| GET | `/api/v1/locations/{id}/occupancy` | any user | the seat map behind the occupancy card |
| GET | `/api/v1/locations/{id}/vehicles` | any user | vehicle register and lookup |
| GET | `/api/v1/users` | **owner** | staff list |
| POST | `/api/v1/users` | **owner** | create a manager |
| POST | `/api/v1/users/{id}/deactivate` | **owner** | disable an account |
| GET | `/health` | public | liveness probe |

### Login defences

1. **No registration endpoint.** Accounts are issued by the owner from inside
   the application. A public sign-up form on a private tool is attack surface
   with no user.
2. **Owners cannot create owners.** `role` is hard-coded to `MANAGER` in the
   create handler — it is not a request field, so there is no parameter to
   tamper with. A stolen owner session cannot mint a permanent backdoor account.
   *(Verified: posting `"role": "super_admin"` produced a manager.)*
3. **One error message** for unknown email, wrong password and disabled account.
4. **Constant-time misses.** An unknown account is verified against a dummy
   hash so a miss costs the same CPU as a hit — measured at 284 ms either way,
   so response timing reveals nothing about who has an account.
5. **Lockout** after 5 failures per (email, IP) for 15 minutes. Keyed on the
   pair so an attacker cannot lock a real user out from elsewhere.
6. **PBKDF2-HMAC-SHA256, 600,000 iterations** (OWASP guidance), no binary deps.
7. **Password minimum 12 characters** for new accounts.
8. **Tokens carry identity and role only** — never the location grants, which
   are re-read from the database on every request, so revoking a manager's
   access takes effect immediately rather than at token expiry.
9. **Deactivation is immediate**: the user row is re-read per request.

### Token handling

The JWT never reaches client-side JavaScript. The browser posts to a Next.js
route handler on the Vercel origin, which forwards to FastAPI and stores the
token in a **first-party httpOnly cookie**. Server components read that cookie
and attach a bearer header.

This sidesteps third-party cookies entirely — Vercel and Render are different
origins, and Safari blocks cross-site cookies — and means an XSS bug on the
frontend cannot exfiltrate the token. It also keeps `API_BASE_URL` server-side,
so the backend address is never published.

## 14. Frontend

| Route | Purpose |
|---|---|
| `/login` | sign-in; no registration link |
| `/sites` | site picker with live occupancy and outstanding rent per building |
| `/sites/[id]` | the dashboard |
| `/sites/[id]/rent` | revenue analysis — reached by clicking the rent card (owner only) |
| `/sites/[id]/occupancy` | the seat map — reached by clicking the occupancy card (both roles) |
| `/sites/[id]/vehicles` | vehicle lookup (both roles) |

A manager with exactly one building skips the picker.

**Design.** Warm paper ground, ink text, hairline rules rather than drop
shadows, near-square corners, and one clay accent. Fraunces for headings, IBM
Plex Sans for UI, IBM Plex Mono with tabular figures for every number, so
columns of rupees align to the digit. Rupees use Indian digit grouping
(₹1,32,000). Full light and dark themes, both keyed to the same warm palette.

**Responsive.** Tables become cards below `sm`, with phone numbers as tappable
`tel:` links. Verified at 390 px and 1440 px, in both themes; no horizontal
overflow.

## 14a. Revenue analysis

Clicking the rent card on the dashboard opens the drill-down. Owner-only: a
manager's rent panel is rendered as a static block, not a link, so no
affordance is offered that would answer 404.

### The financial model

Four figures, in order of how much of each we actually see:

```
POTENTIAL    every active bed at its own list rent
  − vacancy loss          (beds nobody is in)
CONTRACTED   what current residents agreed to pay
  − rate leakage          (beds let below list price)
BILLED       invoiced for the month
  − pending               (billed, not received)
COLLECTED    what arrived
```

The headline is **yield = collected ÷ potential**, and it factors *exactly*
into three independent rates:

```
yield  =  beds filled  ×  billed vs list  ×  rent collected
          (empty beds)   (under-billing)    (non-payment)
```

That decomposition is the point of the screen. 56.6% yield means something very
different at 68 × 100 × 84 (beds are empty) than at 95 × 99 × 60 (nobody is
paying) — three different problems with three different fixes, and a single
revenue figure hides which one you have.

The middle factor is measured against **billed**, not contracted, so the
product is exact. Measuring it against contracted looks more intuitive but
leaves a residue: a resident who leaves mid-month is still billed for that
month while no longer being a current contract. `contract_realisation` and
`rate_leakage` carry the pricing view separately.

### Dimensions

Every cut covers the same beds, so all subtotals equal the grand total:

| Dimension | Question it answers |
|---|---|
| Floor | Which floors carry the building, which are dead weight |
| Male vs female flats | Which side performs better |
| Attached vs shared bath | Is the attached premium actually realised |
| Hall vs bedroom | Are cheap hall beds worth the space |
| Flat type (2BHK/3BHK/RK) | Which configuration earns more per bed |
| Individual flat | Best and worst units, ranked |

Per segment: beds, occupied/vacant/blocked, occupancy %, value-weighted
occupancy, potential, contracted, billed, collected, pending, vacancy loss,
rate leakage, collection %, yield %, **RevPAB** (revenue per available bed —
the only per-bed figure that lets a 48-bed building be compared with a 32-bed
one), ARPO, and average list rent.

Plus payment behaviour (on-time vs late, measured from each resident's own due
date), month-on-month trend, and generated callouts naming the weakest floor,
the weakest flat, and any pricing or collection gap.

### How it is computed

Two queries — one row per bed, one row per rent record — rolled up in Python
across all six dimensions. Deliberately **not** one `GROUP BY` per dimension:
rolling up a single fact set guarantees that floors, flat types and genders all
sum to identical totals. Six separate queries with six join paths would
eventually disagree, and a report whose own subtotals contradict each other is
worse than no report.

Verified: **270 dimension subtotals** checked against their grand totals across
3 buildings × 3 months × 6 dimensions × 5 measures — 0 mismatches.

### Schema additions

| Column | Why |
|---|---|
| `residents.gender` | NOT NULL, CHECK ∈ {male, female, other} — flats are allocated by gender, and an optional column would grow a silent "unknown" bucket |
| `flats.gender_policy` | NOT NULL, CHECK ∈ {male, female, mixed} — held on the flat, since most PGs run both in one block |

## 14b. Occupancy board

Clicking the occupancy card opens the seat map. **Open to managers as well as
the owner** — knowing which bed is free and who has not paid is the daily job,
not privileged analysis. That is the deliberate difference from the revenue
page.

### The metaphor

A cinema booking chart, where a **room is a price tier**:

```
FLAT 201 · 2BHK · MALE                                5 / 7
  HALL           ₹7,000    ① ② ③
  SHARED BATH    ₹8,000    ④ ⑤
  ATTACHED BATH  ₹9,500    ⑥ ⑦
```

### Six seat states

| State | Colour | Glyph | Meaning |
|---|---|---|---|
| Paid | moss | ✓ | living here, this month settled |
| Rent due | amber | ! | living here, has not paid |
| On notice | slate | → | leaving; the seat carries the free-from date |
| Booked | indigo | ◆ | reserved, arriving on a known date |
| Vacant | clay wash | — | empty and sellable |
| Out of service | hatched | × | blocked for repair |

Colour is never the only signal: every seat also carries a glyph and an
`aria-label` naming its state and occupant. Seats are 44 px — this is used on a
tablet, often standing up.

**Seat state is derived, not stored.** `beds.status` records the physical fact;
the two *occupied* states come from joining this month's rent record, because
"who is in this bed" and "have they paid" are the two questions staff actually
combine.

### What this page deliberately does not repeat

The dashboard already owns bed counts, occupancy %, vacancy loss and the
move-out list. Repeating them would be clutter. What only a spatial view can
give:

* **Filter chips** — Vacant · Rent due · On notice · Booked · Attached · Hall.
  Non-matching seats dim to 22%. This is the one-stop checklist, and exists
  nowhere else.
* **Free by tier** — "6 hall, 4 shared, 4 attached free", the answer to the
  most common phone call.
* **Free by side** — free beds in male vs female flats.
* **Move-out dates on the seats themselves**, not in a second list.

### Vehicle register

A prominent button leads to `/sites/[id]/vehicles`, built for one question
asked at the gate: whose is this? Plates are stored twice — as written, and
normalised to letters and digits — so "MH12 AB 4472", "mh-12-ab-4472" and a
remembered "4472" all reach the same row. Residents who have **left** are
searchable on purpose: an unfamiliar vehicle usually belongs to someone who
moved out and never collected it.

### Schema additions

| Table / column | Why |
|---|---|
| `bed_reservations` | a booking is not a stay (see ADR-035); holds person, phone, expected move-in, token, agreed rent |
| `BedStatus.BOOKED` | a reserved bed is neither occupied nor sellable |
| `vehicles` | plate + normalised plate, type, make, colour; unique per location |

`BOOKED` sits in the occupancy denominator but not the numerator — it correctly
drags occupancy down until the person arrives — and is **excluded from vacancy
loss**, because that revenue is committed rather than lost.

## 15. Not yet built

* Write actions: mark rent paid, assign bed, serve notice, complete move-out
* Residents, Rent and Move-Outs screens
* Per-floor occupancy mapping and statistics (the next step you flagged)
* Rent-record generation for a new month (idempotent via the unique constraint)
* Alembic baseline migration
* **Supabase RLS policy SQL** — the one item blocking production
* An automated test suite (`verify.py` and `crosscheck.py` are checks, not tests)
