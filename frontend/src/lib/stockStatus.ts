export type StockStatus = "zero" | "low" | "ok";

/** Shared zero/low-stock classification, used by both the Products page and the Sales/POS page. */
export function getStockStatus(stockQuantity: number, lowStockThreshold: number): StockStatus {
  if (stockQuantity <= 0) return "zero";
  if (lowStockThreshold > 0 && stockQuantity <= lowStockThreshold) return "low";
  return "ok";
}
