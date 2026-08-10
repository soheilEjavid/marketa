import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import { History, ImagePlus, Layers, X } from "lucide-react";

import { createCategory, createProduct, getAuditLogs, updateProduct, ApiError } from "../api";
import { useI18n } from "../i18n";
import { calculateMarginPct, formatMarginPct } from "../lib/margin";
import { JalaliDatePicker } from "./JalaliDatePicker";
import { Modal } from "./Modal";
import type { AuditLogEntry, Category, Product } from "../types";
import { AmountInput } from "./AmountInput";

type ProductFormModalProps = {
  /** Present => edit mode; absent/null => create mode. */
  product?: Product | null;
  categories: Category[];
  /** Existing products, used for live barcode/SKU duplicate checks and brand suggestions. */
  products?: Product[];
  /** Quick-add context: hides advanced sections behind a toggle. */
  compact?: boolean;
  onSaved: (product: Product) => void;
  onClose: () => void;
  onCategoryCreated?: (category: Category) => void;
  /** Called when the user wants to go edit a conflicting product instead. */
  onViewProduct?: (product: Product) => void;
};

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

function toInputString(value: string | null | undefined): string {
  return value ?? "";
}

function resizeImageToDataUrl(file: File, maxDimension: number, quality: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("read failed"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("decode failed"));
      img.onload = () => {
        const scale = Math.min(1, maxDimension / Math.max(img.width, img.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("canvas unsupported"));
          return;
        }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL("image/jpeg", quality));
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);
  });
}

function generateSkuSuggestion(): string {
  return `P-${Date.now().toString(36).toUpperCase()}${Math.floor(10 + Math.random() * 90)}`;
}

export function ProductFormModal({
  product,
  categories,
  products = [],
  compact = false,
  onSaved,
  onClose,
  onCategoryCreated,
  onViewProduct,
}: ProductFormModalProps) {
  const { t, money, language, number } = useI18n();
  const isEdit = Boolean(product);

  const [name, setName] = useState(product?.name ?? "");
  const [categoryId, setCategoryId] = useState<number | null>(product?.category_id ?? null);
  const [brand, setBrand] = useState(toInputString(product?.brand));
  const [barcode, setBarcode] = useState(toInputString(product?.barcode));
  const [sku, setSku] = useState(toInputString(product?.sku));
  const [purchasePrice, setPurchasePrice] = useState(product?.purchase_price ?? "");
  const [salePrice, setSalePrice] = useState(product?.sale_price ?? "");
  const [minSalePrice, setMinSalePrice] = useState(toInputString(product?.min_sale_price));
  const [unit, setUnit] = useState(toInputString(product?.unit));
  const [isWeighted, setIsWeighted] = useState(product?.is_weighted ?? false);
  const [stockQuantity, setStockQuantity] = useState(product?.stock_quantity ?? "0");
  const [lowStockThreshold, setLowStockThreshold] = useState(toInputString(product?.low_stock_threshold) || "0");
  const [packagingUnitLabel, setPackagingUnitLabel] = useState(toInputString(product?.packaging_unit_label));
  const [packagingUnitQuantity, setPackagingUnitQuantity] = useState(toInputString(product?.packaging_unit_quantity));
  const [expirationDate, setExpirationDate] = useState(toInputString(product?.expiration_date));
  const [imageUrl, setImageUrl] = useState<string | null>(product?.image_url ?? null);
  const [description, setDescription] = useState(toInputString(product?.description));
  const [isActive, setIsActive] = useState(product?.is_active ?? true);
  const [loyaltyPointMultiplier, setLoyaltyPointMultiplier] = useState(
    toInputString(product?.loyalty_point_multiplier),
  );

  const [showAdvanced, setShowAdvanced] = useState(!compact);
  const [showNewCategory, setShowNewCategory] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState("");
  const [categorySaving, setCategorySaving] = useState(false);

  const [confirmedBelowPurchase, setConfirmedBelowPurchase] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState("");
  const [saving, setSaving] = useState(false);
  const [imageError, setImageError] = useState("");

  const [showCollapseConfirm, setShowCollapseConfirm] = useState(false);
  const [collapsing, setCollapsing] = useState(false);

  const [showHistory, setShowHistory] = useState(false);
  const [historyEntries, setHistoryEntries] = useState<AuditLogEntry[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");

  useEffect(() => {
    setConfirmedBelowPurchase(false);
  }, [purchasePrice, salePrice]);

  const purchaseNumber = Number(purchasePrice) || 0;
  const saleNumber = Number(salePrice) || 0;
  // Margin-on-sales, matching lib/margin.ts — the same formula used by the
  // Products page column, sale-detail views, and Reports margin figures.
  const margin = calculateMarginPct(saleNumber, purchaseNumber);
  const belowPurchase = purchaseNumber > 0 && saleNumber > 0 && saleNumber < purchaseNumber;

  const barcodeConflict = useMemo(() => {
    const trimmed = barcode.trim();
    if (!trimmed) return undefined;
    return products.find((p) => p.id !== product?.id && p.barcode?.trim() === trimmed);
  }, [barcode, products, product?.id]);

  const skuConflict = useMemo(() => {
    const trimmed = sku.trim();
    if (!trimmed) return undefined;
    return products.find((p) => p.id !== product?.id && p.sku?.trim() === trimmed);
  }, [sku, products, product?.id]);

  const brandSuggestions = useMemo(() => {
    const set = new Set<string>();
    for (const p of products) {
      if (p.brand?.trim()) set.add(p.brand.trim());
    }
    return Array.from(set);
  }, [products]);

  const unitSuggestions = [
    t("unitPiece"),
    t("unitKg"),
    t("unitGram"),
    t("unitLiter"),
    t("unitPackage"),
    t("unitCarton"),
    t("unitMeter"),
  ];

  async function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setImageError("");
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError(t("imageTooLarge"));
      return;
    }
    try {
      const dataUrl = await resizeImageToDataUrl(file, 320, 0.82);
      setImageUrl(dataUrl);
    } catch {
      setImageError(t("imageTooLarge"));
    }
  }

  async function handleCollapse(tier: "old" | "new") {
    if (!product) return;
    setCollapsing(true);
    try {
      const updated = await updateProduct(product.id, { collapse_to_tier: tier });
      onSaved(updated);
    } catch (error) {
      setGeneralError(error instanceof Error ? error.message : t("apiError"));
      setCollapsing(false);
      setShowCollapseConfirm(false);
    }
  }

  async function toggleHistory() {
    if (showHistory) {
      setShowHistory(false);
      return;
    }
    setShowHistory(true);
    if (historyEntries !== null || !product) return;
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const entries = await getAuditLogs({ entityType: "product", entityId: product.id });
      setHistoryEntries(entries);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : t("priceHistoryError"));
    } finally {
      setHistoryLoading(false);
    }
  }

  async function handleCreateCategory() {
    if (!newCategoryName.trim()) return;
    setCategorySaving(true);
    try {
      const category = await createCategory({ name: newCategoryName.trim() });
      onCategoryCreated?.(category);
      setCategoryId(category.id);
      setShowNewCategory(false);
      setNewCategoryName("");
      setErrors((prev) => ({ ...prev, category: "" }));
    } catch (error) {
      setErrors((prev) => ({
        ...prev,
        category: error instanceof Error ? error.message : t("apiError"),
      }));
    } finally {
      setCategorySaving(false);
    }
  }

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = t("requiredField");
    if (!categoryId) next.category = t("requiredField");
    if (purchasePrice === "" || Number.isNaN(Number(purchasePrice))) next.purchasePrice = t("requiredField");
    if (salePrice === "" || Number.isNaN(Number(salePrice))) next.salePrice = t("requiredField");
    if (barcodeConflict) next.barcode = t("barcodeAlreadyUsedFor").replace("{name}", barcodeConflict.name);
    if (skuConflict) next.sku = t("skuAlreadyUsedFor").replace("{name}", skuConflict.name);
    return next;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setGeneralError("");
    const validationErrors = validate();
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;

    if (belowPurchase && !confirmedBelowPurchase) {
      setConfirmedBelowPurchase(true);
      return;
    }

    setSaving(true);
    try {
      const sharedFields = {
        name: name.trim(),
        category_id: categoryId,
        brand: brand.trim() || null,
        barcode: barcode.trim() || null,
        sku: sku.trim() || null,
        purchase_price: Number(purchasePrice),
        sale_price: Number(salePrice),
        min_sale_price: minSalePrice.trim() ? Number(minSalePrice) : null,
        low_stock_threshold: Number(lowStockThreshold) || 0,
        is_weighted: isWeighted,
        unit: unit.trim() || null,
        packaging_unit_label: packagingUnitLabel.trim() || null,
        packaging_unit_quantity: packagingUnitQuantity.trim() ? Number(packagingUnitQuantity) : null,
        expiration_date: expirationDate.trim() || null,
        image_url: imageUrl,
        description: description.trim() || null,
        is_active: isActive,
        loyalty_point_multiplier: loyaltyPointMultiplier.trim() ? Number(loyaltyPointMultiplier) : null,
      };
      // Stock can't be edited directly once a product exists — it only
      // changes via purchase/sale/adjustment — so it's only ever sent here
      // on create, never on update.
      const saved = isEdit && product
        ? await updateProduct(product.id, sharedFields)
        : await createProduct({ ...sharedFields, stock_quantity: Number(stockQuantity) || 0 });
      onSaved(saved);
    } catch (error) {
      if (error instanceof ApiError && error.message.toLowerCase().includes("barcode")) {
        setErrors((prev) => ({ ...prev, barcode: error.message }));
      } else if (error instanceof ApiError && error.message.toLowerCase().includes("sku")) {
        setErrors((prev) => ({ ...prev, sku: error.message }));
      } else {
        setGeneralError(error instanceof Error ? error.message : t("apiError"));
      }
    } finally {
      setSaving(false);
    }
  }

  const saveLabel = saving
    ? t("loading")
    : belowPurchase && confirmedBelowPurchase
      ? t("confirmAnyway")
      : t("save");

  return (
    <Modal onClose={onClose}>
      <form
        className="party-form product-form"
        onSubmit={handleSubmit}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="panel-heading">
          <h2>{t(isEdit ? "editProduct" : "addProduct")}</h2>
          <button type="button" className="icon-button" onClick={onClose} aria-label={t("cancel")}>
            <X size={18} />
          </button>
        </div>

        {generalError && <div className="feedback-banner error">{generalError}</div>}

        <div className="form-section">
          <h4 className="form-section-title">{t("sectionBasicInfo")}</h4>
          <div className="form-grid">
            <label className="field full-span">
              <span>{t("productName")} *</span>
              <input
                autoFocus
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={t("productNamePlaceholder")}
              />
              {errors.name && <small className="field-error">{errors.name}</small>}
            </label>

            <label className="field">
              <span>{t("category")} *</span>
              {!showNewCategory ? (
                <select
                  value={categoryId ?? ""}
                  onChange={(event) => {
                    if (event.target.value === "__new__") {
                      setShowNewCategory(true);
                    } else {
                      setCategoryId(event.target.value ? Number(event.target.value) : null);
                    }
                  }}
                >
                  <option value="">{t("chooseCategory")}</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
                  <option value="__new__">+ {t("addNewCategory")}</option>
                </select>
              ) : (
                <div style={{ display: "flex", gap: 6 }}>
                  <input
                    autoFocus
                    value={newCategoryName}
                    onChange={(event) => setNewCategoryName(event.target.value)}
                    placeholder={t("newCategoryName")}
                  />
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={categorySaving || !newCategoryName.trim()}
                    onClick={handleCreateCategory}
                  >
                    {categorySaving ? t("loading") : t("save")}
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => {
                      setShowNewCategory(false);
                      setNewCategoryName("");
                    }}
                    aria-label={t("cancel")}
                  >
                    <X size={16} />
                  </button>
                </div>
              )}
              {errors.category && <small className="field-error">{errors.category}</small>}
            </label>

            <label className="field">
              <span>{t("brand")}</span>
              <input
                list="product-form-brands"
                value={brand}
                onChange={(event) => setBrand(event.target.value)}
                placeholder={t("brandPlaceholder")}
              />
              <datalist id="product-form-brands">
                {brandSuggestions.map((value) => (
                  <option value={value} key={value} />
                ))}
              </datalist>
            </label>

            <label className="field">
              <span>{t("barcode")}</span>
              <input
                value={barcode}
                onChange={(event) => setBarcode(event.target.value)}
                placeholder={t("barcodePlaceholder")}
              />
              {barcodeConflict && (
                <small className="field-warning">
                  {t("barcodeAlreadyUsedFor").replace("{name}", barcodeConflict.name)}
                  {onViewProduct && (
                    <button
                      type="button"
                      className="inline-link-button"
                      onClick={() => onViewProduct(barcodeConflict)}
                    >
                      {t("viewProduct")}
                    </button>
                  )}
                </small>
              )}
            </label>

            <label className="field">
              <span>{t("sku")}</span>
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  value={sku}
                  onChange={(event) => setSku(event.target.value)}
                  placeholder={t("skuPlaceholder")}
                />
                <button type="button" className="secondary-button" onClick={() => setSku(generateSkuSuggestion())}>
                  {t("generateSku")}
                </button>
              </div>
              {skuConflict && (
                <small className="field-warning">
                  {t("skuAlreadyUsedFor").replace("{name}", skuConflict.name)}
                  {onViewProduct && (
                    <button
                      type="button"
                      className="inline-link-button"
                      onClick={() => onViewProduct(skuConflict)}
                    >
                      {t("viewProduct")}
                    </button>
                  )}
                </small>
              )}
            </label>
          </div>
        </div>

        <div className="form-section">
          <h4 className="form-section-title" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span>{t("sectionPricing")}</span>
            {isEdit && product && (
              <button
                type="button"
                className="icon-button"
                title={t("viewPriceHistory")}
                aria-label={t("viewPriceHistory")}
                onClick={toggleHistory}
              >
                <History size={14} />
              </button>
            )}
          </h4>

          {showHistory && (
            <div className="price-history-panel">
              {historyLoading ? (
                <small className="field-hint">{t("loading")}</small>
              ) : historyError ? (
                <small className="field-error">{historyError}</small>
              ) : !historyEntries || historyEntries.length === 0 ? (
                <small className="field-hint">{t("priceHistoryEmpty")}</small>
              ) : (
                <ul className="price-history-list">
                  {historyEntries.map((entry) => (
                    <li key={entry.id}>
                      <div className="price-history-entry-head">
                        <strong>{entry.action}</strong>
                        <span>{entry.occurred_at ? new Date(entry.occurred_at).toLocaleString() : ""}</span>
                      </div>
                      {entry.details && <small className="field-hint">{entry.details}</small>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {isEdit && product?.is_dual_priced && (
            <div className="dual-price-product-card">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                <span className="dual-price-badge">
                  <Layers size={13} />
                  {t("dualPriceBadge")}
                </span>
                {!showCollapseConfirm && (
                  <button
                    type="button"
                    className="inline-link-button"
                    onClick={() => setShowCollapseConfirm(true)}
                  >
                    {t("dualPriceCollapse")}
                  </button>
                )}
              </div>
              <div className="price-comparison">
                <span className="old-label">
                  {t("dualPriceOldPrice")}: {money(Number(product.old_sale_price))}
                </span>
                <span className="arrow">→</span>
                <span className="new-label">
                  {t("dualPriceNewPrice")}: {money(Number(product.sale_price))}
                </span>
              </div>
              {showCollapseConfirm && (
                <div className="collapse-confirm">
                  <button type="button" disabled={collapsing} onClick={() => handleCollapse("old")}>
                    {t("dualPriceKeepOld")}
                  </button>
                  <button type="button" disabled={collapsing} onClick={() => handleCollapse("new")}>
                    {t("dualPriceKeepNew")}
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="form-grid">
            <label className="field">
              <span>{t("purchasePrice")} *</span>
              <AmountInput
                min="0"
                value={Number(purchasePrice) || null}
                onChange={(v) => setPurchasePrice(v === null ? "" : String(v))}
              />
              {errors.purchasePrice && <small className="field-error">{errors.purchasePrice}</small>}
            </label>

            <label className="field">
              <span>{t("salePrice")} *</span>
              <AmountInput
                min="0"
                value={Number(salePrice) || null}
                onChange={(v) => setSalePrice(v === null ? "" : String(v))}
              />
              {errors.salePrice && <small className="field-error">{errors.salePrice}</small>}
            </label>

            <div className="field">
              <span>{t("profitMargin")}</span>
              <div className="margin-display">
                {margin === null ? "—" : formatMarginPct(margin, language, number)}
              </div>
            </div>

            {showAdvanced && (
              <label className="field">
                <span>{t("minSalePrice")}</span>
                <AmountInput
                  min="0"
                  value={Number(minSalePrice) || null}
                  onChange={(v) => setMinSalePrice(v === null ? "" : String(v))}
                />
                <small className="field-hint">{t("minSalePriceHint")}</small>
              </label>
            )}

            {belowPurchase && (
              <div className="field-warning full-span price-warning">
                {t("salePriceBelowPurchaseWarning")}
              </div>
            )}
          </div>
        </div>

        <div className="form-section">
          <h4 className="form-section-title">{t("sectionInventory")}</h4>
          <div className="form-grid">
            <label className="field">
              <span>{t("stockQuantity")}</span>
              <input
                type="number"
                min="0"
                step="0.001"
                value={stockQuantity}
                disabled={isEdit}
                title={isEdit ? t("stockQuantityEditLocked") : undefined}
                onChange={(event) => setStockQuantity(event.target.value)}
              />
              {isEdit && <small className="field-hint">{t("stockQuantityEditLocked")}</small>}
            </label>

            {showAdvanced && (
              <>
                <label className="field">
                  <span>{t("unitOfSale")}</span>
                  <input
                    list="product-form-units"
                    value={unit}
                    onChange={(event) => setUnit(event.target.value)}
                  />
                  <datalist id="product-form-units">
                    {unitSuggestions.map((value) => (
                      <option value={value} key={value} />
                    ))}
                  </datalist>
                </label>

                <label className="checkbox-field full-span">
                  <input
                    type="checkbox"
                    checked={isWeighted}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setIsWeighted(checked);
                      // Turning this on with no unit named would leave the
                      // till showing a bare "2.350". Kilogram is the near
                      // universal case; anything already typed is kept.
                      if (checked && !unit.trim()) setUnit(t("unitKg"));
                    }}
                  />
                  <span>{t("soldByWeight")}</span>
                </label>
                <small className="field-hint full-span">{t("soldByWeightHint")}</small>

                <label className="field">
                  <span>{t("lowStockThreshold")}</span>
                  <input
                    type="number"
                    min="0"
                    step="0.001"
                    value={lowStockThreshold}
                    onChange={(event) => setLowStockThreshold(event.target.value)}
                  />
                </label>

                <label className="field">
                  {/* Reuses the existing "expiryDate" label (already used for
                      PurchaseItem.expiry_date in Purchases.tsx) — same
                      concept, no need for a near-duplicate i18n key. */}
                  <span>{t("expiryDate")} ({t("optional")})</span>
                  <JalaliDatePicker value={expirationDate} onChange={setExpirationDate} />
                </label>

                <div className="field full-span">
                  <span>{t("packagingConversion")}</span>
                  <small className="field-hint">{t("packagingConversionHint")}</small>
                  <div className="packaging-conversion-row">
                    <span>1</span>
                    <input
                      value={packagingUnitLabel}
                      onChange={(event) => setPackagingUnitLabel(event.target.value)}
                      placeholder={t("packagingUnitLabelPlaceholder")}
                    />
                    <span>=</span>
                    <input
                      type="number"
                      min="0"
                      step="0.001"
                      value={packagingUnitQuantity}
                      onChange={(event) => setPackagingUnitQuantity(event.target.value)}
                      placeholder={t("packagingUnitQuantity")}
                    />
                    <span>{unit || t("unitOfSale")}</span>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {showAdvanced && (
          <div className="form-section">
            <h4 className="form-section-title">{t("sectionOther")}</h4>
            <div className="form-grid">
              <div className="field">
                <span>{t("productImage")}</span>
                <div className="image-upload-row">
                  {imageUrl ? (
                    <img src={imageUrl} alt="" className="image-upload-preview" />
                  ) : (
                    <div className="image-upload-placeholder">
                      {name ? name.charAt(0) : <ImagePlus size={18} />}
                    </div>
                  )}
                  <div className="image-upload-actions">
                    <label className="secondary-button image-upload-button">
                      {t("uploadImage")}
                      <input
                        type="file"
                        accept="image/*"
                        onChange={handleImageChange}
                        style={{ display: "none" }}
                      />
                    </label>
                    {imageUrl && (
                      <button type="button" className="icon-button danger" onClick={() => setImageUrl(null)}>
                        <X size={15} />
                      </button>
                    )}
                  </div>
                </div>
                {imageError && <small className="field-error">{imageError}</small>}
              </div>

              <label className="field full-span">
                <span>{t("internalNotes")}</span>
                <textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </label>

              <label className="field">
                <span>{t("loyaltyPointMultiplier")} ({t("optional")})</span>
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={loyaltyPointMultiplier}
                  onChange={(event) => setLoyaltyPointMultiplier(event.target.value)}
                  placeholder={t("loyaltyPointMultiplierPlaceholder")}
                />
                <small className="field-hint">{t("loyaltyPointMultiplierHint")}</small>
              </label>

              <label className="checkbox-field full-span">
                <input
                  type="checkbox"
                  checked={isActive}
                  onChange={(event) => setIsActive(event.target.checked)}
                />
                <span>{t("active")}</span>
              </label>
            </div>
          </div>
        )}

        {compact && (
          <button
            type="button"
            className="inline-link-button show-more-fields"
            onClick={() => setShowAdvanced((current) => !current)}
          >
            {showAdvanced ? `− ${t("sectionOther")}` : `+ ${t("sectionInventory")} / ${t("sectionOther")}`}
          </button>
        )}

        <div className="form-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            {t("cancel")}
          </button>
          <button type="submit" className="primary-button" disabled={saving}>
            {saveLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}
