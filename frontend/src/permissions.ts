/** Single source of truth for role-based UI show/hide — mirrors the real
 * `require_role(...)` sets already enforced on the backend (see each
 * route file's own role tuple). Keep this in sync with the backend by
 * hand; there is no generated contract between the two, so any backend
 * role-set change must be mirrored here too.
 *
 * This is coarse, page/action-level gating only — not a full permission
 * matrix. Hiding an action here is a UX nicety (no dead-end clicks); the
 * backend's own require_role() remains the actual enforcement.
 */

export type Role = "admin" | "cashier" | "manager" | "inventory_manager" | "accountant";

function has(role: string, allowed: readonly Role[]): boolean {
  return (allowed as readonly string[]).includes(role);
}

// sales.py: edit = admin,manager
export const canEditSale = (role: string) => has(role, ["admin", "manager"]);
// sales.py /{id}/cancel: admin,manager — voiding an issued invoice rewrites
// history, so it is gated exactly like editing one.
export const canCancelSale = (role: string) => has(role, ["admin", "manager"]);
// purchases.py: create/edit = admin,inventory_manager,manager
export const canManagePurchases = (role: string) => has(role, ["admin", "inventory_manager", "manager"]);
// products.py: create/update = admin,manager
export const canManageProducts = (role: string) => has(role, ["admin", "manager"]);
// customers.py: update = admin,manager (create is broader, see canRecordPayments)
export const canEditCustomer = (role: string) => has(role, ["admin", "manager"]);
// suppliers.py: create/update = admin,manager (mirrors products)
export const canManageSuppliers = (role: string) => has(role, ["admin", "manager"]);
// categories.py: create = admin,manager
export const canManageCategories = (role: string) => has(role, ["admin", "manager"]);
// customers.py/suppliers.py payments: admin,cashier,manager,accountant
export const canRecordPayments = (role: string) => has(role, ["admin", "cashier", "manager", "accountant"]);
// sales.py: allow_credit_override past a customer's credit_limit = admin,manager
export const canOverrideCreditLimit = (role: string) => has(role, ["admin", "manager"]);
// adjustments.py stock/purchase-return: admin,inventory_manager
// adjustments.py /stock: admin,manager,inventory_manager — a manual stock
// movement is a financial event (it changes what the shelf is worth), so it
// sits with the roles that may edit an invoice, plus the one whose whole job
// is the stockroom.
export const canAdjustStock = (role: string) => has(role, ["admin", "manager", "inventory_manager"]);
// checks.py READ_ROLES: admin,inventory_manager,manager,accountant (no cashier)
export const canViewChecks = (role: string) => has(role, ["admin", "inventory_manager", "manager", "accountant"]);
// checks.py WRITE_ROLES: admin,inventory_manager,manager (no cashier)
export const canManageChecks = (role: string) => has(role, ["admin", "inventory_manager", "manager"]);
// reports.py READ_ROLES: admin,manager,inventory_manager,accountant (no cashier)
export const canViewReports = (role: string) => has(role, ["admin", "manager", "inventory_manager", "accountant"]);
// inventory.py READ_ROLES: admin,manager,inventory_manager,accountant (no cashier)
export const canViewInventoryHistory = (role: string) => has(role, ["admin", "manager", "inventory_manager", "accountant"]);
// users.py: admin-only (Part 5)
export const canManageUsers = (role: string) => has(role, ["admin"]);
// customers.py /loyalty/adjust: admin,manager (most sensitive loyalty action)
export const canAdjustLoyaltyPoints = (role: string) => has(role, ["admin", "manager"]);
// expenses.py EXPENSE_ROLES: admin,manager (general expenses + net-profit)
export const canManageExpenses = (role: string) => has(role, ["admin", "manager"]);
// expenses.py SALARY_ROLES: admin ONLY — even viewing payroll must be
// restricted, not just editing (see docs/expense-management.md). Callers
// must use this to omit the "حقوق و دستمزد" tab from the DOM entirely for
// non-admins, not just hide it with CSS.
export const canViewSalaries = (role: string) => has(role, ["admin"]);
