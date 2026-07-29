/**
 * Invoice Scanner — mock extraction layer.
 *
 * This is the ONLY place that will need to change when wiring in a real OCR/AI
 * service.  Everything else in the UI consumes the {@link ExtractedInvoice}
 * interface defined in types.ts and knows nothing about how the data is
 * obtained.
 *
 * To integrate a real service:
 *   1. Remove the mock data in this file.
 *   2. Replace the body of {@link extractInvoiceData} with the real API call.
 *   3. The return type stays {@link ExtractedInvoice} — the UI won't change.
 */

import type { ExtractedInvoice } from "./types";

// ---------------------------------------------------------------------------
// Mock product catalogue — used only for "unmatched product" simulation.
// In production this would be a real catalog lookup (or fuzzy match).
// ---------------------------------------------------------------------------
const MOCK_PRODUCT_NAMES = new Set([
  "شیر پاستوریزه ۱ لیتری",
  "ماست ساده ۴۰۰ گرمی",
  "پنیر سفید ۵۰۰ گرمی",
  "کره حیوانی ۱۰۰ گرمی",
  "خامه قنادی ۲۰۰ میلی‌لیتری",
  "دوغ ۱٫۵ لیتری",
  "نوشابه رژیمی ۳۳۰ میلی‌لیتری",
  "آب معدنی ۱٫۵ لیتری",
  "روغن سرخ کردنی ۱ لیتری",
  "برنج هاشمی ۱ کیلویی",
  "رب گوجه فرنگی ۸۰۰ گرمی",
  "ماکارونی ۷۰۰ گرمی",
  "قند شکسته ۱ کیلویی",
  "چای سیاه ۵۰۰ گرمی",
  "قهوه فوری ۲۰۰ گرمی",
]);

function isKnownProduct(name: string): boolean {
  return MOCK_PRODUCT_NAMES.has(name.trim());
}

// ---------------------------------------------------------------------------
// Mock invoice data — a "messy" realistic example that exercises all three
// warning states the UI must surface (zero-amount line, unmatched product,
// invoice total mismatch).
// ---------------------------------------------------------------------------
function buildMockInvoice(): ExtractedInvoice {
  const lineItems = [
    {
      rawName: "شیر پاستوریزه ۱ لیتری",
      quantity: 10,
      unit: "عدد",
      unitPrice: 28_000,
      taxAmount: 0,
      discountAmount: 0,
      lineTotal: 280_000,
    },
    {
      rawName: "پنیر سفید ۵۰۰ گرمی",
      quantity: 5,
      unit: "عدد",
      unitPrice: 65_000,
      taxAmount: 0,
      discountAmount: 15_000,
      lineTotal: 310_000,
    },
    {
      // Zero-amount line — item was scanned but price/cost couldn't be read
      rawName: "کره حیوانی ۱۰۰ گرمی",
      quantity: 3,
      unit: "عدد",
      unitPrice: 0,
      taxAmount: 0,
      discountAmount: 0,
      lineTotal: 0,
    },
    {
      // Unmatched product — not in the mock catalogue
      rawName: "کنسرو لوبیا چیتی ۴۰۰ گرمی  (اقلام تازه وارداتی)",
      quantity: 24,
      unit: "کارتن",
      unitPrice: 18_500,
      taxAmount: 0,
      discountAmount: 0,
      lineTotal: 444_000,
    },
    {
      rawName: "رب گوجه فرنگی ۸۰۰ گرمی",
      quantity: 12,
      unit: "عدد",
      unitPrice: 42_000,
      taxAmount: 12_600,
      discountAmount: 0,
      lineTotal: 516_600,
    },
  ];

  const netAmount = lineItems.reduce((s, l) => s + l.lineTotal, 0);
  const vatTotal = lineItems.reduce((s, l) => s + l.taxAmount, 0);
  const discountTotal = lineItems.reduce((s, l) => s + l.discountAmount, 0);

  return {
    header: {
      invoiceNumber: "INV-۹۸۱۲۴",
      date: "2026-07-24",
      supplierName: "شرکت پخش مواد غذایی البرز",
      paymentTerms: "30 روزه",
    },
    lineItems,
    netAmount,
    vatTotal,
    discountTotal,
    // INTENTIONAL mismatch: finalTotal does NOT match netAmount + vat - discount
    // This lets the UI surface a "total mismatch" warning.
    finalTotal: 1_450_000,
  };
}

// ---------------------------------------------------------------------------
// Mock failures — toggle this to test the error flow.
// ---------------------------------------------------------------------------
/** Set to `true` to simulate an extraction failure. */
const SIMULATE_FAILURE = false;
/** Set to `true` to simulate a network timeout. */
const SIMULATE_TIMEOUT = false;

/**
 * Extract invoice data from an image file.
 *
 * Currently returns mock data after a simulated delay.  When a real OCR/AI
 * service is wired in, only the inside of this function needs to change.
 *
 * @param _imageFile - The image file (unused in mock mode, will be passed to
 *                     the real OCR service in production).
 * @returns A promise that resolves to {@link ExtractedInvoice}.
 */
export async function extractInvoiceData(
  _imageFile: File,
): Promise<ExtractedInvoice> {
  // Simulate network latency (1.5 – 2.5 seconds)
  const delay = 1500 + Math.random() * 1000;
  await new Promise((resolve) => setTimeout(resolve, delay));

  // Simulated failure paths
  if (SIMULATE_FAILURE) {
    throw new Error("خطا در خوانش تصویر: متن فاکتور خوانا نیست. لطفاً تصویر واضح‌تری ارسال کنید.");
  }
  if (SIMULATE_TIMEOUT) {
    throw new Error("مدت زمان درخواست به پایان رسید. لطفاً اتصال اینترنت خود را بررسی کنید و دوباره تلاش کنید.");
  }

  return buildMockInvoice();
}

/**
 * Check whether a product name matches a known product in the catalogue.
 *
 * Current implementation uses exact string matching against a small hardcoded
 * list.  In production this will be replaced by a fuzzy-match or an API call.
 *
 * @returns The matched product name, or `null` if no match was found.
 */
export function matchProductName(rawName: string): string | null {
  const trimmed = rawName.trim();
  if (isKnownProduct(trimmed)) return trimmed;

  // Naïve normalisation for the mock (strip parenthesised suffixes, etc.)
  // In production this would be a proper fuzzy-matching routine.
  const cleaned = trimmed.replace(/\(.*?\)/g, "").trim();
  if (cleaned && cleaned !== trimmed && isKnownProduct(cleaned)) return cleaned;

  return null;
}