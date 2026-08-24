# Architectural Decisions — PG Logistics & Rent Tally Portal (Backend)

Each entry records a decision, why it was taken, what was rejected, and what it
costs. Decisions were made against the requirements in `Project.md`.

**Legend:** ✅ implemented · ⚠️ has a real cost · 🔄 revisit if the business changes

---

## ADR-001 — SQLAlchemy ORM as the database abstraction ✅

**Decision.** All data access goes through SQLAlchemy 2.0 declarative models.
No raw SQL in application code.

**Why.** The requirement is explicit: SQLite now, Supabase Postgres later, with
minimal change. SQLAlchemy is the only mature Python layer that emits correct
DDL and DML for both from one model definition, and it is what makes the
migration a config change rather than a rewrite.

**Rejected.**
* *Raw SQL + sqlite3* — would hard-code SQLite dialect into every query, which is
  precisely the dependency requirement 9 forbids.
* *Supabase Python client for everything* — would make SQLite impossible and tie
  local development to a network service.
* *Tortoise / SQLModel* — SQLModel blurs the DTO/table boundary that requirement
  11 asks us to keep sharp (see ADR-012).

**Cost.** ⚠️ A learning curve, and a real risk of accidental N+1 queries. Mitigated
by putting the hot reads in `services/queries.py` as explicit joins.

---

## ADR-002 — UUID primary keys, not autoincrement integers ✅

**Decision.** Every table uses a UUID PK via a custom `GUID` type: native `UUID`
on Postgres, `CHAR(36)` on SQLite.

**Why.**
1. Ids are generated in Python, so a row's id is known before flush — which lets
   the seed script build a whole flat of related rows in one pass.
2. Sequential integers in URLs leak business volume (`/residents/47` tells a
   competitor how many residents exist).
3. If the three buildings ever needed merging from separate sources, integer PKs
   would collide.
4. Supabase Auth issues UUIDs, so `users.auth_user_id` matches naturally.

**Rejected.** *BIGSERIAL* — smaller and faster, but loses all four benefits above.

**Cost.** ⚠️ 36 bytes per key on SQLite versus 8, and slightly slower joins. At
~250 beds and a few thousand rent records a year, this is irrelevant. At a
million rows it would not be.

---

## ADR-003 — Money as INTEGER rupees ✅ 🔄

**Decision.** All money is a plain `INTEGER` holding **whole rupees**.

**Why.** The business is entirely whole-rupee: rents of ₹8,000, a flat ₹1,000
deduction, and no partial payments at all (Project.md §12). An integer is exact,
sums and sorts correctly, and behaves **identically** on SQLite and Postgres.

**Rejected.**
* *FLOAT* — never correct for money; ₹0.01 drift on a ₹5,60,000 total is a
  month-end argument waiting to happen.
* *NUMERIC(12,2)* — correct on Postgres, but SQLite silently degrades it to a
  float behind SQLAlchemy's back, so development and production would disagree.
* *INTEGER paise* — the textbook answer, and genuinely safer in general. Rejected
  because it forces a ÷100 at every read and ×100 at every write for a business
  that will never see a paisa, and each conversion is a place to get it wrong.

**Cost.** ⚠️ **This is the decision most likely to need revisiting.** If the PG ever
charges a non-integer amount (a pro-rata half month, a percentage late fee), this
becomes a widening migration: `INTEGER` → `BIGINT` paise, plus a data conversion
and a sweep of every read site. Flagging it explicitly rather than burying it.

---

## ADR-004 — `location_id` denormalised onto every operational table ✅

**Decision.** Every table below `Location` stores `location_id` directly, even
though it is reachable by joining upward (bed → room → flat → floor → location).

**Why.** This is the single most important decision for requirement 7.
1. **Isolation becomes one predicate at any depth.** Filtering beds by tenant is
   `WHERE location_id = ?`, not a four-table join. A join that is easy to forget
   is a leak; a column that is always there is not.
2. **It is exactly what Supabase RLS needs.** An RLS policy must decide from the
   row itself. A policy that has to join upward is slow and hard to write
   correctly.
3. **Indexes get much better.** `(location_id, status)` on beds and
   `(location_id, period_year, period_month, status)` on rent records serve the
   dashboard directly.

**Rejected.** *Strict normalisation* — theoretically cleaner, but makes the tenant
boundary a property of every query rather than of the data, and makes RLS
impractical.

**Cost.** ⚠️ Redundant data that could theoretically drift: a bed could claim
location A while its room claims location B. Mitigated because only the service
layer writes these, and it copies the parent's value. **A defensive improvement
would be composite foreign keys** — `FOREIGN KEY (flat_id, location_id) REFERENCES
flats(id, location_id)` — which would make drift impossible rather than merely
unlikely. Not implemented yet; noted as a hardening step.

---

## ADR-005 — `resident_stays` separates the person from the tenancy ✅

**Decision.** A resident is a person; a **stay** is one continuous occupation of
one bed at one rent. Rent records, deposits and notices hang off the *stay*.

**Why.** This is what keeps history honest. Without it:
* moving someone from 101-1NA to 204-2A would destroy the record of who slept
  where in June;
* revising a rent would retroactively rewrite past months' ledgers, because the
  ledger would read the resident's *current* rent;
* a returning resident would have their old and new deposits confused.

`end_date IS NULL` is then the single source of truth for occupancy.

**Rejected.** *Bed and rent columns directly on `residents`* — simpler, and the
obvious first move. It fails the moment anyone changes bed or rent, and
Project.md §14 explicitly wants a month-by-month ledger, which requires that
each month remember its own amount.

**Cost.** ⚠️ One extra join in most queries, and the service layer must keep
`is_current`, `beds.status` and `residents.status` in step on every transition.
A CHECK constraint ties `is_current` to `end_date`; the rest is service
discipline covered by `verify.py`.

---

## ADR-006 — Beds carry their own `default_rent` ✅

**Decision.** `beds.default_rent` stores the rent that bed is expected to fetch,
separately from the rent the current resident actually pays
(`resident_stays.monthly_rent`).

**Why.** This was one of the open questions I raised when reading `Project.md`,
and §21 answers it: *"the system can calculate this based on the actual rent
associated with each vacant bed"*. A vacant bed has **no resident to read a rent
from**. Without a rent on the bed itself, vacancy loss could only be
`vacant_count × average_rent`, which the requirement explicitly calls the less
accurate option. With it, the figure is a true `SUM` of real per-bed rents.

It also gives the owner a sensible default when assigning a new resident, and
lets an attached bed price higher than a hall bed without any special-casing.

**Cost.** One more field to maintain during building setup. The seed derives it
from room type (attached +₹1,500, hall −₹1,000), which is a reasonable default
for the UI to offer.

---

## ADR-007 — Rent periods as `(year, month)` integers, not a date ✅

**Decision.** `rent_records.period_year` and `period_month` are separate integers.

**Why.** A month is not a day. Storing "August 2026" as `2026-08-01` invites
every off-by-one and timezone bug at month boundaries, and makes "the same month"
comparisons depend on a convention everyone must remember. Two integers sort,
group, compare and index exactly, on both backends. The unique constraint
`(stay_id, period_year, period_month)` then reads as what it means: **one bill per
resident per month**, making double-billing structurally impossible.

**Rejected.** *A `period_start` DATE* — needs a "always use the 1st" convention
enforced nowhere. *A `"2026-08"` string* — sorts correctly by luck, not design,
and cannot be arithmetically incremented.

**Cost.** Slightly more verbose queries; "the previous month" needs a couple of
lines rather than date arithmetic.

---

## ADR-008 — One payment per rent record, enforced by UNIQUE ✅

**Decision.** `payments.rent_record_id` is UNIQUE.

**Why.** Project.md §12 is emphatic that there are no partial payments. Encoding
that as a database constraint rather than an application rule **deletes entire
subsystems**: no payment allocation, no running balances, no installment
schedules, no receivables ageing, no reconciliation. The month is paid or it is
not.

**Cost.** ⚠️ If the business ever accepts a part payment, this is not a small
change: drop the constraint, add an `amount_paid` running total to rent records,
and rewrite every "is it paid" check. That is the correct trade — Project.md says
the simplicity is deliberate, so the schema should make the simple case airtight
rather than pre-building for a case the owner has ruled out. 🔄

---

## ADR-009 — Refund arithmetic is a CHECK constraint ✅

**Decision.**
```sql
CHECK (refund_amount = gross_amount - mandatory_deduction - other_deduction)
```
and each component is stored, not just the final number.

**Why.** Money leaving the business is the highest-consequence write in the
system. A bug in the service layer, a bad manual correction, or a future
developer could otherwise store a refund that does not add up, and nobody would
notice until the resident did. Storing every component lets the arithmetic be
*shown* at move-out, which is what §26 asks for.

`mandatory_deduction` is **copied from the location at settlement time**, not read
live, so raising the house deduction later cannot silently restate refunds that
were already paid out.

**Cost.** A correction requires updating the components consistently, not just
the total. That is the point.

---

## ADR-010 — Isolation enforced in three independent layers ✅

**Decision.** Schema (`location_id` everywhere) + service (`scope()` / `require()`)
+ database (Supabase RLS, at cutover).

**Why.** Requirement 7 makes cross-PG leakage the most serious failure this
system can have. One mechanism means one bug is a breach. Layer 3 does not exist
on SQLite, which is exactly why layer 2 raises `AccessDenied` — a **hard failure**
— rather than quietly filtering to nothing. A silent filter hides the bug; an
exception surfaces it in development.

**Sub-decision: `AccessDenied` maps to HTTP 404, not 403.** Answering 403 confirms
that a location exists but belongs to someone else, which leaks the owner's
portfolio to a manager. To a manager, other buildings do not exist.

**Sub-decision: fail closed.** A manager with no grants gets an always-false
predicate. The natural bug — `if not location_ids: return stmt` — would show them
*everything*.

**Cost.** ⚠️ Layer 3 is **not yet written**. Until the RLS policies exist, anything
holding the Supabase service-role key bypasses isolation entirely. That key must
stay server-side, and writing those policies is a prerequisite for going live.

---

## ADR-011 — Managers granted via a join table ✅

**Decision.** `user_locations`, not a `location_id` column on `users`.

**Why.** Project.md §2 says locations 4 and 5 are coming. A manager covering two
buildings during a handover, or an area manager over two PGs, is an ordinary
business situation — it should not require a schema migration. Super admins need
no rows at all; their access follows from the role, so a newly created location
is visible without re-granting or re-login.

**Cost.** One join to resolve a manager's scope. Loaded once per request into the
frozen `AccessContext`.

---

## ADR-012 — DTOs are separate from ORM models ✅

**Decision.** ORM objects never leave the service layer. Every response is a
Pydantic model in `app/schemas/dto.py`.

**Why.** This *is* requirement 11. The property that makes it work: a field not
declared on the DTO **cannot be serialised**. `password_hash` and `auth_user_id`
are not absent because someone remembered to exclude them — they are absent
because they were never declared. Safety by construction beats safety by
vigilance.

It also lets role-based withholding happen in the service: a manager's
`DashboardView` returns `deposits_held = None`. The number is never queried,
never sent, and never merely hidden by the frontend.

**Rejected.** *SQLModel / returning ORM objects directly* — fewer classes, but
every new column becomes a potential leak, and the default is "exposed".

**Cost.** ⚠️ Two definitions of overlapping shapes, kept in sync by hand. Accepted
deliberately: the duplication is the safety mechanism.

---

## ADR-013 — Enums as VARCHAR + CHECK, never native PG ENUM ✅

**Decision.** Python `StrEnum` for vocabulary; stored as `VARCHAR` guarded by a
generated `CHECK ... IN (...)`.

**Why.** Native Postgres enums need an `ALTER TYPE` migration to add a value and
have **no SQLite equivalent at all** — so development and production would have
different schemas, which is the thing requirement 9 rules out. A CHECK constraint
gives the same protection on both, and adding a value is an ordinary migration.

**Cost.** Marginally more storage than a native enum. Irrelevant at this scale.

---

## ADR-014 — Bed status: `available` = `vacant`, plus `notice` and `blocked` ✅

**Decision.** Four states: `available`, `occupied`, `notice`, `blocked`.

**Why.** `Project.md` is internally inconsistent here — §7 lists
"Available / Vacant / Occupied" but then explains "Occupied / To-be Vacant /
Available". I raised this and resolved it as follows:

* **Available and Vacant mean the same thing** — an empty, rentable bed. Two names
  for one state would guarantee they drift apart in the UI.
* **`notice`** is kept because "frees up on 10-Sep" is genuinely distinct
  information and drives the upcoming-vacancy view.
* **`blocked` was added**, and is not in the requirements. A bed under repair is
  neither occupied nor a vacancy the owner can sell. Without it, every
  maintenance job would inflate "potential revenue loss" with money that was
  never losable.

**Consequence for the maths.** A resident under notice is **still occupied and
still paying**, so `occupancy_rate = (occupied + notice) / (occupied + notice +
available)`, and blocked beds are excluded from that denominator while still
counting toward `total_beds`.

🔄 **Confirm with the owner** that "Available" and "Vacant" were indeed meant as
one state, and that blocked beds should sit outside the occupancy percentage.

---

## ADR-015 — Bed status cached, `resident_stays` authoritative ✅

**Decision.** `beds.status` is a maintained cache; the truth is
`resident_stays.end_date IS NULL`.

**Why.** The dashboard counts beds by status constantly, and a `GROUP BY status`
on an indexed column is far cheaper than a `LEFT JOIN` against stays on every
load. But a cache must never be the only record, or a bug in one transition
permanently corrupts occupancy.

**Guarded by** two partial unique indexes on `resident_stays` that make
double-booking impossible **at the database level** — one bed cannot hold two
current residents, and one resident cannot hold two current beds. Both are
proven in `verify.py`, not assumed.

**Cost.** ⚠️ Every transition must update both. A periodic reconciliation query
comparing bed status against current stays would be a cheap safety net; not built
yet.

---

## ADR-016 — Deposits kept structurally separate from rent ✅

**Decision.** Deposits and refunds live in their own tables, never in
`rent_records` or `payments`.

**Why.** Project.md §27 warns specifically against confusing them. A deposit is
money **held on behalf of** the resident and later returned; rent is revenue. If
they shared a table, one forgotten `WHERE kind = 'rent'` would inflate collected
revenue by lakhs. Separate tables mean the mistake requires a deliberate join.

**Cost.** None worth noting.

---

## ADR-017 — Stdlib PBKDF2 instead of bcrypt or argon2 ✅ *(revised)*

**Decision.** `hashlib.pbkdf2_hmac` (SHA-256, **600,000 iterations**), no crypto
dependency.

**Why.** Requirement 12 caps the Render image at 500 MB, and both bcrypt and
argon2 pull compiled wheels. PBKDF2-HMAC-SHA256 is in the standard library and
is an accepted password KDF; 600,000 iterations is the current OWASP parameter
for it.

**Revised from the original decision.** This was first written on the assumption
that Supabase Auth would own credentials and this code would never run in
production. ADR-023 reverses that, so this is now the real credential path — and
the iteration count was raised from 240,000 to 600,000 accordingly. Measured at
**284 ms** per verification, which is fine for an endpoint used a few times a day.

The hash format is self-describing (`pbkdf2_sha256$iterations$salt$hash`), so the
count can be raised again later without invalidating existing hashes.

**Cost.** ⚠️ Argon2id resists GPU cracking better than PBKDF2 at equal cost. If
the dependency budget ever loosens, argon2id is the upgrade — the stored format
already carries its own algorithm name, so a migration can rehash on next login.

---

## ADR-018 — No background worker, no cache, no queue ✅

**Decision.** No Celery, no Redis, no cron service. Monthly rent generation is a
request-triggered idempotent operation, protected by the
`(stay_id, period_year, period_month)` unique constraint.

**Why.** Requirement 12 asks for lightweight, and requirement 8 warns against
unnecessary infrastructure. A worker would roughly double the memory footprint
and the operational surface to perform **one job a month** for ~250 residents —
a job that takes well under a second. Because generation is idempotent, running
it twice is harmless, so it can safely be triggered by whoever opens the rent
screen first that month.

**Cost.** The first request of a new month does slightly more work. Unnoticeable
at this scale.

---

## ADR-019 — Aggregation in SQL, not in Python ✅

**Decision.** Dashboard figures are computed with `SUM`/`COUNT`/`CASE WHEN`
aggregates. No pandas, no numpy.

**Why.** Two reasons, both requirement 12. Pulling every rent record into Python
to total it would be slower and would scale with resident count; and pandas alone
would consume a large share of the 500 MB budget. Databases are extremely good at
this. `rent_summary()` computes expected, collected, paid count and pending count
in **one pass**.

**Cost.** Slightly denser query code, concentrated in one reviewed file.

---

## ADR-020 — Explicit constraint naming convention ✅

**Decision.** A `MetaData` naming convention for every index, unique, check,
foreign key and primary key.

**Why.** Small decision, disproportionate payoff. Without it SQLite invents
anonymous constraint names, and a later Alembic migration against Postgres cannot
drop or alter them by name — which turns routine schema changes into
table-rebuild scripts. Setting it up before the first migration costs nothing;
retrofitting it afterwards is genuinely painful.

**Cost.** None.

---

## ADR-021 — Lightweight audit log, not event sourcing ✅

**Decision.** One `audit_logs` table with actor, location, action, entity and an
optional JSON diff.

**Why.** Project.md §15 wants to know **who marked a payment and when**, for
month-end verification. That is a narrow, real need. Full event sourcing or
temporal tables would multiply write volume and complexity for a business whose
own stated history requirement is "about two months" (§10).

Critically, `marked_by_user_id`, `processed_by_user_id` and `created_by_user_id`
are `RESTRICT` foreign keys — **a user cannot be deleted out from under the audit
trail**.

**Cost.** No automatic before/after capture; services must write log entries
deliberately. The `changes` JSON column is there when a specific action warrants
it.

---

## ADR-022 — SQLite made to behave like Postgres ✅

**Decision.** `PRAGMA foreign_keys=ON`, WAL journal, busy timeout, on every
connection.

**Why.** SQLite **silently ignores foreign keys by default**. Without this pragma,
every FK in the schema would be decorative during development, and data would
drift into states Postgres later rejects — turning the migration into a data
cleanup. This one line is what makes SQLite a faithful rehearsal rather than a
different database wearing the same schema.

**Cost.** None.

---

## Summary of accepted risks

| # | Risk | Severity | Mitigation / status |
|---|---|---|---|
| ADR-003 | Whole-rupee integers can't express paise | Medium 🔄 | Widening migration if ever needed; flagged, not hidden |
| ADR-004 | Denormalised `location_id` could drift | Low ⚠️ | Composite FKs would eliminate it — **not yet implemented** |
| ADR-008 | Partial payments would need real rework | Low 🔄 | Deliberate; owner has ruled them out |
| ADR-010 | **RLS policies not yet written** | **High** ⚠️ | Prerequisite for production; service-role key must stay server-side |
| ADR-012 | DTO/model duplication drifts | Low | Accepted — the duplication *is* the safety mechanism |
| ADR-015 | Cached bed status could desync | Low ⚠️ | DB-level partial unique indexes; a reconciliation job would help |
| ADR-017 | PBKDF2 weaker than argon2 | Low | Not a production code path |

---

## Open questions for the owner

1. **ADR-014** — Confirm "Available" and "Vacant" were meant as one state, and
   that beds blocked for repair should sit outside the occupancy percentage.
2. **ADR-006** — Confirm that per-bed expected rent is the right basis for
   vacancy loss (§21 implies yes).
3. Should a resident under notice count as **occupied** in the headline
   occupancy figure? Implemented as yes — they still live there and still pay.
4. Is `waived` rent an acceptable owner-only escape hatch for corrections, or
   should mistakes be fixed by editing the record instead?
5. When a resident transfers between beds mid-month, does the rent for that month
   follow the old bed or the new one? Currently each stay bills its own months.


---

## ADR-023 — Authentication in our own `users` table, not Supabase Auth ✅

**Decision.** The application issues and verifies its own credentials and signs
its own JWTs. Supabase provides Postgres only.

**Why.** The system has a handful of staff accounts — one owner and one manager
per building. Supabase Auth would add a second identity provider to keep in
sync with the `users` table that already has to exist (for roles, grants and the
`marked_by` audit references), plus a second failure mode during sign-in, plus a
dependency on Supabase being reachable for login and not merely for data. For
four accounts, that is cost without benefit.

`users.auth_user_id` is kept as a nullable unique column so moving to Supabase
Auth later is an additive migration rather than a redesign.

**Cost.** ⚠️ We own password security ourselves: hashing (ADR-017), lockout, and
the absence of any password-reset flow — the owner currently resets a manager's
password by re-creating the account. A self-service reset needs email delivery,
which is the point at which Supabase Auth may start earning its place. 🔄

---

## ADR-024 — The token lives in a first-party httpOnly cookie ✅

**Decision.** The browser never receives the JWT in JavaScript. It posts to a
Next.js route handler on the Vercel origin; that handler calls FastAPI and puts
the token in an httpOnly, SameSite=Lax, Secure cookie. Server components read
the cookie and forward a bearer header.

**Why.** Three problems solved at once:
1. **Third-party cookies.** Vercel and Render are different origins. A cookie set
   by Render would be cross-site — SameSite=None, Secure, and blocked outright by
   Safari's tracking prevention. Proxying makes it first-party.
2. **XSS.** `localStorage` is readable by any injected script. An httpOnly cookie
   is not.
3. **Exposure.** `API_BASE_URL` has no `NEXT_PUBLIC_` prefix, so the backend
   address never ships to the browser and the API cannot be called from client
   code.

**Rejected.** *Token in localStorage* — the common pattern, and the reason so
many XSS bugs become account takeover.

**Cost.** Every authenticated read is a server component or route handler; there
is no client-side data fetching. For a dashboard that renders server-side anyway,
that is no loss.

---

## ADR-025 — One dashboard endpoint, not one per card ✅

**Decision.** `GET /locations/{id}/dashboard` returns occupancy, rent, vacancy,
resident counts, deposits, the pending list, vacant beds, beds under notice and
upcoming move-outs — in a single response.

**Why.** The value of this screen is that its figures **reconcile**. Occupancy
fetched before a move-out is recorded and rent fetched after it would produce a
dashboard whose own numbers contradict each other, and the owner would have no
way to tell which half was stale. One query set, one point in time, one
`generated_at` stamp printed at the foot of the page.

It also suits Render's free tier, where the instance sleeps: one round trip to
wake it beats nine.

**Cost.** A larger payload, and the whole screen waits for the slowest query.
Both are trivial at this scale, and correctness outranks both.

---

## ADR-026 — In-process login throttle, and therefore one worker ✅

**Decision.** Brute-force lockout state lives in a Python dict guarded by a lock.
Render runs `--workers 1`.

**Why.** Consistent with ADR-018's refusal to add Redis. A dozen logins a day do
not justify a cache service. But the consequence must be stated plainly: **with
two workers each would keep its own counter**, so five attempts would become ten.
One worker is therefore a correctness requirement, not only a memory saving.

**Cost.** ⚠️ This is the first thing that breaks if the backend is ever scaled
horizontally. If that day comes, the throttle moves to a shared store — and this
ADR is the note explaining why it must.

---

## ADR-027 — Owners can create managers, but never other owners ✅

**Decision.** `POST /users` hard-codes `role = MANAGER`. Role is not a field on
the request. The owner role can only be granted with direct database access.

**Why.** It closes an escalation path. If role were a request parameter, a stolen
owner session — or a CSRF against one — could mint a second permanent owner
account as a backdoor that survives the original password being reset. Removing
the parameter means there is nothing to tamper with.

*Verified: posting `"role": "super_admin"` creates a manager.*

**Cost.** Adding a second owner requires a database write. For a family business
with one owner, that is the correct amount of friction.

---

## ADR-028 — Prepared statements disabled on the Supabase pooler ✅

**Decision.** When the connection string names port 6543, psycopg is configured
with `prepare_threshold=None`.

**Why.** Port 6543 is PgBouncer in **transaction** mode: a connection may be
handed to a different client between statements. psycopg3 automatically prepares
a statement after a few executions, and the plan it names may not exist on
whichever backend connection it lands on next. The symptom is intermittent
`prepared statement does not exist` errors that appear only under load — the
worst kind of bug to debug in production.

The alternative, the direct endpoint on port 5432, exhausts its connection limit
quickly on a small instance.

**Cost.** No plan reuse, so a marginally higher per-query cost. Unmeasurable at
this query volume.

---

## Verification of these decisions

The claims above are checked, not asserted:

* **188 cross-checks** (`scripts/crosscheck.py`) recompute every dashboard figure
  by a second method and compare against the SQL aggregate.
* **25 checks** (`scripts/verify.py`) cover schema constraints and access control.
* **The full schema was created on the live Supabase PostgreSQL 17.6 instance**
  inside a transaction and rolled back — confirming partial indexes, native
  UUIDs, JSONB and CHECK constraints all translate. ADR-001, 002, 013 and 015
  are therefore verified against real Postgres, not assumed.
* **101 MB measured** installed footprint against the 500 MB cap (ADR-017/019).
* **284 ms** for both a real and a dummy password verification, confirming the
  timing-equalisation in the login handler.


---

## ADR-029 — Beds carry a list rent, so yield can be decomposed ✅

**Decision.** Revenue analysis is built on `beds.default_rent` as a *list
price*, against which everything else is measured.

**Why.** It turns a flat revenue number into a diagnosis. Without a list price
there is no denominator: you can say "we collected ₹1.66L" but not whether that
is good. With one, collected ÷ potential is a yield, and the shortfall splits
into empty beds, under-pricing, and non-payment.

This is the payoff from ADR-006, which added `default_rent` for vacancy-loss
maths. The same column now anchors the whole financial model.

**Cost.** ⚠️ The analysis is only as honest as the list rents. If they are set
optimistically, yield reads low everywhere and the screen loses its meaning.
They need reviewing when the market moves — a maintenance obligation the owner
should know about. 🔄

---

## ADR-030 — The yield decomposition is exact, at the cost of an intuitive term ✅

**Decision.** `yield = (Po/P) × (B/Po) × (R/B)`, where the middle term uses
**billed**, not contracted rent.

**Why.** The first implementation used contracted, which reads more naturally
("are residents paying list price?"). It did not reconcile: the three factors
multiplied to 58.4% against a stated yield of 61.2%. The cause is real, not a
rounding artefact — a resident who leaves mid-month is still billed for that
month but is no longer a current contract, so contracted and billed genuinely
differ.

A decomposition that does not add up is worse than a slightly less obvious one:
the owner would find the discrepancy, and then trust none of the figures. The
contracted view is kept as `contract_realisation` and `rate_leakage`, which is
where the pricing question actually belongs.

**Cost.** The middle factor can exceed 100% in a month when someone moved out —
correct, but it needs the explanation the UI gives it.

---

## ADR-031 — One fact set, rolled up in Python, not six GROUP BYs ✅

**Decision.** Two queries (one row per bed, one per rent record) accumulated
across all six dimensions in a single pass.

**Why.** Every dimension must sum to the same total, because the owner will
check. Six separate `GROUP BY` queries with six slightly different join paths
would drift apart the first time one of them handled a mid-month move-out
differently. Rolling up one fact set makes agreement structural rather than
coincidental.

Rent facts are joined **through the stay**, not through the current occupant, so
a departed resident's rent is still attributed to the bed they occupied.

**Cost.** ⚠️ All beds for one building are loaded into memory. At ~112 beds that
is nothing; at tens of thousands it would need reworking into SQL aggregates
with a shared CTE. Noted rather than pre-optimised.

**Verified.** 270 subtotals against their grand totals, 0 mismatches.

---

## ADR-032 — Gender is a required column, not an optional one ✅

**Decision.** `residents.gender` is NOT NULL; `flats.gender_policy` is NOT NULL.

**Why.** A PG allocates flats by gender — it is an operational fact, not
demographic decoration, and a resident without one cannot legitimately be
placed. Made required because an optional column would accumulate a silent
"unknown" bucket that quietly grows until the male/female revenue split stops
meaning anything.

`gender_policy` sits on the **flat** rather than the building, because most PGs
run male and female flats in the same block, usually on different floors.

**Cost.** Every resident record needs the field. It is one radio button at
move-in.

---

## ADR-033 — Depth from three stacked shadows, warm-tinted ✅

**Decision.** Cards use a hairline border, a 1px contact shadow, and a wider
soft shadow. Shadow colour is warm brown, never neutral grey. Four sheet levels:
`.sheet`, `.sheet-raised`, `.sheet-sunk`, `.sheet-interactive`.

**Why.** The first build read as "one flat white background with things on it" —
correct feedback. A single large blur is the usual fix and looks generic; three
small stacked cues read as physical. And on cream paper a grey shadow looks like
a smudge, so the shadow is tinted `rgba(90, 70, 45, …)` to match the ground.

In dark mode a cast shadow is nearly invisible, so the tokens flip: depth comes
mostly from the border, and the shadow only deepens the seam beneath a card.

**Cost.** Four levels is a system that has to be applied consistently. Verified
in the Selenium suite, which asserts cards actually have a computed shadow, a
border, and a background distinct from the page.

---

## ADR-034 — UI is tested on computed styles, not markup ✅

**Decision.** The Selenium suite (98 checks) asserts on computed CSS values,
real clicks, and figures scraped from the rendered DOM.

**Why.** It was written after a bug where every page returned HTTP 200 while
being completely unstyled and inert — a stale server was serving HTML that
referenced chunk hashes wiped by a rebuild. Status codes, snapshots and markup
assertions would all have passed. So the suite checks that the body background
is exactly the paper colour, that the accent is exactly clay, that clicking
"Show" changes the input type, and that the on-screen expected/collected/pending
figures reconcile.

**Cost.** ⚠️ Slower than unit tests and needs both servers running. Worth it:
this suite has since caught a manager being shown a link to an owner-only page.

**Operational note.** Never run `rm -rf .next && next build` while the dev
server is live — it wipes the cache out from under the running process and
reproduces exactly the failure above. This cost time twice.


---

## ADR-035 — A booking is not a stay ✅

**Decision.** Advance bookings live in their own `bed_reservations` table, with
the person stored inline rather than as a `Resident` row.

**Why.** A `resident_stay` means someone is living in a bed and owes rent for
it. Every guarantee on that table assumes exactly that: the two partial unique
indexes, and the CHECK tying `is_current` to `end_date`. A future stay would
have to be `is_current = false` with a NULL end date, which that CHECK forbids —
so holding a booking there would mean weakening the constraint that makes
occupancy trustworthy, in order to store something that is not a tenancy.

The person is kept inline for the same reason: they are not a resident until
they arrive. A half-real `Resident` row would appear in head-counts, in the
rent run, and in the residents list, and someone would eventually bill them.

**Cost.** Converting a booking into a tenancy is an explicit step that copies
data across rather than flipping a flag. That step is the right place to create
the resident, the stay and the deposit anyway.

---

## ADR-036 — Seat state is derived; `beds.status` stays physical ✅

**Decision.** The board computes six seat states from bed status **plus** this
month's rent record and any live reservation. `beds.status` keeps only the five
physical states.

**Why.** The two states staff most need to tell apart — someone who has paid and
someone who has not — are not properties of the bed at all; they belong to a
rent record for a particular month. Writing "occupied_unpaid" into `beds.status`
would mean the bed row changing every time a payment is ticked, and going stale
the moment the month rolls over.

Deriving it keeps one physical truth and lets the board ask a *period* question
of it.

**Cost.** The board query joins rent records and reservations. One query,
~170 beds, assembled in Python.

---

## ADR-037 — BOOKED counts against occupancy, but not against vacancy loss ✅

**Decision.** A booked bed sits in the occupancy **denominator** and not the
numerator, and is **excluded** from vacancy loss.

**Why.** Both halves are deliberate and they pull in opposite directions.
Occupancy asks "is someone sleeping here" — no, so it should drag the figure
down until they arrive. Vacancy loss asks "what could I still sell" — nothing,
the bed is spoken for, and counting it would send staff chasing a bed already
promised and overstate the problem.

**Cost.** ⚠️ It is a genuinely new state that had to be threaded through
`occupancy_stats`, the analysis segments, the vacant list, the dashboard and
three test suites. `verify.py` caught the one place the change was missed —
which is the argument for having written it.

---

## ADR-038 — Plates stored twice: as written, and normalised ✅

**Decision.** `vehicles.vehicle_number` holds what the owner typed;
`number_normalised` holds letters and digits only, uppercased, and is the column
every search runs against.

**Why.** The same plate gets written "MH12AB4472", "MH 12 AB 4472" and
"mh-12-ab-4472", and at a gate nobody recalls the whole thing — they remember
the last four digits. Normalising on read would mean a full scan and no usable
index; normalising on write makes the lookup an indexed substring match, and
keeps the display form intact so it still looks like a plate.

Uniqueness is enforced on the normalised form per location, because an ambiguous
answer to "whose is this?" is the one failure this feature cannot have.

**Cost.** Two columns to keep in step. Both are set in one place, and
`crosscheck.py` asserts the normalised form really is normalised.

---

## ADR-039 — Ex-residents stay in the vehicle register ✅

**Decision.** The lookup searches residents who have left, and labels them.

**Why.** The vehicle you cannot identify is usually the one whose owner moved
out months ago and never collected it. A lookup that only covered current
residents would fail on exactly the case it exists for. The result is labelled
"Left the PG" with no current bed, so the answer is complete rather than
misleading.

**Cost.** None; the register grows slowly.

---

## ADR-040 — The board repeats nothing the dashboard already shows ✅

**Decision.** No bed counts, no occupancy percentage, no vacancy-loss figure and
no move-out list on the occupancy page. It carries filter chips, free-by-tier,
free-by-side, and move-out dates printed on the seats themselves.

**Why.** A brief we were given directly: no redundant data. Two screens showing
the same number is not twice as useful — it is a maintenance liability and an
invitation to notice them disagreeing. Each figure should have one home, and the
board's job is the spatial question the dashboard cannot answer: *which* bed,
next to which, in which tier, free from when.

**Cost.** Anyone wanting the headline occupancy figure has to go back one
screen. That is one tap, and it is where that number lives.


---

## ADR-041 — Every write carries an idempotency key ✅

**Decision.** `expenses.idempotency_key` is UNIQUE and required. The client
mints one per submit attempt; a replay returns the existing row with
`created: false` and HTTP 200.

**Why.** This is the first thing in the application that writes money, and the
failure it prevents is ordinary: a manager on a weak connection taps Save,
sees nothing happen, taps again. Without a key that is two payments on the
books, and nobody notices until the month does not reconcile.

Required rather than optional, because an optional safety mechanism is one
that a future caller forgets. Checked *before* validation, so a replay is
never even re-evaluated.

**Cost.** The client must generate a UUID. `crypto.randomUUID()` is one line.

---

## ADR-042 — Expenses are voided, never deleted ✅

**Decision.** A wrong entry keeps its row and gains `status = 'void'`, a
reason, an author and a timestamp. A CHECK constraint refuses a void without
the first two.

**Why.** Spend that disappears from a ledger is worse than spend that is
visibly wrong: the total silently changes and there is nothing to explain it.
A struck-through row with "recorded twice by mistake" beside it is a complete
account of what happened.

**Manager window.** A manager may void only their own entry, and only within
24 hours — enough to fix a fat-fingered amount, not enough to rewrite a month
that has already been reported on. Deliberately a rolling window rather than
"the same calendar day", so filing at 11:58pm does not cost you the ability to
correct it at midnight.

**Cost.** Every read has to filter on status. Wrapped in `month_view()` so no
caller can forget.

---

## ADR-043 — Owner-only expense categories ✅

**Decision.** Site rent, salaries, taxes, insurance, EMI and deposit refunds
can only be filed by a super admin. Enforced in the service; the API returns
403 with an explanation.

**Why.** A manager runs a building day to day. The lease, the payroll and the
tax bill are the fixed cost base of the business, and letting a site login
write to them means whoever holds that login can move the company's cost
structure. The categories are still *shown* in the form, disabled and marked —
hiding them entirely would leave a manager wondering where to file the rent.

**403 here, 404 for a foreign site.** A forbidden category is worth explaining:
it leaks nothing and the user can act on it. A forbidden *building* must stay
invisible (ADR-010).

**Cost.** A manager who genuinely needs to record a salary must ask an owner.
That is the intended friction.

---

## ADR-044 — One live booking per recurring item per month ✅

**Decision.** A partial unique index on
`(template_id, period_year, period_month) WHERE template_id IS NOT NULL AND
status = 'recorded'`.

**Why.** The whole point of the "still to record this month" checklist is that
two people can both see the rent is unpaid. Both may tap it. The idempotency
key does not help — those are two genuine attempts with different keys — so
the guarantee has to come from the data: October's rent exists once or not at
all.

Voided rows fall out of the index, so a mistaken entry can be voided and
re-recorded correctly.

**Cost.** The service has to translate the resulting IntegrityError into
"already recorded for this month" rather than leaking a database error.

---

## ADR-045 — `paid_from` distinguishes whose money left ✅

**Decision.** Three sources: site petty cash, business account, or personal.
`reimbursed_on` may only be set on the last, enforced by CHECK.

**Why.** Without it, a manager buying cleaning supplies out of their own pocket
is indistinguishable from petty cash, and they are never paid back. The page
totals what is owed to staff so it cannot be forgotten.

**Cost.** One more field on the form, defaulted and remembered between entries.

---

## ADR-046 — CSRF origin check on the write proxies ✅

**Decision.** `assertSameOrigin()` rejects any POST to the Next.js write
handlers whose `Origin` does not match the host, or that has no `Origin` at all.

**Why.** Reads were safe by construction — a cross-site page cannot set an
`Authorization` header, and cannot read a cross-origin response. Writes are
different: the Next.js proxy reads a **cookie**, which is exactly the shape a
CSRF attack needs.

`SameSite=Lax` already blocks the cookie on a cross-site POST, so this is
defence in depth rather than the only guard. It is worth having because Lax is
a browser behaviour we do not control: it has exceptions, it varies by version,
and a future change to `SameSite=None` for an embed would silently remove the
protection. An explicit origin check keeps working regardless.

**Cost.** None meaningful. Verified: no origin → 403, foreign origin → 403,
same origin → 201.

---

## ADR-047 — Recurrence is the interface, not a scheduler ✅

**Decision.** Templates describe recurring costs, but nothing is ever recorded
automatically. The page lists what is *not yet* recorded and makes each one a
tap.

**Why.** Auto-posting the rent every month would produce a ledger of things
nobody checked — and the first time the landlord was not paid, the accounts
would say otherwise. Keeping a human tap keeps every row an assertion that the
money actually moved.

Listing the unrecorded items gets most of the benefit anyway: the reason
expense tracking fails is not that entry is hard, it is that nobody remembers
what is missing.

**Cost.** Someone still has to open the page each month. The checklist is the
prompt.

---

## ADR-048 — Sticky header needs `scroll-padding-top` ✅

**Decision.** `html { scroll-padding-top: 5rem }`, plus `scroll-margin-top` on
the expense form.

**Why.** Found by the Selenium suite, which could not click the form toggle:
the sticky top bar was intercepting the click. It was a real bug, not a test
artefact — "Repeat" scrolled to the page top and left the form's first control
underneath the header, invisible and untappable on a phone.

**Cost.** None. Worth recording because a sticky header breaks every in-page
scroll target, and it is invisible until something tries to click one.
