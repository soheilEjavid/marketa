import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  GitMerge,
  Layers,
  Package,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { deactivateProduct, getCategories, getProducts, updateProduct } from "../api";
import { useI18n } from "../i18n";
import type { Category, Product } from "../types";
import { Modal } from "../components/Modal";
import { CategoryManagerModal } from "../components/CategoryManagerModal";
import { ProductFormModal } from "../components/ProductFormModal";
import { getStockStatus } from "../lib/stockStatus";
import { daysUntilExpiry, getExpiryStatus } from "../lib/expiryStatus";
import { calculateMarginPct, formatMarginPct, getMarginStatus } from "../lib/margin";
import { isoToJalaliStr } from "../utils/jalali";
import { canManageProducts } from "../permissions";
import { getSession } from "../session";

type SortKey = "name" | "purchase_price" | "sale_price" | "stock_quantity";

export function Products() {
  const { t, money, number, language } = useI18n();
  const canManage = canManageProducts(getSession()?.role ?? "");
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [showInactive, setShowInactive] = useState(false);
  // Persisted like the dashboard-widget visibility toggles in
  // lib/dashboardWidgets.ts (localStorage — the project's established
  // pattern for filter/preference state that must survive a refresh; this
  // page had no existing persisted filter of its own to follow). A one-shot
  // hand-off key ("marketa-products-filter" = "expiry") is set by the
  // Dashboard widget and the Reports "نزدیک انقضا" tab's "مشاهده همه" button;
  // consumed once here, then cleared so it doesn't stick beyond that one
  // navigation — the *toggle itself* is what persists afterward.
  const [expiryFilterOnly, setExpiryFilterOnly] = useState<boolean>(() => {
    try {
      if (localStorage.getItem("marketa-products-filter") === "expiry") {
        localStorage.removeItem("marketa-products-filter");
        localStorage.setItem("marketa-products-expiry-filter", "true");
        return true;
      }
      return localStorage.getItem("marketa-products-expiry-filter") === "true";
    } catch {
      return false;
    }
  });

  function toggleExpiryFilter(value: boolean) {
    setExpiryFilterOnly(value);
    try {
      localStorage.setItem("marketa-products-expiry-filter", String(value));
    } catch {
      // localStorage unavailable — filter still works for this session.
    }
  }
  const [sortConfig, setSortConfig] = useState<{ key: SortKey; dir: "asc" | "desc" }>({
    key: "name",
    dir: "asc",
  });

  const [showForm, setShowForm] = useState(false);
  const [showCategoryManager, setShowCategoryManager] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [deletingProduct, setDeletingProduct] = useState<Product | null>(null);
  const [deactivating, setDeactivating] = useState(false);

  const [collapsingId, setCollapsingId] = useState<number | null>(null);
  const [collapsing, setCollapsing] = useState(false);

  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  function loadProducts() {
    setLoading(true);
    return getProducts({ activeOnly: !showInactive })
      .then(setProducts)
      .catch(() => {
        setStatus("error");
        setMessage(t("apiError"));
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadProducts();
    getCategories().then(setCategories).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showInactive]);

  const categoryById = useMemo(
    () => new Map(categories.map((category) => [category.id, category.name])),
    [categories],
  );

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return products.filter((product) => {
      if (categoryFilter && product.category_id !== Number(categoryFilter)) return false;
      // Full expiry-tracking view: every expiry-dated product, all statuses
      // (including "green", far from expiring) — not just the red/orange
      // subset the dashboard widget/report tab focus on.
      if (expiryFilterOnly && !product.expiration_date) return false;
      if (!query) return true;
      return (
        product.name.toLowerCase().includes(query) ||
        product.barcode?.toLowerCase().includes(query) ||
        product.brand?.toLowerCase().includes(query) ||
        product.sku?.toLowerCase().includes(query)
      );
    });
  }, [products, search, categoryFilter, expiryFilterOnly]);

  const sorted = useMemo(() => {
    const list = [...filtered];
    list.sort((a, b) => {
      const cmp =
        sortConfig.key === "name"
          ? a.name.localeCompare(b.name)
          : Number(a[sortConfig.key]) - Number(b[sortConfig.key]);
      return sortConfig.dir === "asc" ? cmp : -cmp;
    });
    return list;
  }, [filtered, sortConfig]);

  function toggleSort(key: SortKey) {
    setSortConfig((current) =>
      current.key === key
        ? { key, dir: current.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "asc" },
    );
  }

  function sortIndicator(key: SortKey) {
    if (sortConfig.key !== key) return null;
    return sortConfig.dir === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />;
  }

  function openCreate() {
    setEditingProduct(null);
    setShowForm(true);
  }

  function openEdit(product: Product) {
    setEditingProduct(product);
    setShowForm(true);
  }

  function handleSaved(product: Product) {
    setProducts((current) => {
      const exists = current.some((item) => item.id === product.id);
      return exists
        ? current.map((item) => (item.id === product.id ? product : item))
        : [...current, product];
    });
    setShowForm(false);
    setEditingProduct(null);
    setStatus("success");
    setMessage(t("productSaved"));
  }

  function handleViewConflict(target: Product) {
    setEditingProduct(target);
    setShowForm(true);
  }

  async function confirmDeactivate() {
    if (!deletingProduct) return;
    setDeactivating(true);
    try {
      const updated = await deactivateProduct(deletingProduct.id);
      setProducts((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setDeletingProduct(null);
      setStatus("success");
      setMessage(t("productDeactivated"));
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : t("apiError"));
    } finally {
      setDeactivating(false);
    }
  }

  async function handleReactivate(product: Product) {
    try {
      const updated = await updateProduct(product.id, { is_active: true });
      setProducts((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : t("apiError"));
    }
  }

  async function handleCollapse(product: Product, tier: "old" | "new") {
    setCollapsing(true);
    try {
      const updated = await updateProduct(product.id, { collapse_to_tier: tier });
      setProducts((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setCollapsingId(null);
    } catch {
      // Leave the confirm UI open so the manager can retry.
    } finally {
      setCollapsing(false);
    }
  }

  const hasAnyProducts = products.length > 0;

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("products")}</p>
          <h1>{t("products")}</h1>
        </div>
        {canManage && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="secondary-button" onClick={() => setShowCategoryManager(true)}>
              <Layers size={18} />
              {t("manageCategories")}
            </button>
            <button className="primary-button" onClick={openCreate}>
              <Plus size={18} />
              {t("addProduct")}
            </button>
          </div>
        )}
      </header>

      {message && (
        <div className={`feedback-banner ${status}`}>
          {message}
        </div>
      )}

      <div className="product-filters">
        <label className="search-field">
          <Search size={18} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("searchProductsCatalog")}
          />
        </label>
        <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
          <option value="">{t("allCategories")}</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>
        <label className="checkbox-field product-filter-toggle">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(event) => setShowInactive(event.target.checked)}
          />
          <span>{t("showInactive")}</span>
        </label>
        <label className="checkbox-field product-filter-toggle">
          <input
            type="checkbox"
            checked={expiryFilterOnly}
            onChange={(event) => toggleExpiryFilter(event.target.checked)}
          />
          <span>{t("nearExpiryTitle")}</span>
        </label>
      </div>

      <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
        <div className="inventory-table">
          <div className="inventory-row inventory-head product-columns">
            <button type="button" className="sort-header" onClick={() => toggleSort("name")}>
              {t("product")} {sortIndicator("name")}
            </button>
            <span>{t("barcode")}</span>
            <button type="button" className="sort-header" onClick={() => toggleSort("purchase_price")}>
              {t("purchasePrice")} {sortIndicator("purchase_price")}
            </button>
            <button type="button" className="sort-header" onClick={() => toggleSort("sale_price")}>
              {t("salePrice")} {sortIndicator("sale_price")}
            </button>
            <span>{t("marginPct")}</span>
            <button type="button" className="sort-header" onClick={() => toggleSort("stock_quantity")}>
              {t("stock")} {sortIndicator("stock_quantity")}
            </button>
            <span />
          </div>

          {loading ? (
            <div className="empty-state">
              <p>{t("loading")}</p>
            </div>
          ) : !hasAnyProducts ? (
            <div className="empty-state">
              <Package size={32} />
              <p>{t("noProducts")}</p>
            </div>
          ) : sorted.length === 0 ? (
            <div className="empty-state">
              <Search size={32} />
              <p>{t("noSearchResults")}</p>
            </div>
          ) : (
            sorted.map((product) => {
              const stock = Number(product.stock_quantity);
              const threshold = Number(product.low_stock_threshold) || 0;
              const stockStatus = getStockStatus(stock, threshold);
              const stockClass = stockStatus === "ok" ? "stock-value" : `stock-value ${stockStatus}`;
              const oldStockEstimate = product.old_price_stock_estimate;
              const categoryName = product.category_id ? categoryById.get(product.category_id) : undefined;

              return (
                <div
                  className={`inventory-row product-columns animated-line ${!product.is_active ? "row-inactive" : ""}`}
                  key={product.id}
                >
                  <div className="transaction-product">
                    <div
                      className="product-avatar"
                      style={
                        product.image_url
                          ? { backgroundImage: `url(${product.image_url})`, backgroundSize: "cover" }
                          : undefined
                      }
                    >
                      {!product.image_url && product.name.charAt(0)}
                    </div>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                        <strong>{product.name}</strong>
                        {product.is_dual_priced && (
                          <span className="dual-price-badge">
                            <Layers size={13} />
                            {t("dualPriceBadge")}
                          </span>
                        )}
                        {!product.is_active && (
                          <span className="status-pill">{t("inactive")}</span>
                        )}
                        {product.expiration_date && (() => {
                          const expiryStatus = getExpiryStatus(daysUntilExpiry(product.expiration_date));
                          const daysLeft = daysUntilExpiry(product.expiration_date);
                          return (
                            <span className={`expiry-status-badge ${expiryStatus}`}>
                              {expiryStatus === "expired"
                                ? t("alreadyExpiredLabel")
                                : `${isoToJalaliStr(product.expiration_date)} · ${t("daysRemainingLabel").replace("{days}", number(daysLeft))}`}
                            </span>
                          );
                        })()}
                      </div>
                      {(product.brand || categoryName) && (
                        <small style={{ display: "block", color: "var(--muted)", fontSize: 11 }}>
                          {[product.brand, categoryName].filter(Boolean).join(" · ")}
                        </small>
                      )}
                      {product.is_dual_priced && oldStockEstimate !== null && oldStockEstimate !== undefined && (
                        <span
                          className={`old-stock-estimate ${oldStockEstimate <= 0 ? "exhausted" : ""}`}
                          style={{ marginTop: 4 }}
                          title={t("dualPriceOldStockEstimateWhy")}
                        >
                          {oldStockEstimate > 0
                            ? t("dualPriceOldStockEstimate").replace("{count}", number(oldStockEstimate))
                            : t("dualPriceOldStockExhausted")}
                        </span>
                      )}
                    </div>
                  </div>
                  <span>{product.barcode || "—"}</span>
                  <span>
                    {product.is_dual_priced
                      ? `${money(Number(product.old_purchase_price))} → ${money(Number(product.purchase_price))}`
                      : money(Number(product.purchase_price))}
                  </span>
                  <span>
                    {product.is_dual_priced
                      ? `${money(Number(product.old_sale_price))} → ${money(Number(product.sale_price))}`
                      : money(Number(product.sale_price))}
                  </span>
                  <span>
                    {(() => {
                      const marginPct = calculateMarginPct(Number(product.sale_price), Number(product.purchase_price));
                      if (marginPct === null) return "—";
                      return (
                        <span className={`margin-value ${getMarginStatus(marginPct)}`}>
                          {formatMarginPct(marginPct, language, number)}
                        </span>
                      );
                    })()}
                  </span>
                  <span className={stockClass}>{number(stock)}</span>
                  <div className="action-buttons">
                    {collapsingId === product.id ? (
                      <div className="collapse-confirm">
                        <button disabled={collapsing} onClick={() => handleCollapse(product, "old")}>
                          {t("dualPriceKeepOld")}
                        </button>
                        <button disabled={collapsing} onClick={() => handleCollapse(product, "new")}>
                          {t("dualPriceKeepNew")}
                        </button>
                      </div>
                    ) : (
                      <>
                        <button className="icon-button" title={t("edit")} onClick={() => openEdit(product)}>
                          <Pencil size={16} />
                        </button>
                        {product.is_active ? (
                          <button
                            className="icon-button danger"
                            title={t("deactivateProduct")}
                            onClick={() => setDeletingProduct(product)}
                          >
                            <Trash2 size={16} />
                          </button>
                        ) : (
                          <button
                            className="icon-button"
                            title={t("reactivateProduct")}
                            onClick={() => handleReactivate(product)}
                          >
                            <RotateCcw size={16} />
                          </button>
                        )}
                        {product.is_dual_priced && (
                          <button
                            className="icon-button"
                            title={t("dualPriceCollapse")}
                            aria-label={t("dualPriceCollapse")}
                            onClick={() => setCollapsingId(product.id)}
                          >
                            <GitMerge size={16} />
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </section>

      {showForm && (
        <ProductFormModal
          key={editingProduct?.id ?? "new"}
          product={editingProduct}
          categories={categories}
          products={products}
          onSaved={handleSaved}
          onClose={() => {
            setShowForm(false);
            setEditingProduct(null);
          }}
          onCategoryCreated={(category) => setCategories((current) => [...current, category])}
          onViewProduct={handleViewConflict}
        />
      )}

      {showCategoryManager && (
        <CategoryManagerModal
          categories={categories}
          onClose={() => setShowCategoryManager(false)}
          onCategoriesChanged={setCategories}
        />
      )}

      {deletingProduct && (
        <Modal onClose={() => setDeletingProduct(null)}>
          <div
            className="party-form"
            style={{ width: "min(440px, 100%)" }}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="panel-heading">
              <h2>{t("deactivateProductConfirmTitle")}</h2>
              <button className="icon-button" onClick={() => setDeletingProduct(null)} aria-label={t("cancel")}>
                <X size={18} />
              </button>
            </div>
            <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("deactivateProductConfirmBody")}</p>
            <div className="form-actions">
              <button className="secondary-button" onClick={() => setDeletingProduct(null)}>
                {t("cancel")}
              </button>
              <button className="primary-button" disabled={deactivating} onClick={confirmDeactivate}>
                {deactivating ? t("loading") : t("confirmDeactivate")}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </main>
  );
}
