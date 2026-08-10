/** Quantities, and the difference between counting and weighing.
 *
 * A counted product's quantity is a whole number and reads as one: "3".
 * A weighted product's is a measurement, and a measurement keeps its
 * trailing zeros — 2.350 kg is not "2.35 kg", because the third digit is
 * part of what was on the scale. The app's shared `number()` formatter
 * cannot express that on its own: `toLocaleString` drops trailing zeros,
 * so it renders both 2.35 and 2.350 identically.
 *
 * The backend column is Numeric(14,3), so three decimals is the precision
 * the database itself keeps, and matching it here means nothing is shown
 * that was not stored.
 */

/** The precision Numeric(14,3) stores, and the step the POS inputs use. */
export const WEIGHT_DECIMALS = 3;
export const WEIGHT_STEP = 0.001;

/**
 * Format a line quantity for display. Weighted quantities are padded to
 * three decimals; counted ones keep the app's ordinary number formatting.
 */
export function formatQuantity(
  quantity: number,
  isWeighted: boolean,
  locale: string,
  numberFn: (value: number) => string,
): string {
  if (!isWeighted) return numberFn(quantity);
  return quantity.toLocaleString(locale, {
    minimumFractionDigits: WEIGHT_DECIMALS,
    maximumFractionDigits: WEIGHT_DECIMALS,
  });
}

/**
 * Format a quantity with its unit appended, when the product has one.
 * Counted products usually have no `unit` set, and reading "3" is clearer
 * than "3 عدد", so an absent unit simply produces the bare number.
 */
export function formatQuantityWithUnit(
  quantity: number,
  isWeighted: boolean,
  unit: string | null | undefined,
  locale: string,
  numberFn: (value: number) => string,
): string {
  const formatted = formatQuantity(quantity, isWeighted, locale, numberFn);
  return unit ? `${formatted} ${unit}` : formatted;
}

/**
 * Round a typed weight to the stored precision. Without this, a pasted or
 * arrow-keyed value like 2.3499999999 reaches the backend, which quantizes
 * it to 2.350 — and the line total the cashier was shown while typing then
 * disagrees with the one on the receipt.
 */
export function roundToWeightPrecision(value: number): number {
  const factor = 10 ** WEIGHT_DECIMALS;
  return Math.round(value * factor) / factor;
}
