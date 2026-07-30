import { useEffect, useState } from "react";
import { Trash2, X } from "lucide-react";

import { ApiError, editPurchase, getProducts } from "../api";
import { useI18n } from "../i18n";
import type { Product, Purchase } from "../types";
import { Modal } from "./Modal";
import { ProductCombobox } from "./ProductCombobox";
import { JalaliDatePicker } from "./JalaliDatePicker";

type PurchaseEditFormProps = {
  purchase: Purchase;
  onClose: () => void;
  onSaved: () => void;
};

type EditLine = {
  /** null = a brand-new line being added during this edit. */
  id: number | null;
  productId: number;
  productName: string;
  quantity: number;
  unitCost: number;
  sellingPrice: number | null;
  expiryDate: string;
};

let nextKey = 1;

export function PurchaseEditForm({ purchase, onClose, onSaved }: PurchaseEditFormProps) {
  const { t, money } = useI18n();
  const [products, setProducts] = useState<Product[]>([]);
  const [lines, setLines] = useState<(EditLine & { key: number })[]>([]);
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState<"loading" | "idle" | "submitting" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    getProducts()
      .then((productList) => {
        setProducts(productList);
        setLines(
          purchase.items.map((item) => {
            const product = productList.find((p) => p.id === item.product_id);
            return {
              key: nextKey++,
              id: item.id,
              productId: item.product_id,
              productName: product?.name ?? `#${item.product_id}`,
              quantity: Number(item.quantity),
              unitCost: Number(item.unit_cost),
              sellingPrice: item.selling_price ? Number(item.selling_price) : null,
              expiryDate: item.expiry_date ?? "",
            };
          }),
        );
        setStatus("idle");
      })
      .catch(() => {
        setStatus("error");
        setMessage(t("apiError"));
      });
  }, [purchase, t]);

  const total = lines.reduce((sum, line) => sum + line.quantity * line.unitCost, 0);

  function updateLine(key: number, changes: Partial<EditLine>) {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...changes } : line)));
  }

  function removeLine(key: number) {
    setLines((current) => current.filter((line) => line.key !== key));
  }

  function addLineForProduct(product: Product) {
    setLines((current) => {
      const existingIndex = current.findIndex((line) => line.productId === product.id);
      if (existingIndex !== -1) {
        return current.map((line, i) =>
          i === existingIndex ? { ...line, quantity: line.quantity + 1 } : line,
        );
      }
      return [
        ...current,
        {
          key: nextKey++,
          id: null,
          productId: product.id,
          productName: product.name,
          quantity: 1,
          unitCost: Number(product.purchase_price),
          sellingPrice: Number(product.sale_price),
          expiryDate: "",
        },
      ];
    });
  }

  function addLine(productId: number) {
    const product = products.find((p) => p.id === productId);
    if (!product) return;
    addLineForProduct(product);
  }

  // A brand-new product made via ProductCombobox's quick-add — `products`
  // (fetched once on mount) doesn't contain it yet, so addLine()'s lookup
  // by id would silently no-op. See the same fix in Purchases.tsx.
  function handleProductCreated(product: Product) {
    setProducts((current) => [...current, product]);
    addLineForProduct(product);
  }

  async function handleSubmit() {
    if (!lines.length) return;
    setStatus("submitting");
    setMessage("");
    try {
      await editPurchase(purchase.id, {
        reason: reason.trim() || null,
        items: lines.map((line) => ({
          ...(line.id !== null ? { id: line.id } : {}),
          product_id: line.productId,
          quantity: line.quantity,
          unit_cost: line.unitCost,
          ...(line.sellingPrice !== null ? { selling_price: line.sellingPrice } : {}),
          ...(line.expiryDate ? { expiry_date: line.expiryDate } : {}),
        })),
      });
      onSaved();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof ApiError ? error.message : t("apiError"));
    }
  }

  return (
    <Modal onClose={onClose}>
      <div className="party-form product-form" style={{ width: "min(820px, 100%)" }} onMouseDown={(event) => event.stopPropagation()}>
        <div className="panel-heading">
          <h2>{t("editInvoice")}</h2>
          <button className="icon-button" onClick={onClose} aria-label={t("cancel")}>
            <X size={18} />
          </button>
        </div>

        {message && <div className="feedback-banner error">{message}</div>}

        {status === "loading" ? (
          <div className="empty-state compact">{t("loading")}</div>
        ) : (
          <>
            <div className="purchase-table" style={{ maxHeight: 300, overflowY: "auto" }}>
              <div className="purchase-row purchase-head">
                <span>{t("product")}</span>
                <span>{t("quantity")}</span>
                <span>{t("unitCost")}</span>
                <span>{t("sellingPrice")}</span>
                <span>{t("expiryDate")}</span>
                <span>{t("total")}</span>
                <span />
              </div>
              {lines.map((line) => (
                <div className="purchase-row animated-line" key={line.key}>
                  <span>{line.productName}</span>
                  <input
                    type="number"
                    min="0.001"
                    step="0.001"
                    value={line.quantity}
                    onChange={(event) => updateLine(line.key, { quantity: Number(event.target.value) || 0 })}
                  />
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={line.unitCost}
                    onChange={(event) => updateLine(line.key, { unitCost: Number(event.target.value) || 0 })}
                  />
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={line.sellingPrice ?? ""}
                    onChange={(event) =>
                      updateLine(line.key, {
                        sellingPrice: event.target.value.trim() ? Number(event.target.value) : null,
                      })
                    }
                  />
                  <JalaliDatePicker
                    value={line.expiryDate}
                    onChange={(isoDate) => updateLine(line.key, { expiryDate: isoDate })}
                  />
                  <strong>{money(line.quantity * line.unitCost)}</strong>
                  <button
                    type="button"
                    className="icon-button danger"
                    disabled={lines.length === 1}
                    onClick={() => removeLine(line.key)}
                    aria-label={t("remove")}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>

            <label className="field">
              <span>{t("addLine")}</span>
              <ProductCombobox value={0} products={products} onChange={addLine} onProductCreated={handleProductCreated} />
            </label>

            <label className="field">
              <span>{t("reasonForEdit")}</span>
              <textarea
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder={t("reasonPlaceholder")}
                rows={2}
              />
            </label>

            <div className="total-row">
              <span>{t("total")}</span>
              <strong>{money(total)}</strong>
            </div>
          </>
        )}

        <div className="form-actions">
          <button className="secondary-button" onClick={onClose}>
            {t("cancel")}
          </button>
          <button
            className={`primary-button ${status === "submitting" ? "is-loading" : ""}`}
            disabled={!lines.length || status === "submitting" || status === "loading"}
            onClick={handleSubmit}
          >
            {status === "submitting" ? t("loading") : t("saveEdit")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
