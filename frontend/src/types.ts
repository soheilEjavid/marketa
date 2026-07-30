export type Product = {
  id: number;
  barcode: string | null;
  sku: string | null;
  name: string;
  brand: string | null;
  purchase_price: string;
  sale_price: string;
  min_sale_price: string | null;
  stock_quantity: string;
  low_stock_threshold: string;
  unit: string | null;
  packaging_unit_label: string | null;
  packaging_unit_quantity: string | null;
  image_url: string | null;
  description: string | null;
  expiration_date: string | null;
  category_id: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  /* ── Dual-price fields ────────────────────────────────────────── */
  is_dual_priced?: boolean;
  old_purchase_price?: string | null;
  old_sale_price?: string | null;
  new_purchase_price?: string | null;
  new_sale_price?: string | null;
  old_price_stock_estimate?: number | null;
  dual_price_started_at?: string | null;
  /** Manager override of the automatic loyalty earn rate; null = automatic. */
  loyalty_point_multiplier?: string | null;
};

export type ProductInput = {
  name: string;
  barcode?: string | null;
  sku?: string | null;
  brand?: string | null;
  purchase_price: number;
  sale_price: number;
  min_sale_price?: number | null;
  stock_quantity: number;
  low_stock_threshold?: number;
  unit?: string | null;
  packaging_unit_label?: string | null;
  packaging_unit_quantity?: number | null;
  image_url?: string | null;
  description?: string | null;
  category_id?: number | null;
  is_active: boolean;
  loyalty_point_multiplier?: number | null;
};

export type ProductUpdate = {
  // Deliberately no stock_quantity — see backend ProductUpdate schema.
  name?: string;
  barcode?: string | null;
  sku?: string | null;
  brand?: string | null;
  purchase_price?: number;
  sale_price?: number;
  min_sale_price?: number | null;
  low_stock_threshold?: number;
  unit?: string | null;
  packaging_unit_label?: string | null;
  packaging_unit_quantity?: number | null;
  image_url?: string | null;
  description?: string | null;
  category_id?: number | null;
  is_active?: boolean;
  /* Dual-price management */
  is_dual_priced?: boolean;
  old_purchase_price?: number | null;
  old_sale_price?: number | null;
  new_purchase_price?: number | null;
  new_sale_price?: number | null;
  old_price_stock_estimate?: number | null;
  /** When collapsing: which tier to keep ("old" | "new") */
  collapse_to_tier?: "old" | "new";
  loyalty_point_multiplier?: number | null;
};

export type Category = {
  id: number;
  name: string;
  description: string | null;
};

export type AuditLogEntry = {
  id: number;
  user_id: number | null;
  username: string | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  details: string | null;
  occurred_at: string | null;
};

export type CategoryInput = {
  name: string;
  description?: string | null;
};

export type CategoryUpdateInput = {
  name?: string;
  description?: string | null;
};

export type Customer = {
  id: number;
  full_name: string;
  phone: string | null;
  national_id: string | null;
  address: string | null;
  notes: string | null;
  credit_limit: string;
  balance: string;
  is_active: boolean;
  birth_date: string | null;
  loyalty_points_balance: number;
  loyalty_member: boolean;
  created_at: string;
  updated_at: string;
};

export type CustomerInput = {
  full_name: string;
  phone?: string | null;
  national_id?: string | null;
  address?: string | null;
  notes?: string | null;
  credit_limit: number;
  is_active: boolean;
  birth_date?: string | null;
  // Enrolls the customer as a loyalty member immediately on creation —
  // used by the post-checkout quick-add suggestion (a big, no-customer
  // sale that crossed the membership threshold); never retroactive.
  loyalty_member?: boolean;
};

export type LoyaltyTier = "bronze" | "silver" | "gold";

export type LoyaltyBalance = {
  customer_id: number;
  points_balance: number;
  points_value_toman: string;
  max_redeemable_points: number;
  is_member: boolean;
  tier: LoyaltyTier;
};

export type LoyaltyRewardSuggestion = {
  product_id: number;
  product_name: string;
  sale_price: string;
  points_required: number;
  affordable: boolean;
  reason: "near_expiry" | "dead_stock";
  days_until_expiry: number | null;
};

export type CustomerTierRow = {
  customer_id: number;
  customer_name: string;
  lifetime_spend: string;
  tier: LoyaltyTier;
};

export type ChurnCouponIssueResult = {
  customer_id: number;
  customer_name: string;
  points: number;
};

export type LoyaltyTransaction = {
  id: number;
  points: number;
  transaction_type: "earn" | "redeem" | "expire" | "adjust";
  sale_id: number | null;
  expires_at: string | null;
  expired: boolean;
  reason: string | null;
  created_at: string;
};

export type LoyaltyLiabilityRow = {
  customer_id: number;
  customer_name: string;
  points_balance: number;
  points_value_toman: string;
};

export type BirthdayCustomerRow = {
  customer_id: number;
  customer_name: string;
  phone: string | null;
  birth_date: string;
  days_until_birthday: number;
};

export type ChurnRiskCustomerRow = {
  customer_id: number;
  customer_name: string;
  phone: string | null;
  purchase_count_recent: number;
  last_purchase_at: string;
  days_since_last_purchase: number;
};

export type LoyaltySettings = {
  min_invoice_total_for_membership: string | null;
  min_invoice_profit_for_membership: string | null;
  tier_silver_min_spend: string | null;
  tier_gold_min_spend: string | null;
  tier_window_days: number | null;
  tier_silver_earn_bonus: string | null;
  tier_gold_earn_bonus: string | null;
  churn_recovery_coupon_points: number | null;
};

export type LoyaltyRewardCatalogRow = {
  product_id: number;
  product_name: string;
  sale_price: string;
  points_required: number;
  is_suggested: boolean;
  reason: "near_expiry" | "dead_stock" | null;
};

export type LoyaltyRedemptionRow = {
  payment_id: number;
  customer_id: number;
  customer_name: string;
  sale_id: number | null;
  invoice_number: string | null;
  discount_value: string;
  points_used: number;
  product_names: string[];
  paid_at: string;
};

export type Supplier = {
  id: number;
  name: string;
  contact_person: string | null;
  phone: string | null;
  address: string | null;
  notes: string | null;
  balance: string;
  last_purchase_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type SupplierInput = {
  name: string;
  contact_person?: string | null;
  phone?: string | null;
  address?: string | null;
  notes?: string | null;
  is_active: boolean;
};

export type SaleItemCreate = {
  /** Present only when editing an existing line; omitted/null = new line. */
  id?: number | null;
  product_id: number;
  quantity: number;
  unit_price?: number | null;
  discount?: number;
  /** "old" or "new" — which price tier was selected at checkout. */
  price_tier?: "old" | "new";
};

export type SalePaymentMethod = "cash" | "card";

export type SalePaymentLineInput = {
  method: SalePaymentMethod;
  amount: number;
  check_number?: string | null;
  check_bank_name?: string | null;
  /** ISO date (YYYY-MM-DD) — required when method is "check". */
  check_due_date?: string | null;
  notes?: string | null;
};

export type SaleCreate = {
  invoice_number?: string | null;
  customer_id?: number | null;
  discount?: number;
  // Legacy single-method fields — still fully supported by the backend,
  // but the checkout UI now sends payment_lines instead (see Sales.tsx).
  paid_amount?: number | null;
  payment_method?: "cash" | "card" | "credit";
  /** A non-empty list takes over entirely from payment_method/paid_amount. */
  payment_lines?: SalePaymentLineInput[];
  notes?: string | null;
  items: SaleItemCreate[];
  redeem_points?: number;
  /** Only honored server-side if the caller is admin/manager — see the
   * credit-limit-exceeded retry flow in Sales.tsx. */
  allow_credit_override?: boolean;
};

/**
 * Narrow, delta-safe edit of an existing sale's lines and whole-invoice
 * discount. Customer, payment method, and invoice number are NOT editable
 * here (out of scope for invoice editing).
 */
export type SaleEditRequest = {
  discount?: number;
  items: SaleItemCreate[];
  /** Optional free-text note explaining the edit. */
  reason?: string | null;
};

export type SaleItemRead = {
  id: number;
  product_id: number;
  quantity: string;
  unit_price: string;
  cost_price: string;
  discount: string;
  line_total: string;
  price_tier?: "old" | "new";
};

export type SalePaymentLineRead = {
  id: number;
  method: SalePaymentMethod;
  amount: string;
  check_number: string | null;
  check_bank_name: string | null;
  check_due_date: string | null;
  check_status: CheckStatus | null;
  notes: string | null;
  paid_at: string;
};

export type Sale = {
  id: number;
  invoice_number: string;
  customer_id: number | null;
  subtotal: string;
  discount: string;
  total: string;
  paid_amount: string;
  remaining_amount: string;
  payment_method: "cash" | "card" | "credit" | "check" | "mixed" | "loyalty";
  payment_status: "paid" | "partial" | "unpaid";
  status: "draft" | "completed" | "cancelled";
  notes: string | null;
  created_at: string;
  items: SaleItemRead[];
  payment_lines: SalePaymentLineRead[];
  shift_id: number | null;
  // Transient — only true on the immediate POST /sales response for the
  // sale whose payment just crossed the loyalty membership threshold.
  loyalty_membership_just_earned?: boolean;
};

export type UserSummary = {
  id: number;
  username: string;
  full_name: string;
  role: string;
  is_active: boolean;
};

export type UserCreate = {
  username: string;
  password: string;
  full_name: string;
  role: "admin" | "cashier" | "manager" | "inventory_manager" | "accountant";
};

export type ShiftStatus = "open" | "closed";

export type CashierShift = {
  id: number;
  cashier_id: number;
  cashier_name: string;
  status: ShiftStatus;
  opening_cash: string;
  closing_cash: string | null;
  expected_cash: string | null;
  difference: string | null;
  opened_at: string;
  closed_at: string | null;
  notes: string | null;
};

export type CashierPerformanceRow = {
  cashier_id: number;
  cashier_name: string;
  invoice_count: number;
  total_sales: string;
  average_ticket: string;
  total_discount: string;
  payment_method_breakdown: Record<string, string>;
  edited_count: number;
  held_count: number;
  discarded_count: number;
};

export type PurchaseItemCreate = {
  /** Present only when editing an existing line; omitted/null = new line. */
  id?: number | null;
  product_id: number;
  quantity: number;
  unit_cost: number;
  selling_price?: number | null;
  expiry_date?: string | null;
  /** کالای امانی — only meaningful on purchase creation; ignored by edits. */
  is_consignment?: boolean;
};

export type PurchasePaymentMethod = "cash" | "card" | "check";

export type PurchasePaymentLineInput = {
  method: PurchasePaymentMethod;
  amount: number;
  check_number?: string | null;
  check_bank_name?: string | null;
  /** ISO date (YYYY-MM-DD) — required when method is "check". */
  check_due_date?: string | null;
  notes?: string | null;
};

export type PurchaseCreate = {
  invoice_number?: string | null;
  supplier_id?: number | null;
  payment_lines?: PurchasePaymentLineInput[];
  notes?: string | null;
  items: PurchaseItemCreate[];
  confirm_dual_pricing?: boolean;
  dual_pricing_new_sale_prices?: Record<number, number>;
};

/**
 * Narrow, delta-safe edit of an existing purchase's lines. Supplier and
 * invoice number are NOT editable here. Blocked entirely by the backend if
 * any referenced product currently has an active dual-price state.
 */
export type PurchaseEditRequest = {
  items: PurchaseItemCreate[];
  /** Optional free-text note explaining the edit. */
  reason?: string | null;
};

export type PurchaseItemRead = {
  id: number;
  product_id: number;
  quantity: string;
  unit_cost: string;
  selling_price: string | null;
  expiry_date: string | null;
  line_total: string;
  is_consignment: boolean;
  consignment_settled_at: string | null;
};

export type CheckStatus = "pending" | "cleared" | "bounced";

export type PurchasePaymentLineRead = {
  id: number;
  method: PurchasePaymentMethod;
  amount: string;
  check_number: string | null;
  check_bank_name: string | null;
  check_due_date: string | null;
  check_status: CheckStatus | null;
  notes: string | null;
  paid_at: string;
};

export type CheckRead = {
  id: number;
  supplier_id: number | null;
  supplier_name: string | null;
  purchase_id: number | null;
  purchase_invoice_number: string | null;
  amount: string;
  check_number: string | null;
  check_bank_name: string | null;
  check_due_date: string | null;
  check_status: CheckStatus;
  notes: string | null;
  paid_at: string;
};

export type CheckSummary = {
  due_this_week: string;
  due_this_month: string;
};

export type Purchase = {
  id: number;
  invoice_number: string;
  supplier_id: number | null;
  total: string;
  paid_amount: string;
  remaining_amount: string;
  payment_status: "paid" | "partial" | "unpaid";
  status: "draft" | "completed" | "cancelled";
  notes: string | null;
  created_at: string;
  items: PurchaseItemRead[];
  payment_lines: PurchasePaymentLineRead[];
};

export type InventoryTransactionType = "sale" | "purchase" | "adjustment";

export type InventoryTransaction = {
  id: number;
  product_id: number;
  product_name: string;
  quantity_change: string;
  transaction_type: InventoryTransactionType;
  related_id: number | null;
  timestamp: string;
};

export type DashboardDebtor = {
  customer_id: number;
  customer_name: string;
  phone: string | null;
  balance: string;
};

export type DashboardActivity = {
  customer_id: number;
  customer_name: string;
  entry_type: string;
  reference: string;
  amount: string;
  occurred_at: string;
  payment_status: string | null;
};

export type DashboardTrendPoint = {
  date: string;
  sales: string;
};

export type ProfitTrendPoint = {
  date: string;
  profit: string;
};

export type DashboardSummary = {
  today_sales: string;
  today_transactions: number;
  active_products: number;
  low_stock_products: number;
  total_receivables: string;
  total_payables: string;
  top_debtors: DashboardDebtor[];
  recent_customer_activity: DashboardActivity[];
  sales_trend: DashboardTrendPoint[];
  profit_trend?: ProfitTrendPoint[];
};

export type DailySalesPoint = {
  date: string;
  total_sales: string;
  transaction_count: number;
  average_ticket: string;
  profit: string;
};

export type TopProductRow = {
  product_id: number;
  product_name: string;
  total_quantity: string;
  total_revenue: string;
  total_profit: string;
};

export type DeadStockRow = {
  product_id: number;
  product_name: string;
  category_name: string | null;
  stock_quantity: string;
  days_since_last_sale: number | null;
  value_tied_up: string;
};

export type OutstandingConsignmentRow = {
  purchase_item_id: number;
  purchase_id: number;
  invoice_number: string;
  supplier_id: number | null;
  supplier_name: string | null;
  product_id: number;
  product_name: string;
  quantity: string;
  value: string;
  received_at: string;
};

export type PaymentMethodBreakdownRow = {
  payment_method: "cash" | "card" | "credit" | "mixed";
  total: string;
  transaction_count: number;
};

export type Payment = {
  id: number;
  amount: string;
  method: "cash" | "card" | "credit";
  reference: string | null;
  notes: string | null;
  paid_at: string;
};

export type LedgerEntry = {
  id: string;
  occurred_at: string;
  entry_type: "sale" | "purchase" | "payment";
  reference: string;
  description: string;
  debit: string;
  credit: string;
  running_balance: string;
  payment_status: string | null;
};

export type CustomerLedger = {
  customer_id: number;
  customer_name: string;
  balance: string;
  entries: LedgerEntry[];
};

export type SupplierLedger = {
  supplier_id: number;
  supplier_name: string;
  balance: string;
  entries: LedgerEntry[];
};

/* ===== Invoice Scanner Types ===== */

/** A single line item extracted from an invoice image. */
export type ExtractedLineItem = {
  /** Raw item name as it appeared on the invoice (may be long/messy). */
  rawName: string;
  /** Parsed quantity as a number (e.g. 2 for "2 carton"). */
  quantity: number;
  /** Human-readable unit description (e.g. "carton", "box", "piece"). */
  unit: string;
  /** Unit price in the invoice currency. */
  unitPrice: number;
  /** Tax amount for this line (0 if not itemized). */
  taxAmount: number;
  /** Discount amount for this line (0 if none). */
  discountAmount: number;
  /** Line total as printed on the invoice. */
  lineTotal: number;
};

/** Header-level fields extracted from an invoice image. */
export type ExtractedInvoiceHeader = {
  invoiceNumber: string;
  /** ISO date string (YYYY-MM-DD) or empty if not found. */
  date: string;
  supplierName: string;
  paymentTerms: string;
};

/** The complete result of scanning an invoice. */
export type ExtractedInvoice = {
  header: ExtractedInvoiceHeader;
  lineItems: ExtractedLineItem[];
  /** Net amount before tax/discount (sum of line totals as printed). */
  netAmount: number;
  /** Total VAT/GST as printed on the invoice. */
  vatTotal: number;
  /** Total discount as printed on the invoice. */
  discountTotal: number;
  /** Final total as printed on the invoice. */
  finalTotal: number;
};