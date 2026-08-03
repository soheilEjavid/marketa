export type ExpiryStatus = "expired" | "red" | "orange" | "green";

/** Same red/orange thresholds as services/reports.py::near_expiry_products
 * (red_days=7, orange_days=30) — kept as this module's own defaults so the
 * Products page's full view (which classifies every expiry-dated product,
 * including ones far enough out to be "green") agrees with the backend
 * report/dashboard widget on where red ends and orange begins. */
export function daysUntilExpiry(expirationDate: string, today: Date = new Date()): number {
  const expiry = new Date(expirationDate);
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startOfExpiry = new Date(expiry.getFullYear(), expiry.getMonth(), expiry.getDate());
  return Math.round((startOfExpiry.getTime() - startOfToday.getTime()) / 86_400_000);
}

/** Mirrors getStockStatus/getMarginStatus's shape: a small pure classifier
 * function, not a new ad-hoc styling scheme. */
export function getExpiryStatus(
  daysRemaining: number,
  redDays = 7,
  orangeDays = 30,
): ExpiryStatus {
  if (daysRemaining < 0) return "expired";
  if (daysRemaining <= redDays) return "red";
  if (daysRemaining <= orangeDays) return "orange";
  return "green";
}
