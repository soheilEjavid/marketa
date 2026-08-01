# MARKETA

MARKETA is a modular store-management platform for products, sales, purchasing,
inventory, customer credit, supplier debt, and operational reporting.

## Current foundation

- FastAPI backend with versioned REST endpoints
- SQLAlchemy domain model covering the core store workflows
- Product CRUD API with soft deletion and barcode conflict handling
- Transactional sales and purchasing with atomic stock updates
- Inventory transaction ledger for sales, purchases, and adjustments
- SQLite development default with PostgreSQL-ready configuration
- Alembic migration setup
- React and TypeScript dashboard, POS, purchasing, and inventory history
- English/Persian localization with automatic LTR/RTL layout
- Responsive store-management interface
- Focused backend tests

## Project structure

```text
marketa/
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   └── tests/
├── frontend/
│   └── src/
└── compose.yaml
```

## Run the backend

```bash
cd /home/tsik/marketa/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Then generate a real `SECRET_KEY` and put it in `.env` — the app refuses to
start with the placeholder value or with none set at all:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

```bash
uvicorn app.main:app --reload
```

### Authentication

The app requires a real login. Seed the demo users first:

```bash
cd /home/tsik/marketa/backend
python -m app.seed
```

Then sign in through the frontend with one of the seeded accounts
(`admin` / `Admin@123`, `cashier` / `Cashier@123`, `manager` /
`Manager@123`). There is a `DEV_DISABLE_AUTH` env var that bypasses login
entirely for local debugging, but it is **not** part of this normal setup —
leave it `false` (the default) unless you specifically need it.

The API runs at `http://localhost:8000`; interactive documentation is available
at `http://localhost:8000/docs`.

SQLite is used automatically for a quick local start. To use PostgreSQL, start
the database and change `DATABASE_URL`:

```bash
cd /home/tsik/marketa
docker compose up -d database
```

```env
DATABASE_URL=postgresql+psycopg://marketa:marketa@localhost:5432/marketa
```

For schema migrations:

```bash
cd /home/tsik/marketa/backend
alembic upgrade head
```

Phase 2 exposes:

```text
POST /api/v1/sales
POST /api/v1/purchases
GET  /api/v1/inventory/transactions
```

Sales and purchases are committed as one database transaction. A failed sale
rolls back its document, line items, stock changes, and inventory transactions.

## Run the frontend

Use Node.js 20 or newer:

```bash
cd /home/tsik/marketa/frontend
npm install
npm run dev
```

The web application runs at `http://localhost:5173` and proxies `/api` requests
to the backend.

## Test

```bash
cd /home/tsik/marketa/backend
pytest
```

## Current status and next gaps

The project is well past its early phases now — real authentication/RBAC,
customer/supplier management with payments and ledgers, the customer loyalty
program, dual pricing, checks, and consignment tracking are all built. For an
up-to-date, evidence-based picture of what's done and what's still missing
(tax support, expense tracking, multi-warehouse, weighted goods, and more),
see `docs/MARKETA_FEATURE_AUDIT.md`. The earlier `docs/phase-3-technical-blueprint.md`
plan has been completed and is archived at `docs/archive/phase-3-technical-blueprint.md`
for historical reference only.

Apply the latest migration with:

```bash
cd /home/tsik/marketa/backend
alembic upgrade head
```
