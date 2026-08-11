# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MARKETA — a single-tenant store-management platform for an Iranian neighbourhood
supermarket: POS, purchasing, inventory, customer credit, supplier debt, cheques,
cashier shifts, a loyalty program, expenses/payroll, and ~17 reports. FastAPI +
SQLAlchemy backend, React/TypeScript frontend, Persian-first UI.

Status and roadmap live in `docs/MARKETA_FEATURE_AUDIT.md` (dated — verify its
claims against the code before relying on them; several P1s it lists as open have
since been closed). The largest genuine gaps are **no tax/VAT anywhere in the
schema** and **no double-entry accounting** (customer/supplier balances are
running totals, not a ledger).

## Commands

Backend (`backend/`, a `.venv` already exists there):

```bash
.venv/bin/uvicorn app.main:app --reload     # API on :8000, docs at /docs
.venv/bin/python -m pytest                  # 169 tests
.venv/bin/python -m pytest tests/test_sales.py::test_get_sale_returns_sale_with_items
.venv/bin/alembic upgrade head
.venv/bin/alembic revision -m "description" # then hand-write the ops; autogenerate is not used
.venv/bin/python -m app.seed [--reset]      # ~15-20 min: simulates a year of trading
```

Frontend (`frontend/`):

```bash
npm run dev      # :5173, proxies /api -> localhost:8000
npm run build    # tsc -b && vite build — the only type-check gate
```

There is no linter installed. `[tool.ruff]` is configured in `pyproject.toml`
(line-length 88, py312) but ruff is not a dependency; match the existing style by
hand. The frontend has no test framework — `npm run build` is the whole check.

`.env` is required and the app **fails fast at startup** without a real
`SECRET_KEY` (≥16 chars, not one of the known placeholders). PostgreSQL via
`docker compose up -d database` is the production target; SQLite is the dev
default.

## Architecture

### Backend layering — routes are thin, services own the work

`app/api/routes/*.py` → `app/services/*.py` → `app/models/entities.py`. A route
does exactly four things: declare `Depends(require_role(...))`, call one service
function, call `record_audit(...)`, and map service exceptions to HTTP status
codes. All business logic, all queries, and all transaction control live in the
service. Never put a query or a rule in a route file.

Services raise a small hierarchy of domain errors (e.g. `SaleError` with
`ProductNotFoundError`, `InsufficientStockError`, `CreditLimitExceededError`
subclassing it) and the route translates each to its own status. Follow that
shape rather than raising `HTTPException` from a service.

`process_sale()` / `process_purchase()` commit **once** at the end, so a failure
rolls back the document, its line items, the stock mutation, and the
`InventoryTransaction` rows together. Service functions that can be called from
inside a larger transaction take a `commit: bool = True` parameter (see
`financials.record_customer_payment`) — reuse that pattern instead of committing
mid-flow.

Every stock change must go through an `InventoryTransaction`. `PATCH /products/{id}`
deliberately cannot set `stock_quantity`; that was removed so the ledger can't be
bypassed.

All money and quantities are `Decimal` end to end (`Numeric(14,2)` for money,
`Numeric(14,3)` for quantity). Never let a float into the path.

### The shop's clock, not the server's

`app/core/store_time.py` is mandatory reading before touching any report or daily
figure. Timestamps are stored in UTC, but a "day" means a day on the store's own
clock (`STORE_TIMEZONE`, default `Asia/Tehran`) with a configurable handover hour
(`STORE_DAY_BOUNDARY_HOUR`, for shops trading past midnight). Use `business_day()`
in SQL wherever you'd reach for `func.date(col)`, and `business_day_now()` /
`to_business_day()` in Python instead of `datetime.now(UTC).date()`. `utc_date()`
is only for columns that are genuinely a human-typed calendar date
(`Expense.date`, a cheque's due date). The `business_day` construct sets
`inherit_cache = False` on purpose — do not "optimize" that away.

### Counted vs. weighted products

`Product.is_weighted` decides whether a quantity is a count or a measurement.
It changes three things and nothing else: the POS/edit-form control becomes a
decimal field instead of a +/- stepper (`components/QuantityInput.tsx`), a
repeat scan does *not* increment the line (+1 would mean +1 kg — a guess worth
real money), and the quantity is displayed padded to three decimals with its
unit (`lib/quantity.ts`). `Product.unit` is the free-text label that precision
is shown in; the flag is the behaviour, the label is the wording.

Everything else was already decimal-safe: quantity columns are `Numeric(14,3)`
end to end, prices are per one `unit` for both kinds, margin is computed from
unit prices (so weight never enters it), and loyalty earns on `line_total`
rather than quantity. When adding anything that touches a line quantity, use
`formatQuantity`/`formatQuantityWithUnit` rather than the bare `number()` —
`toLocaleString` drops trailing zeros, so it renders 2.350 and 2.35 identically.

### Two pairs of files that must be edited together

1. `frontend/src/lib/margin.ts` and `backend/app/services/margin.py` — the same
   margin-on-sales formula, ported by hand. One drives the POS/Products/Reports
   UI, the other drives loyalty point eligibility. If one changes, change both.
2. `frontend/src/permissions.ts` and each route file's `require_role(...)` tuple.
   `permissions.ts` is a hand-maintained mirror with a comment naming the backend
   file for each rule; there is no generated contract. The frontend copy is only
   UX (no dead-end clicks) — `require_role` is the actual enforcement, and every
   route has one.

### Frontend

`api.ts` is the single fetch layer: it attaches the bearer token from
`session.ts` and, on any 401, clears the session and dispatches
`marketa:unauthorized`, which `App.tsx` listens for to drop back to `Login.tsx`.
Never fetch outside `api.ts`.

`i18n.tsx` holds both language dictionaries (fa/en, ~1300 lines) *and* the
toman↔rial currency toggle — one toman is ten rial, and the toggle changes only
presentation, never a stored value. Adding UI text means adding a key to both
dictionaries. Layout direction flips with the language. Jalali date handling is
in `utils/jalali.ts` and the shared `JalaliDatePicker` component.

State is plain React hooks and props — no state library, no router (page
switching is state in `App.tsx`).

### Schema and migrations

Alembic owns the schema outright. `Base.metadata.create_all()` is *not* called at
startup; instead `db/migration_check.py` compares the DB revision to the repo head
and logs loudly on drift without blocking. Any model change needs a hand-written
migration in `alembic/versions/` (25 so far, named `YYYYMMDD_NN_description.py`).

All domain models are in the single file `app/models/entities.py`; schemas are
split per domain under `app/schemas/`.

### Tests

`pytest` with a deliberately thin `conftest.py` — it turns SQLite's
`foreign_keys` pragma on for every engine the suite creates (the app has it
on, and without this the tests ran with referential integrity off) and
offers a `db_session` fixture for new tests. Existing tests still build
their own `create_engine("sqlite://")` in-memory database and call
`Base.metadata.create_all(engine)`; `test_migrations.py` is the one that
runs the real Alembic chain instead. Most tests exercise service functions
directly rather than going through HTTP. Financial tests hand-compute the
expected figure (see `test_inflation_rate.py`, `test_returns_accounting.py`) —
match that when adding accounting logic; asserting "it runs" is not a test here.

## Gotchas

- `with_for_update()` is a **no-op on SQLite**, so concurrent overselling is
  possible in dev and only Postgres actually enforces the lock.
- The reverse asymmetry also exists, and it bites in the opposite direction.
  `app/bootstrap.py::create_first_admin` guards itself with a single atomic
  `INSERT ... SELECT ... WHERE NOT EXISTS (SELECT 1 FROM users)` instead of a
  check-then-act. SQLite serializes writers, so there that is a hard
  guarantee — but **on PostgreSQL at READ COMMITTED two concurrent
  transactions can each see an empty table and each insert a differently
  named admin**, since the unique index on `username` only stops identical
  ones. Postgres is the production target, so if you ever move that function
  (or write another "create this only if the table is still empty" guard)
  into an HTTP path, it needs a table-level lock to be correct there.
- There is no auth bypass. `DEV_DISABLE_AUTH` was removed before the first shop
  deployment — don't reintroduce one; seed the users and log in.
- Seeded logins: `admin`/`Admin@123`, `cashier`/`Cashier@123`,
  `manager`/`Manager@123`. Roles are `admin`, `manager`, `cashier`,
  `inventory_manager`, `accountant`; payroll is the one surface where even
  *reading* is admin-only.
- `app/seed.py` drives the real service layer and then back-dates every row
  (including `InventoryTransaction.timestamp`). If you add a table that carries a
  timestamp, back-date it there too or the demo data will claim a year of history
  happened today.
- The shop's Windows package is built by `installer/build.sh` and documented
  in `installer/README.md`. Two things about it constrain backend changes:
  `app/seed.py` is deliberately not in the payload (the build asserts this),
  and the built frontend is served by the API process itself via
  `app/web.py`, whose SPA catch-all must stay the last route registered.
