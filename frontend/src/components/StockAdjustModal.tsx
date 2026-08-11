import { useState } from "react";
import { Boxes } from "lucide-react";

import { adjustStock, getErrorMessage } from "../api";
import { useI18n } from "../i18n";
import { formatQuantityWithUnit } from "../lib/quantity";
import type { Product } from "../types";
import { AmountInput } from "./AmountInput";
import { Modal } from "./Modal";

type Props = {
  product: Product;
  onAdjusted: (product: Product) => void;
  onClose: () => void;
};

/**
 * Move stock by hand, through the inventory ledger.
 *
 * The product form deliberately cannot edit `stock_quantity`: every other
 * stock change writes an InventoryTransaction, and the audit that keeps this
 * app honest checks `stock == Σ movements`. Letting the form overwrite the
 * number would break that silently and leave the difference unexplainable.
 *
 * So a correction is its own action with its own record. The reason is
 * required — "12 fewer, no reason given" cannot be told apart later from a
 * miscount, a breakage and a theft.
 *
 * It moves stock only. The cost of anything written off is a real loss but
 * has nowhere honest to go yet: Expense carries a cash/bank method and is
 * subtracted from the till at close, so booking it there would invent a cash
 * shortage that never happened.
 */
export function StockAdjustModal({ product, onAdjusted, onClose }: Props) {
  const { t, number, language } = useI18n();
  const [delta, setDelta] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const current = Number(product.stock_quantity);
  const resulting = current + (delta ?? 0);
  const wouldGoNegative = resulting < 0;
  const ready = delta !== null && delta !== 0 && reason.trim().length > 0 && !wouldGoNegative;

  async function submit() {
    if (!ready) return;
    setSaving(true);
    setError("");
    try {
      const result = await adjustStock({
        product_id: product.id,
        quantity_change: delta as number,
        reason: reason.trim(),
      });
      onAdjusted(result.product);
    } catch (caught) {
      setError(getErrorMessage(caught, t));
    } finally {
      setSaving(false);
    }
  }

  const show = (value: number) =>
    formatQuantityWithUnit(value, product.is_weighted, product.unit, language, number);

  return (
    <Modal onClose={onClose}>
      <div
        className="party-form"
        style={{ width: "min(440px, 100%)" }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="panel-heading">
          <h2><Boxes size={18} /> {t("adjustStock")}</h2>
        </div>
        <p className="muted-text">{product.name}</p>

        <label className="field">
          <span>{t("stockAdjustDelta")}</span>
          <AmountInput
            currencyAware={false}
            value={delta}
            onChange={setDelta}
            placeholder={t("stockAdjustDeltaPlaceholder")}
            autoFocus
          />
          <small className="field-hint">{t("stockAdjustDeltaHint")}</small>
        </label>

        <div className="shift-close-summary">
          <div>
            <span>{t("currentStock")}</span>
            <strong>{show(current)}</strong>
          </div>
          <div>
            <span>{t("stockAfterAdjustment")}</span>
            <strong className={wouldGoNegative ? "quantity-negative" : ""}>{show(resulting)}</strong>
          </div>
        </div>
        {wouldGoNegative && <div className="feedback-banner error">{t("insufficientStock")}</div>}

        <label className="field">
          <span>{t("stockAdjustReason")}</span>
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder={t("stockAdjustReasonPlaceholder")}
            list="stock-adjust-reasons"
          />
          {/* Suggestions, not an enum — the same "manageable, not locked"
              treatment expense categories get. */}
          <datalist id="stock-adjust-reasons">
            <option value={t("stockReasonSpoilage")} />
            <option value={t("stockReasonBreakage")} />
            <option value={t("stockReasonTheft")} />
            <option value={t("stockReasonStocktake")} />
          </datalist>
        </label>

        {error && <div className="feedback-banner error">{error}</div>}

        <div className="form-actions">
          <button className="secondary-button" onClick={onClose}>{t("cancel")}</button>
          <button className="primary-button" disabled={!ready || saving} onClick={submit}>
            {saving ? t("loading") : t("save")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
