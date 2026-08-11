import type { PaymentStatus } from "../types";

/**
 * The label key for every value PaymentStatus can take.
 *
 * Both ledger views used to pick between two labels with a ternary —
 * `status === "unpaid" ? "unpaidStatus" : "partialStatus"` — over an enum
 * with three values. It was correct only because the line above filtered
 * "paid" out first. That is a mine: anyone relaxing the filter, for a
 * perfectly good reason and without reading two lines up, would get a fully
 * settled invoice labelled "partially paid".
 *
 * A wrong label is worse than a missing one. A blank prompts somebody to
 * look; a confident wrong answer does not. Typed as a full Record, so
 * adding a value to PaymentStatus fails the build here rather than
 * mislabelling it in production.
 */
const LABELS: Record<PaymentStatus, string> = {
  paid: "paidStatus",
  partial: "partialStatus",
  unpaid: "unpaidStatus",
};

/** The ledger endpoints type this loosely, so accept anything and let an
 *  unknown value fall through to itself — visible, not silent. */
export function paymentStatusLabel(status: string | null | undefined): string {
  if (!status) return "";
  return LABELS[status as PaymentStatus] ?? status;
}
