import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";

import { useI18n } from "../i18n";
import { Modal } from "./Modal";
import type { DualPriceRequiredResponse } from "../api";
import { AmountInput } from "./AmountInput";

type DualPriceConfirmModalProps = {
  products: DualPriceRequiredResponse["products"];
  submitting?: boolean;
  onConfirm: (newSalePrices: Record<number, number>) => void;
  onSkip: () => void;
  onCancel: () => void;
};

export function DualPriceConfirmModal({
  products,
  submitting,
  onConfirm,
  onSkip,
  onCancel,
}: DualPriceConfirmModalProps) {
  const { t, money } = useI18n();
  const [prices, setPrices] = useState<Record<number, number>>(() =>
    Object.fromEntries(products.map((p) => [p.product_id, p.suggested_new_sale_price])),
  );

  function updatePrice(productId: number, value: string) {
    const parsed = Number(value);
    setPrices((current) => ({
      ...current,
      [productId]: Number.isNaN(parsed) ? 0 : parsed,
    }));
  }

  return (
    <Modal onClose={onCancel}>
      <div className="dual-price-modal" onMouseDown={(event) => event.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
          <div>
            <h2>{t("dualPriceTitle")}</h2>
            <p>{t("dualPricePrompt")}</p>
          </div>
          <button className="icon-button" onClick={onCancel} aria-label={t("cancel")}>
            <X size={18} />
          </button>
        </div>

        {products.map((product) => (
          <div className="dual-price-product-card" key={product.product_id}>
            <h4>{product.product_name}</h4>

            {product.is_update_existing_dual && (
              <span className="warning-chip unmatched" style={{ marginBottom: 8 }}>
                <AlertTriangle size={13} />
                {t("dualPriceReplaceWarning")}
              </span>
            )}

            {product.purchase_price_changed !== false && (
              <div className="price-comparison">
                <span className="old-label">
                  {t("dualPriceOldPurchase")}: {money(product.current_purchase_price)}
                </span>
                <span className="arrow">→</span>
                <span className="new-label">
                  {t("dualPriceNewPurchase")}: {money(product.new_purchase_price)}
                </span>
              </div>
            )}

            <label className="field">
              <span>{t("dualPriceSuggestedSale")}</span>
              {product.sale_price_changed && (
                <small className="field-hint">
                  {t("dualPriceOldPrice")}: {money(product.current_sale_price)}
                </small>
              )}
              <AmountInput
                min="0"
                value={Number(prices[product.product_id]) || null}
                onChange={(v) => updatePrice(product.product_id, v === null ? "" : String(v))}
              />
            </label>
          </div>
        ))}

        <div className="dual-price-actions">
          <button
            className="primary-button"
            disabled={submitting}
            onClick={() => onConfirm(prices)}
          >
            {t("dualPriceConfirm")}
          </button>
          <button className="secondary-button" disabled={submitting} onClick={onSkip}>
            {t("dualPriceSkip")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
