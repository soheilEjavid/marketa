# MARKETA Phase 3 Technical Blueprint

## Current State Assessment

MARKETA currently provides a compact Phase 1/2 foundation:

- FastAPI, SQLAlchemy 2, Alembic, and a SQLite development default with
  PostgreSQL configuration available.
- Product CRUD with barcode validation, soft deactivation, stock quantity, and
  low-stock thresholds.
- Transactional sale and purchase creation with line items, atomic inventory
  changes, invoice uniqueness, and rollback on failure.
- Inventory transaction history for sale, purchase, and adjustment types.
- Preliminary `Customer`, `Supplier`, `User`, and generic `Payment` tables exist,
  but they have no API, service, frontend, authentication, ledger, or posting
  workflow.
- Sales and purchases already have nullable customer/supplier foreign keys, but
  relations are not validated or exposed as useful nested response data.
- The frontend has a Persian/English RTL-aware shell, POS, purchasing, inventory
  history, and a dashboard. Dashboard financial figures and charts are static.
- Tests cover health, products, transactional sales/purchases, stock mutation,
  and rollback behavior.

The current codebase is intentionally small. Phase 3 should preserve its
service-oriented route/schema/model structure while splitting new business
domains into focused modules.

## Target Domain Model

### Party Management

- Extend `Customer` with `full_name`, `national_id`, `is_active`, and retained
  timestamps. Keep `balance` as a cached operational balance, reconciled against
  documents and payments.
- Extend `Supplier` with `contact_person` and `is_active`. Keep `balance` as a
  cached payable balance.
- Add indexes for customer national ID and active/search fields where useful.

### Financial Documents

- Keep existing `Sale.total` and `Purchase.total` database columns initially to
  minimize disruption; expose them as `total_amount` aliases only if a later API
  version requires strict naming.
- Add `remaining_amount` and `payment_status` to both documents.
- Treat the existing sale `payment_method` as `payment_type`; add the equivalent
  field to purchases.
- Replace the ambiguous generic payment workflow with explicit
  `CustomerPayment` and `SupplierPayment` models. A compatibility migration can
  transform existing generic payment rows before the old table is removed.
- Enforce positive payment values, party/document ownership, document balance
  limits, and atomic updates to document and party balances.

### Inventory Operations

- Extend inventory transaction types with `sale_return`, `purchase_return`, and
  `waste`.
- Add `reason`, `notes`, `user_id`, and optional document references to inventory
  transactions.
- Add return header/line models when return documents need independent lifecycle
  and reporting. Initial endpoints may post validated return transactions
  atomically while preserving source sale/purchase references.

### Authorization and Audit

- Keep role names on `User`, but centralize a role-to-permission map in the
  authorization service.
- Add JWT login/current-user dependencies and password hashing.
- Add `AuditLog` with JSON changes, actor, entity type/id, action, and timestamp.
- Record audit entries inside the same database transaction as the business
  operation.

## API Plan

### Customers

- `GET /customers`: search, active filter, offset, limit.
- `POST /customers`: create with phone/national-ID validation.
- `GET /customers/{id}`: party details and current balance.
- `PATCH /customers/{id}`: partial update/deactivation.
- `POST /customers/{id}/payments`: record an allocated or unallocated receipt.
- `GET /customers/{id}/ledger`: chronological invoices, payments, running balance.

### Suppliers

- `GET /suppliers`: search, active filter, offset, limit.
- `POST /suppliers`: create.
- `GET /suppliers/{id}`: details and current payable balance.
- `PATCH /suppliers/{id}`: partial update/deactivation.
- `POST /suppliers/{id}/payments`: record an allocated or unallocated payment.
- `GET /suppliers/{id}/ledger`: purchases, payments, running balance.

### Documents

- Add sale/purchase list and detail endpoints.
- Validate selected customer/supplier during document creation.
- Return nested party summaries and computed payment fields.
- Post initial paid amounts through the explicit payment service so all balance
  and audit behavior follows one path.

### Inventory

- `POST /inventory/adjustments`
- `POST /inventory/sales-returns`
- `POST /inventory/purchase-returns`
- `POST /inventory/waste`
- Extend `GET /inventory/transactions` with date, reason, party, document, and
  transaction-type filters.

### Reports and Dashboard

- `GET /reports/sales-summary`
- `GET /reports/purchase-summary`
- `GET /reports/inventory-summary`
- `GET /reports/low-stock`
- `GET /reports/customer-balances`
- `GET /reports/supplier-balances`
- `GET /reports/top-products`
- `GET /dashboard/summary`

Report queries should aggregate in SQL, accept explicit date boundaries, exclude
cancelled documents, and return both totals and display-ready series. Approximate
gross margin uses stored `SaleItem.cost_price`, which preserves historical cost.

## Frontend Plan

- Add customers and suppliers navigation, searchable tables, create/edit forms,
  active-state controls, and detail/ledger views.
- Add customer/supplier selectors and paid-amount inputs to sale/purchase forms.
- Add receipt/payment dialogs from party ledger screens.
- Replace dashboard placeholders with `/dashboard/summary`.
- Add reports navigation with date filters, cards, and tables; charts remain
  optional.
- Add inventory operation forms for adjustment, waste, sales return, and
  purchase return.
- Add authentication state and permission-aware route/action rendering.
- Reuse existing panels, fields, feedback banners, localization context, and RTL
  layout conventions. Every screen must include loading, error, and empty states.

## Migration Plan

1. Extend customer/supplier fields without dropping operational data. Rename
   `customers.name` to `full_name`, then add nullable/defaulted columns before
   tightening constraints.
2. Add document payment status fields and explicit payment tables. Backfill
   remaining amounts and party balances from completed documents and payments.
3. Extend inventory enum/types and add reason/audit columns. PostgreSQL enum
   changes require explicit enum value migration; SQLite uses batch operations.
4. Add audit logs and authentication-supporting user constraints.
5. Remove or archive the generic `payments` table only after its data is migrated.

Production deployments should run Alembic only. `Base.metadata.create_all` should
eventually be limited to tests/local bootstrap so schema drift cannot bypass
migrations.

## Seed and Demo Strategy

- Add `python -m app.seed --reset` and `python -m app.seed` idempotent workflows.
- Use deterministic scenario fixtures rather than unconstrained random values.
- Seed five role-specific users with documented development-only passwords.
- Seed Persian supermarket categories and 80+ recognizable products with
  coherent price bands, thresholds, and intentionally varied stock.
- Build 20+ customers and 8+ suppliers, then create documents through domain
  services so inventory, balances, payments, and audit logs remain consistent.
- Create 20–30 purchases followed by 50–70 sales across a fixed rolling date
  window, with paid, partial, and unpaid scenarios.
- Add representative receipts, supplier payments, returns, waste, and stock
  corrections. Ensure low-stock items, receivables, payables, and gross margin
  are visible on first load.
- Keep the reset option environment-gated and reject it outside development/test.

## Implementation Order

1. Customer and supplier schema/API/UI.
2. Party validation and nested relations on sales/purchases.
3. Explicit payment models, payment statuses, cached balances, and ledgers.
4. SQL-backed reports and live dashboard.
5. Adjustments, waste, and return workflows.
6. JWT authentication and centralized role/permission enforcement.
7. Transactional audit logging.
8. Deterministic reset/reseed command and demo documentation.
9. Cross-domain tests, frontend build, migration verification, and PostgreSQL run.

## Risks and Assumptions

- Existing development databases may have been created by `create_all` rather
  than Alembic. Migrations must tolerate the documented migration history, while
  legacy local databases may require backup/reseed.
- Cached party balances can drift if mutations bypass services. All Phase 3
  document/payment operations must use domain services, plus reconciliation tests.
- SQLite and PostgreSQL differ in enum and locking behavior. Critical payment and
  stock workflows require PostgreSQL verification before production.
- Current API has no authentication. Permission enforcement must be introduced
  with a deliberate bootstrap/admin path to avoid locking out existing installs.
- Currency is currently formatted as toman in Persian and USD in English while
  stored values are currency-neutral. A store-level currency setting is a later
  configuration concern.

## Acceptance Criteria

- Customers and suppliers support searchable create/read/update/deactivate flows
  in API and RTL/LTR UI.
- Sales and purchases validate and expose their selected party.
- Partial/full payments atomically update document status and party balances.
- Customer and supplier ledgers reconcile to displayed balances.
- Dashboard and reports use live seeded data and exclude cancelled documents.
- Adjustments, returns, and waste update stock and create traceable transactions.
- Backend permissions reject unauthorized operations and frontend actions follow
  the same permission map.
- Important business operations create audit entries in the same transaction.
- Deterministic demo seeding produces the required users, 80+ products, parties,
  invoices, payments, inventory exceptions, and useful report output.
- Backend tests, frontend build, Alembic upgrade, and a PostgreSQL smoke test pass.
