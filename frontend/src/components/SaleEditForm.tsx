import { useEffect, useState } from "react";
import { Minus, Plus, Trash2, X } from "lucide-react";

import { ApiError, editSale, getProducts } from "../api";
import { useI18n } from "../i18n";
import type { Product, Sale } from "../types";
import { Modal } from "./Modal";
import { ProductCombobox } from "./ProductCombobox";

type SaleEditFormProps = {
  sale: Sale;
  onClose: () => void;
  onSaved: () => void;
};

type EditLine = {
  /** null = a brand-new line being added during this edit. */
  id: number | null;
  product: Product;
  quantity: number;
  unitPrice: number;
  discount: number;
  priceTier?: "old" | "new";
};

export function SaleEditForm({ sale, onClose, onSaved }: SaleEditFormProps) {
  const { t, money, number } = useI18n();
  const [products, setProducts] = useState<Product[]>([]);
  const [lines, setLines] = useState<EditLine[]>([]);
  const [invoiceDiscount, setInvoiceDiscount] = useState(String(sale.discount));
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState<"loading" | "idle" | "submitting" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    getProducts()
      .then((productList) => {
        setProducts(productList);
        setLines(
          sale.items.map((item) => {
            const product = productList.find((p) => p.id === item.product_id) ?? {
              id: item.product_id,
              name: `#${item.product_id}`,
              sale_price: item.unit_price,
              purchase_price: "0",
              stock_quantity: "0",
              is_dual_priced: false,
            } as Product;
            return {
              id: item.id,
              product,
              quantity: Number(item.quantity),
              unitPrice: Number(item.unit_price),
              discount: Number(item.discount),
              priceTier: item.price_tier as "old" | "new" | undefined,
            };
          }),
        );
        setStatus("idle");
      })
      .catch(() => {
        setStatus("error");
        setMessage(t("apiError"));
      });
  }, [sale, t]);

  const invoiceDiscountValue = Number(invoiceDiscount) || 0;
  const subtotal = lines.reduce((sum, line) => sum + line.unitPrice * line.quantity - line.discount, 0);
  const total = Math.max(0, subtotal - invoiceDiscountValue);

  function updateLine(id: number | null, index: number, changes: Partial<EditLine>) {
    setLines((current) =>
      current.map((line, i) => (line.id === id && i === index ? { ...line, ...changes } : line)),
    );
  }

  function removeLine(index: number) {
    setLines((current) => current.filter((_, i) => i !== index));
  }

  function addLineForProduct(product: Product) {
    const priceTier = product.is_dual_priced ? "old" : undefined;
    const unitPrice = product.is_dual_priced
      ? Number(product.old_sale_price ?? product.sale_price)
      : Number(product.sale_price);
    setLines((current) => [...current, { id: null, product, quantity: 1, unitPrice, discount: 0, priceTier }]);
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
      await editSale(sale.id, {
        discount: invoiceDiscountValue,
        reason: reason.trim() || null,
        items: lines.map((line) => ({
          ...(line.id !== null ? { id: line.id } : {}),
          product_id: line.product.id,
          quantity: line.quantity,
          unit_price: line.unitPrice,
          discount: line.discount,
          ...(line.product.is_dual_priced && line.priceTier ? { price_tier: line.priceTier } : {}),
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
      <div className="party-form product-form" onMouseDown={(event) => event.stopPropagation()}>
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
            <div className="cart-lines" style={{ maxHeight: 320, overflowY: "auto" }}>
              {lines.map((line, index) => (
                <div className="cart-line animated-line" key={`${line.id ?? "new"}-${index}`}>
                  <div>
                    <strong>{line.product.name}</strong>
                    <div className="cart-line-discount">
                      <span>{t("unitPrice")}</span>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={line.unitPrice}
                        onChange={(event) =>
                          updateLine(line.id, index, { unitPrice: Number(event.target.value) || 0 })
                        }
                      />
                    </div>
                    <div className="cart-line-discount">
                      <span>{t("itemDiscount")}</span>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={line.discount || ""}
                        placeholder="0"
                        onChange={(event) =>
                          updateLine(line.id, index, { discount: Number(event.target.value) || 0 })
                        }
                      />
                    </div>
                  </div>
                  <div className="quantity-control">
                    <button
                      type="button"
                      onClick={() => updateLine(line.id, index, { quantity: Math.max(1, line.quantity - 1) })}
                    >
                      <Minus size={14} />
                    </button>
                    <span>{number(line.quantity)}</span>
                    <button type="button" onClick={() => updateLine(line.id, index, { quantity: line.quantity + 1 })}>
                      <Plus size={14} />
                    </button>
                  </div>
                  <button
                    type="button"
                    className="icon-button danger"
                    onClick={() => removeLine(index)}
                    aria-label={t("remove")}
                  >
                    <Trash2 size={16} />
                  </button>

                  {line.product.is_dual_priced && (
                    <div className="price-tier-toggle" style={{ gridColumn: "1 / -1" }}>
                      <button
                        type="button"
                        className={`price-tier-button ${line.priceTier === "old" ? "price-tier-selected" : ""}`}
                        onClick={() => updateLine(line.id, index, { priceTier: "old" })}
                      >
                        <span className="tier-label">{t("dualPriceOldPrice")}</span>
                        <span className="tier-price">
                          {money(Number(line.product.old_sale_price ?? line.product.sale_price))}
                        </span>
                      </button>
                      <button
                        type="button"
                        className={`price-tier-button ${line.priceTier === "new" ? "price-tier-selected" : ""}`}
                        onClick={() => updateLine(line.id, index, { priceTier: "new" })}
                      >
                        <span className="tier-label">{t("dualPriceNewPrice")}</span>
                        <span className="tier-price">{money(Number(line.product.sale_price))}</span>
                      </button>
                    </div>
                  )}
                </div>
              ))}
              {!lines.length && <div className="empty-state compact">{t("emptyCart")}</div>}
            </div>

            <label className="field">
              <span>{t("addLine")}</span>
              <ProductCombobox value={0} products={products} onChange={addLine} onProductCreated={handleProductCreated} />
            </label>

            <label className="field">
              <span>{t("invoiceDiscount")}</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={invoiceDiscount}
                onChange={(event) => setInvoiceDiscount(event.target.value)}
              />
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
