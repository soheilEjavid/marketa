import type { SaleItemRead } from "../types";

export type MarginStatus = "negative" | "low" | "healthy";

export type InvoiceMargin = {
  revenue: number;
  cost: number;
  profit: number;
  marginPct: number | null;
};

/**
 * Margin-on-sales (not markup-on-cost): (salePrice - costPrice) / salePrice * 100.
 * Returns null when salePrice is not positive — margin is undefined in that case.
 */
export function calculateMarginPct(salePrice: number, costPrice: number): number | null {
  if (!Number.isFinite(salePrice) || salePrice <= 0) return null;
  return ((salePrice - costPrice) / salePrice) * 100;
}

/** Mirrors the low/zero-stock threshold shape from stockStatus.ts, adapted for margin. */
export function getMarginStatus(marginPct: number): MarginStatus {
  if (marginPct < 0) return "negative";
  if (marginPct < 15) return "low";
  return "healthy";
}

/**
 * Aggregates whole-invoice margin from sale line items. Revenue uses each
 * line's backend-computed line_total (post-discount), cost uses cost_price * quantity,
 * then delegates to calculateMarginPct so invoice-level and per-line margin
 * always agree on the same formula.
 */
export function calculateInvoiceMargin(items: SaleItemRead[]): InvoiceMargin {
  let revenue = 0;
  let cost = 0;
  for (const item of items) {
    revenue += Number(item.line_total);
    cost += Number(item.cost_price) * Number(item.quantity);
  }
  const profit = revenue - cost;
  return { revenue, cost, profit, marginPct: calculateMarginPct(revenue, cost) };
}

/** Rounds to one decimal place and formats with the app's locale-aware number formatter. */
export function formatMarginPct(
  marginPct: number,
  language: "fa" | "en",
  numberFn: (value: number) => string,
): string {
  const rounded = Math.round(marginPct * 10) / 10;
  const display = numberFn(Object.is(rounded, -0) ? 0 : rounded);
  return language === "fa" ? `٪${display}` : `${display}%`;
}
