import type { ReactNode } from "react";
import { Printer, ShoppingBag } from "lucide-react";
import { useI18n } from "../i18n";
import { dateToJalaliStr } from "../utils/jalali";

export type ReceiptLine = {
  productName: string;
  quantity: number;
  unitPrice: number;
  discount: number;
  lineTotal: number;
  priceTier?: "old" | "new";
};

export type ReceiptData = {
  invoiceNumber: string;
  createdAt: string;
  paymentMethod: "cash" | "card" | "credit" | "check" | "mixed" | "loyalty";
  customerName?: string | null;
  lines: ReceiptLine[];
  subtotal: number;
  invoiceDiscount: number;
  total: number;
  paidAmount: number;
  remainingAmount: number;
};

type ReceiptViewProps = {
  receipt: ReceiptData;
  onNewSale: () => void;
  /** Rendered directly beside the "new sale" button — currently used for
   * the post-checkout quick-add-loyalty-customer CTA (see Sales.tsx). */
  extraAction?: ReactNode;
};

export function ReceiptView({ receipt, onNewSale, extraAction }: ReceiptViewProps) {
  const { t, money, number } = useI18n();
  const createdAt = new Date(receipt.createdAt);
  const dateLabel = `${dateToJalaliStr(createdAt)} ${createdAt.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
  const totalDiscount =
    receipt.invoiceDiscount + receipt.lines.reduce((sum, line) => sum + line.discount, 0);
  // Any sale can now have a remaining balance regardless of payment method
  // (a split cash/card payment can leave part on account).
  const isPartial = receipt.remainingAmount > 0;

  return (
    <div className="receipt-page">
      <div className="receipt-actions no-print">
        <button className="secondary-button" onClick={onNewSale}>
          <ShoppingBag size={17} />
          {t("newSale")}
        </button>
        {extraAction}
        <button className="primary-button" onClick={() => window.print()}>
          <Printer size={17} />
          {t("printReceipt")}
        </button>
      </div>

      <div id="receipt-print-area" className="receipt-sheet">
        <div className="receipt-header">
          <strong>{t("localStore")}</strong>
          <span>{t("receiptTitle")}</span>
        </div>

        <div className="receipt-meta">
          <span>{t("invoice")}: {receipt.invoiceNumber}</span>
          <span>{dateLabel}</span>
        </div>

        <table className="receipt-table">
          <thead>
            <tr>
              <th>{t("product")}</th>
              <th>{t("quantity")}</th>
              <th>{t("unitPrice")}</th>
              <th>{t("lineTotal")}</th>
            </tr>
          </thead>
          <tbody>
            {receipt.lines.map((line, index) => (
              <tr key={index}>
                <td>
                  {line.productName}
                  {line.priceTier && (
                    <small className="receipt-tier-note">
                      {" "}
                      ({line.priceTier === "old" ? t("dualPriceOldPrice") : t("dualPriceNewPrice")})
                    </small>
                  )}
                </td>
                <td>{number(line.quantity)}</td>
                <td>{money(line.unitPrice)}</td>
                <td>{money(line.lineTotal)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="receipt-summary">
          <div>
            <span>{t("subtotal")}</span>
            <strong>{money(receipt.subtotal)}</strong>
          </div>
          {totalDiscount > 0 && (
            <div>
              <span>{t("discount")}</span>
              <strong>-{money(totalDiscount)}</strong>
            </div>
          )}
          <div className="receipt-total-row">
            <span>{t("total")}</span>
            <strong>{money(receipt.total)}</strong>
          </div>
          <div>
            <span>{t("paymentMethod")}</span>
            <strong>{t(receipt.paymentMethod)}</strong>
          </div>
          {receipt.customerName && (
            <div>
              <span>{t("customer")}</span>
              <strong>{receipt.customerName}</strong>
            </div>
          )}
          {isPartial && (
            <>
              <div>
                <span>{t("paidAmount")}</span>
                <strong>{money(receipt.paidAmount)}</strong>
              </div>
              <div>
                <span>{t("remainingBalance")}</span>
                <strong>{money(receipt.remainingAmount)}</strong>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
