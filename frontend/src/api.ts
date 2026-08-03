import type {
  AuditLogEntry,
  BirthdayCustomerRow,
  CashierPerformanceRow,
  CashierShift,
  Category,
  CategoryInput,
  CategoryUpdateInput,
  ChurnCouponIssueResult,
  ChurnRiskCustomerRow,
  CheckRead,
  CheckStatus,
  CheckSummary,
  Customer,
  CustomerInput,
  CustomerLedger,
  CustomerTierRow,
  DailySalesPoint,
  DashboardSummary,
  Expense,
  ExpenseInput,
  ExpensePaymentMethod,
  InflationRateReport,
  InventoryTransaction,
  InventoryTransactionType,
  LoyaltyBalance,
  LoyaltyLiabilityRow,
  LoyaltyRedemptionRow,
  LoyaltyRewardCatalogRow,
  LoyaltyRewardSuggestion,
  LoyaltySettings,
  LoyaltyTransaction,
  NearExpiryRow,
  NetProfitReport,
  SalaryAdvance,
  SalaryPayment,
  PaymentMethodBreakdownRow,
  Product,
  ProductInput,
  ProductUpdate,
  Purchase,
  PurchaseCreate,
  PurchaseEditRequest,
  PurchaseItemRead,
  Sale,
  SaleCreate,
  SaleEditRequest,
  Supplier,
  SupplierInput,
  SupplierLedger,
  TopProductRow,
  UserCreate,
  UserSummary,
} from "./types";
import { getSession, notifyUnauthorized } from "./session";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "/api/v1";

export type LoginResult = {
  token: string;
  userId: number;
  username: string;
  fullName: string;
  role: string;
};

/** Deliberately bypasses rawFetch(): there's no session yet to attach a
 * header from, and a 401 here means "wrong credentials" — a normal login
 * failure the caller should show inline, not a session-expiry event that
 * should bounce the whole app back to the login screen it's already on. */
export async function login(username: string, password: string): Promise<LoginResult> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    throw new ApiError("Network request failed");
  }
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(typeof error?.detail === "string" ? error.detail : "Login failed", {
      status: response.status,
    });
  }
  const data = (await response.json()) as {
    token: string;
    user_id: number;
    username: string;
    full_name: string;
    role: string;
  };
  return { token: data.token, userId: data.user_id, username: data.username, fullName: data.full_name, role: data.role };
}

export async function getCurrentUser(): Promise<UserSummary> {
  return request<UserSummary>(`${apiBaseUrl}/auth/me`);
}

export type GetProductsParams = {
  search?: string;
  categoryId?: number | null;
  activeOnly?: boolean;
};

export async function getProducts(params: GetProductsParams = {}): Promise<Product[]> {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.categoryId) query.set("category_id", String(params.categoryId));
  if (params.activeOnly === false) query.set("active_only", "false");
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<Product[]>(`${apiBaseUrl}/products${suffix}`);
}

export async function createProduct(data: ProductInput): Promise<Product> {
  return request<Product>(`${apiBaseUrl}/products`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateProduct(
  productId: number,
  data: ProductUpdate,
): Promise<Product> {
  return request<Product>(`${apiBaseUrl}/products/${productId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

/** Soft-deletes a product (sets is_active=false); history is preserved. */
export async function deactivateProduct(productId: number): Promise<Product> {
  return request<Product>(`${apiBaseUrl}/products/${productId}`, {
    method: "DELETE",
  });
}

export async function getCategories(search = ""): Promise<Category[]> {
  const query = search ? `?search=${encodeURIComponent(search)}` : "";
  return request<Category[]>(`${apiBaseUrl}/categories${query}`);
}

export async function createCategory(data: CategoryInput): Promise<Category> {
  return request<Category>(`${apiBaseUrl}/categories`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateCategory(categoryId: number, data: CategoryUpdateInput): Promise<Category> {
  return request<Category>(`${apiBaseUrl}/categories/${categoryId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export type GetAuditLogsParams = {
  entityType?: string;
  entityId?: number;
  action?: string;
  limit?: number;
};

export async function getAuditLogs(params: GetAuditLogsParams = {}): Promise<AuditLogEntry[]> {
  const query = new URLSearchParams();
  if (params.entityType) query.set("entity_type", params.entityType);
  if (params.entityId !== undefined) query.set("entity_id", String(params.entityId));
  if (params.action) query.set("action", params.action);
  if (params.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AuditLogEntry[]>(`${apiBaseUrl}/audit/logs${suffix}`);
}

export type DualPriceRequiredResponse = {
  code: "dual_price_required";
  message: string;
  products: Array<{
    product_id: number;
    product_name: string;
    current_purchase_price: number;
    current_sale_price: number;
    new_purchase_price: number;
    suggested_new_sale_price: number;
    current_stock: number;
    is_update_existing_dual?: boolean;
    /** Which field(s) on this purchase line actually differ from the stored product. */
    purchase_price_changed?: boolean;
    sale_price_changed?: boolean;
  }>;
};

export type CreditLimitExceededResponse = {
  code: "credit_limit_exceeded";
  message: string;
  current_balance: string;
  credit_limit: string;
  credit_portion: string;
};

/** Error thrown by `request()`. Carries the structured dual-price-required
 * payload (code + products) when the API responds with that specific 409,
 * plus the raw HTTP status so callers can distinguish "no permission"
 * (403) or "session expired" (401, already handled globally) from a
 * genuine network failure (status is undefined — fetch() itself threw). */
export class ApiError extends Error {
  code?: string;
  status?: number;
  products?: DualPriceRequiredResponse["products"];
  creditInfo?: {
    currentBalance: number;
    creditLimit: number;
    creditPortion: number;
  };

  constructor(
    message: string,
    extra?: {
      code?: string;
      status?: number;
      products?: DualPriceRequiredResponse["products"];
      creditInfo?: ApiError["creditInfo"];
    },
  ) {
    super(message);
    this.name = "ApiError";
    this.code = extra?.code;
    this.status = extra?.status;
    this.products = extra?.products;
    this.creditInfo = extra?.creditInfo;
  }
}

/** Shared error-message resolver for catch blocks throughout the app: a
 * 403 always means "wrong role, not a real problem" and gets the same
 * friendly Persian/English message everywhere, rather than the raw
 * backend detail string (which is written for developers, not cashiers). */
export function getErrorMessage(error: unknown, t: (key: string) => string): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return t("noPermission");
    if (error.status === undefined) return t("apiError");
  }
  return error instanceof Error ? error.message : t("apiError");
}

export async function getCustomers(search = ""): Promise<Customer[]> {
  const query = search ? `?search=${encodeURIComponent(search)}` : "";
  return request<Customer[]>(`${apiBaseUrl}/customers${query}`);
}

export async function createCustomer(data: CustomerInput): Promise<Customer> {
  return request<Customer>(`${apiBaseUrl}/customers`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateCustomer(
  customerId: number,
  data: Partial<CustomerInput>,
): Promise<Customer> {
  return request<Customer>(`${apiBaseUrl}/customers/${customerId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function getCustomerLedger(customerId: number): Promise<CustomerLedger> {
  return request<CustomerLedger>(`${apiBaseUrl}/customers/${customerId}/ledger`);
}

/** Records an unallocated payment against the customer's overall balance
 * (no document_id) — settles down whatever they currently owe rather than
 * paying off one specific invoice. */
export async function createCustomerPayment(
  customerId: number,
  data: { amount: number; method: "cash" | "card" },
): Promise<void> {
  await request<unknown>(`${apiBaseUrl}/customers/${customerId}/payments`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getLoyaltyBalance(customerId: number, saleTotal?: number): Promise<LoyaltyBalance> {
  const query = saleTotal !== undefined ? `?sale_total=${saleTotal}` : "";
  return request<LoyaltyBalance>(`${apiBaseUrl}/customers/${customerId}/loyalty${query}`);
}

export async function getLoyaltyTransactions(customerId: number): Promise<LoyaltyTransaction[]> {
  return request<LoyaltyTransaction[]>(`${apiBaseUrl}/customers/${customerId}/loyalty/transactions`);
}

export async function adjustLoyaltyPoints(customerId: number, delta: number, reason: string): Promise<LoyaltyBalance> {
  return request<LoyaltyBalance>(`${apiBaseUrl}/customers/${customerId}/loyalty/adjust`, {
    method: "POST",
    body: JSON.stringify({ delta, reason }),
  });
}

export async function getLoyaltyLiability(): Promise<LoyaltyLiabilityRow[]> {
  return request<LoyaltyLiabilityRow[]>(`${apiBaseUrl}/reports/loyalty-liability`);
}

export async function getUpcomingBirthdays(withinDays = 30): Promise<BirthdayCustomerRow[]> {
  return request<BirthdayCustomerRow[]>(`${apiBaseUrl}/reports/upcoming-birthdays?within_days=${withinDays}`);
}

export async function getChurnRiskCustomers(): Promise<ChurnRiskCustomerRow[]> {
  return request<ChurnRiskCustomerRow[]>(`${apiBaseUrl}/reports/churn-risk`);
}

export async function getLoyaltySettings(): Promise<LoyaltySettings> {
  return request<LoyaltySettings>(`${apiBaseUrl}/loyalty/settings`);
}

export async function updateLoyaltySettings(data: LoyaltySettings): Promise<LoyaltySettings> {
  return request<LoyaltySettings>(`${apiBaseUrl}/loyalty/settings`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function getRewardCatalog(search = ""): Promise<LoyaltyRewardCatalogRow[]> {
  const query = search ? `?search=${encodeURIComponent(search)}` : "";
  return request<LoyaltyRewardCatalogRow[]>(`${apiBaseUrl}/loyalty/reward-catalog${query}`);
}

export async function getLoyaltyRedemptions(): Promise<LoyaltyRedemptionRow[]> {
  return request<LoyaltyRedemptionRow[]>(`${apiBaseUrl}/reports/loyalty-redemptions`);
}

export async function getLoyaltyRewardSuggestions(customerId: number): Promise<LoyaltyRewardSuggestion[]> {
  return request<LoyaltyRewardSuggestion[]>(`${apiBaseUrl}/customers/${customerId}/loyalty/reward-suggestions`);
}

export async function getCustomerTiers(): Promise<CustomerTierRow[]> {
  return request<CustomerTierRow[]>(`${apiBaseUrl}/reports/customer-tiers`);
}

export async function issueChurnRecoveryCoupons(): Promise<ChurnCouponIssueResult[]> {
  return request<ChurnCouponIssueResult[]>(`${apiBaseUrl}/reports/churn-risk/issue-coupons`, {
    method: "POST",
  });
}

export async function getSuppliers(search = ""): Promise<Supplier[]> {
  const query = search ? `?search=${encodeURIComponent(search)}` : "";
  return request<Supplier[]>(`${apiBaseUrl}/suppliers${query}`);
}

export async function createSupplier(data: SupplierInput): Promise<Supplier> {
  return request<Supplier>(`${apiBaseUrl}/suppliers`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateSupplier(
  supplierId: number,
  data: Partial<SupplierInput>,
): Promise<Supplier> {
  return request<Supplier>(`${apiBaseUrl}/suppliers/${supplierId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function getSupplierLedger(supplierId: number): Promise<SupplierLedger> {
  return request<SupplierLedger>(`${apiBaseUrl}/suppliers/${supplierId}/ledger`);
}

/** Records an unallocated payment against the supplier's overall balance
 * (no document_id) — same shape as createCustomerPayment. */
export async function createSupplierPayment(
  supplierId: number,
  data: { amount: number; method: "cash" | "card" },
): Promise<void> {
  await request<unknown>(`${apiBaseUrl}/suppliers/${supplierId}/payments`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function createSale(data: SaleCreate): Promise<Sale> {
  return request<Sale>(`${apiBaseUrl}/sales`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getSales(): Promise<Sale[]> {
  return request<Sale[]>(`${apiBaseUrl}/sales`);
}

export async function getSale(saleId: number): Promise<Sale> {
  return request<Sale>(`${apiBaseUrl}/sales/${saleId}`);
}

export async function editSale(saleId: number, data: SaleEditRequest): Promise<Sale> {
  return request<Sale>(`${apiBaseUrl}/sales/${saleId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function holdSale(data: SaleCreate): Promise<Sale> {
  return request<Sale>(`${apiBaseUrl}/sales/hold`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getHeldSales(): Promise<Sale[]> {
  return request<Sale[]>(`${apiBaseUrl}/sales/held`);
}

export async function resumeSale(saleId: number): Promise<Sale> {
  return request<Sale>(`${apiBaseUrl}/sales/${saleId}/resume`, { method: "POST" });
}

export async function discardSale(saleId: number): Promise<Sale> {
  return request<Sale>(`${apiBaseUrl}/sales/${saleId}/discard`, { method: "POST" });
}

export async function getUsers(activeOnly = true): Promise<UserSummary[]> {
  const query = activeOnly ? "" : "?active_only=false";
  return request<UserSummary[]>(`${apiBaseUrl}/users${query}`);
}

export async function createUser(data: UserCreate): Promise<UserSummary> {
  return request<UserSummary>(`${apiBaseUrl}/users`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function setUserActive(userId: number, isActive: boolean): Promise<UserSummary> {
  return request<UserSummary>(`${apiBaseUrl}/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive }),
  });
}

export async function getCurrentShift(): Promise<CashierShift | null> {
  return request<CashierShift | null>(`${apiBaseUrl}/shifts/current`);
}

export async function openShift(cashierId: number, openingCash: number): Promise<CashierShift> {
  return request<CashierShift>(`${apiBaseUrl}/shifts/open`, {
    method: "POST",
    body: JSON.stringify({ cashier_id: cashierId, opening_cash: openingCash }),
  });
}

export async function closeShift(shiftId: number, closingCash: number, notes?: string): Promise<CashierShift> {
  return request<CashierShift>(`${apiBaseUrl}/shifts/${shiftId}/close`, {
    method: "POST",
    body: JSON.stringify({ closing_cash: closingCash, ...(notes ? { notes } : {}) }),
  });
}

export async function getShifts(): Promise<CashierShift[]> {
  return request<CashierShift[]>(`${apiBaseUrl}/shifts`);
}

export async function getCashierPerformance(params: { fromDate?: string; toDate?: string } = {}): Promise<CashierPerformanceRow[]> {
  const query = new URLSearchParams();
  if (params.fromDate) query.set("from_date", params.fromDate);
  if (params.toDate) query.set("to_date", params.toDate);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<CashierPerformanceRow[]>(`${apiBaseUrl}/reports/cashier-performance${suffix}`);
}

export async function createPurchase(data: PurchaseCreate): Promise<Purchase> {
  return request<Purchase>(`${apiBaseUrl}/purchases`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getPurchases(): Promise<Purchase[]> {
  return request<Purchase[]>(`${apiBaseUrl}/purchases`);
}

export async function getPurchase(purchaseId: number): Promise<Purchase> {
  return request<Purchase>(`${apiBaseUrl}/purchases/${purchaseId}`);
}

export async function editPurchase(purchaseId: number, data: PurchaseEditRequest): Promise<Purchase> {
  return request<Purchase>(`${apiBaseUrl}/purchases/${purchaseId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export type PagedResult<T> = { items: T[]; total: number };
export type InvoiceListParams = {
  search?: string;
  sort?: "date_desc" | "date_asc";
  offset?: number;
  limit?: number;
};

async function requestPaged<T>(url: string, params: InvoiceListParams): Promise<PagedResult<T>> {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.sort) query.set("sort", params.sort);
  if (params.offset) query.set("offset", String(params.offset));
  if (params.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const response = await rawFetch(`${url}${suffix}`);
  const items = (await response.json()) as T[];
  const totalHeader = response.headers.get("X-Total-Count");
  return { items, total: totalHeader ? Number(totalHeader) : items.length };
}

export async function getSalesPage(params: InvoiceListParams = {}): Promise<PagedResult<Sale>> {
  return requestPaged<Sale>(`${apiBaseUrl}/sales`, params);
}

export async function getPurchasesPage(params: InvoiceListParams = {}): Promise<PagedResult<Purchase>> {
  return requestPaged<Purchase>(`${apiBaseUrl}/purchases`, params);
}

export async function getInventoryTransactions(
  type?: InventoryTransactionType,
): Promise<InventoryTransaction[]> {
  const query = type ? `?transaction_type=${type}` : "";
  return request<InventoryTransaction[]>(
    `${apiBaseUrl}/inventory/transactions${query}`,
  );
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>(`${apiBaseUrl}/dashboard/summary`);
}

export type DateRangeParams = { fromDate?: string; toDate?: string };

export async function getDailySales(params: DateRangeParams = {}): Promise<DailySalesPoint[]> {
  const query = new URLSearchParams();
  if (params.fromDate) query.set("from_date", params.fromDate);
  if (params.toDate) query.set("to_date", params.toDate);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<DailySalesPoint[]>(`${apiBaseUrl}/reports/daily-sales${suffix}`);
}

export async function getTopProducts(params: {
  sortBy?: "quantity" | "profit" | "revenue";
  limit?: number;
} = {}): Promise<TopProductRow[]> {
  const query = new URLSearchParams();
  if (params.sortBy) query.set("sort_by", params.sortBy);
  if (params.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<TopProductRow[]>(`${apiBaseUrl}/reports/top-products${suffix}`);
}

export async function getNearExpiryProducts(params: {
  redDays?: number;
  orangeDays?: number;
} = {}): Promise<NearExpiryRow[]> {
  const query = new URLSearchParams();
  if (params.redDays) query.set("red_days", String(params.redDays));
  if (params.orangeDays) query.set("orange_days", String(params.orangeDays));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<NearExpiryRow[]>(`${apiBaseUrl}/reports/near-expiry${suffix}`);
}

export async function getInflationRate(params: {
  period1Start: string;
  period1End: string;
  period2Start: string;
  period2End: string;
}): Promise<InflationRateReport> {
  const query = new URLSearchParams({
    period1_start: params.period1Start,
    period1_end: params.period1End,
    period2_start: params.period2Start,
    period2_end: params.period2End,
  });
  return request<InflationRateReport>(`${apiBaseUrl}/reports/inflation-rate?${query.toString()}`);
}

export async function getExpenses(params: { fromDate?: string; toDate?: string } = {}): Promise<Expense[]> {
  const query = new URLSearchParams();
  if (params.fromDate) query.set("from_date", params.fromDate);
  if (params.toDate) query.set("to_date", params.toDate);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<Expense[]>(`${apiBaseUrl}/expenses${suffix}`);
}

export async function getExpenseCategories(): Promise<string[]> {
  return request<string[]>(`${apiBaseUrl}/expenses/categories`);
}

export async function createExpense(data: ExpenseInput): Promise<Expense> {
  return request<Expense>(`${apiBaseUrl}/expenses`, { method: "POST", body: JSON.stringify(data) });
}

export async function updateExpense(expenseId: number, data: Partial<ExpenseInput>): Promise<Expense> {
  return request<Expense>(`${apiBaseUrl}/expenses/${expenseId}`, { method: "PATCH", body: JSON.stringify(data) });
}

export async function getSalaryAdvances(params: { employeeId?: number } = {}): Promise<SalaryAdvance[]> {
  const query = params.employeeId ? `?employee_id=${params.employeeId}` : "";
  return request<SalaryAdvance[]>(`${apiBaseUrl}/salary-advances${query}`);
}

export async function createSalaryAdvance(data: {
  employee_id: number;
  amount: number;
  date: string;
  notes?: string | null;
}): Promise<SalaryAdvance> {
  return request<SalaryAdvance>(`${apiBaseUrl}/salary-advances`, { method: "POST", body: JSON.stringify(data) });
}

export async function getSalaryPayments(params: { employeeId?: number } = {}): Promise<SalaryPayment[]> {
  const query = params.employeeId ? `?employee_id=${params.employeeId}` : "";
  return request<SalaryPayment[]>(`${apiBaseUrl}/salary-payments${query}`);
}

export async function createSalaryPayment(data: {
  employee_id: number;
  period_year: number;
  period_month: number;
  base_amount: number;
  bonus_amount?: number;
  other_deductions_amount?: number;
  payment_method: ExpensePaymentMethod;
  notes?: string | null;
}): Promise<SalaryPayment> {
  return request<SalaryPayment>(`${apiBaseUrl}/salary-payments`, { method: "POST", body: JSON.stringify(data) });
}

export async function updateSalaryPayment(
  paymentId: number,
  data: Partial<{
    base_amount: number;
    bonus_amount: number;
    other_deductions_amount: number;
    payment_method: ExpensePaymentMethod;
    notes: string | null;
  }>,
): Promise<SalaryPayment> {
  return request<SalaryPayment>(`${apiBaseUrl}/salary-payments/${paymentId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function getNetProfit(params: { periodStart: string; periodEnd: string }): Promise<NetProfitReport> {
  const query = new URLSearchParams({ period_start: params.periodStart, period_end: params.periodEnd });
  return request<NetProfitReport>(`${apiBaseUrl}/reports/net-profit?${query.toString()}`);
}

export async function getPaymentMethodBreakdown(
  params: DateRangeParams = {},
): Promise<PaymentMethodBreakdownRow[]> {
  const query = new URLSearchParams();
  if (params.fromDate) query.set("from_date", params.fromDate);
  if (params.toDate) query.set("to_date", params.toDate);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<PaymentMethodBreakdownRow[]>(`${apiBaseUrl}/reports/payment-methods${suffix}`);
}

export type GetChecksParams = {
  status?: CheckStatus;
  sort?: "due_asc" | "due_desc" | "amount_desc";
  search?: string;
};

export async function getChecks(params: GetChecksParams = {}): Promise<CheckRead[]> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.sort) query.set("sort", params.sort);
  if (params.search) query.set("search", params.search);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<CheckRead[]>(`${apiBaseUrl}/checks${suffix}`);
}

export async function getCheckSummary(): Promise<CheckSummary> {
  return request<CheckSummary>(`${apiBaseUrl}/checks/summary`);
}

export async function updateCheckStatus(checkId: number, status: CheckStatus): Promise<CheckRead> {
  return request<CheckRead>(`${apiBaseUrl}/checks/${checkId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

/** The one place every outgoing request goes through: attaches the stored
 * session's Authorization header automatically, and on a 401 clears the
 * session + fires the global "unauthorized" event (App.tsx listens for
 * this and drops back to the login screen) before throwing. This is
 * deliberately the single choke point — request()/requestPaged()/anything
 * else in this file must call through here, not fetch() directly, so 401
 * handling never needs to be duplicated per-call-site. */
async function rawFetch(url: string, options?: RequestInit): Promise<Response> {
  const session = getSession();
  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
        ...options?.headers,
      },
    });
  } catch {
    // fetch() itself threw — a real connectivity failure, not an HTTP
    // error response. No `status` on this ApiError distinguishes it from
    // a proper 401/403/etc for callers that want to tell them apart.
    throw new ApiError("Network request failed");
  }

  if (response.status === 401) {
    notifyUnauthorized();
    throw new ApiError("Session expired", { status: 401 });
  }

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as {
      detail?: string | DualPriceRequiredResponse | CreditLimitExceededResponse;
    } | null;
    const detail = error?.detail;
    if (detail && typeof detail === "object" && detail.code === "dual_price_required") {
      throw new ApiError(detail.message, { code: detail.code, status: response.status, products: detail.products });
    }
    if (detail && typeof detail === "object" && detail.code === "credit_limit_exceeded") {
      throw new ApiError(detail.message, {
        code: detail.code,
        status: response.status,
        creditInfo: {
          currentBalance: Number(detail.current_balance),
          creditLimit: Number(detail.credit_limit),
          creditPortion: Number(detail.credit_portion),
        },
      });
    }
    throw new ApiError(typeof detail === "string" ? detail : "Request failed", { status: response.status });
  }
  return response;
}

export async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await rawFetch(url, options);
  return response.json() as Promise<T>;
}