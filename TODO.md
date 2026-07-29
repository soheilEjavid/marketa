# Dual-Price Product Support Implementation

## Backend

- [x] 1. Database migration — add dual-price columns to products table
- [x] 2. Product model — add new fields to Product entity
- [x] 3. Product schemas — update ProductRead, ProductUpdate with dual-price fields
- [x] 4. Sale schemas — add price_tier to SaleItemCreate / SaleItemRead
- [x] 5. Purchase schemas — add confirm_dual_pricing, dual_pricing_config
- [x] 6. Product service — add enable_dual_pricing(), collapse_dual_pricing(), decrement_old_stock_estimate()
- [x] 7. Purchase service — detect price change with existing stock, prompt for dual-pricing
- [x] 8. Sale service — handle price_tier in process_sale(), use correct cost basis
- [x] 9. Product API routes — add collapse endpoint
- [x] 10. Purchase API routes — handle DualPriceRequiredError
- [x] 11. Sale API routes — pass price_tier through

## Frontend

- [x] 12. Types — finalize PurchaseCreate dual-price fields
- [x] 13. API — add updateProduct(), pass price_tier in createSale
- [x] 14. i18n — add dual-price string keys
- [x] 15. Styles — CSS for price toggle, badges, collapse UI
- [x] 16. Purchases page — dual-price confirmation modal
- [x] 17. Sales page — price-tier toggle for dual-priced products
- [x] 18. Products page — dual-price badge, old-stock estimate, collapse button

# Auth wiring — RESOLVED

Real login is now fully wired end-to-end (see the "Real Authentication +
Role-Based Access" task). `Login.tsx` posts a JSON body matching the real
`/auth/login` contract and is rendered by `App.tsx` behind a real auth gate
(no stored/valid session → login screen, before anything else renders).
`frontend/src/session.ts` stores `{token, userId, username, fullName, role}`
in `localStorage`; `api.ts`'s shared `rawFetch()` attaches
`Authorization: Bearer <token>` to every request and, on any `401`, clears
the session and fires a global event that `App.tsx` listens for to drop
back to the login screen — handled in that one place, not per-page.
Role-based UI show/hide lives in `frontend/src/permissions.ts`, mirroring
the backend's real `require_role(...)` sets. Minimal admin-only user
management (`GET/POST /api/v1/users`, activate/deactivate) was added.
Password hashing moved from unsalted SHA256 to bcrypt; `SECRET_KEY` now has
no default and the app fails fast at startup if it's unset or the known
placeholder value. Every previously-open route (`suppliers.py`,
`categories.py`, `inventory.py`, `reports.py`, `dashboard.py`, and gaps
found in `products.py`) now has `require_role(...)`.

`DEV_DISABLE_AUTH` (default `false`) is kept **on purpose** as an opt-in
local-dev escape hatch — it is not part of the normal/documented run
process (the README's "Run the backend" section never mentions it, and
`.env.example` ships it as `false` with a loud comment). It only bypasses
`get_current_user`, never `require_role`, `decode_access_token`, or any
other real auth logic.

- [x] 19. Fix `Login.tsx` to match the real `/auth/login` contract (JSON body, `token` field) and actually render it from `App.tsx` behind an auth gate
- [x] 20. Store the token (e.g. localStorage) and attach `Authorization: Bearer <token>` in `frontend/src/api.ts`'s `request()`
- [x] 21. Handle 401 responses globally (e.g. redirect to login) once the above exists
- [x] 22. Decision: keep `DEV_DISABLE_AUTH` as an explicit, non-default, non-documented opt-in escape hatch rather than deleting it — real login is now the actual gatekeeper for normal use

