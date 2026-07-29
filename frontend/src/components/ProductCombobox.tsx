import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Plus, Search } from "lucide-react";
import type { Product } from "../types";
import { useI18n } from "../i18n";
import { QuickAddProductModal } from "./QuickAddProductModal";

type ProductComboboxProps = {
  value: number;
  products: Product[];
  onChange: (productId: number) => void;
  disabled?: boolean;
  /** Fires with the full freshly-created product (not just its id) when a
   * new product is made via the quick-add flow below. Callers that need
   * the row updated with real cost/sale price right away (see
   * Purchases.tsx) should use this instead of relying on `onChange` +
   * their own `products` list — that list won't include the brand-new
   * product until the next fetch, so looking it up by id there would
   * silently resolve to nothing. Optional: falls back to plain
   * `onChange(product.id)` if not provided. */
  onProductCreated?: (product: Product) => void;
};

const DROPDOWN_GAP = 6;
const ESTIMATED_DROPDOWN_HEIGHT = 320;

export function ProductCombobox({
  value,
  products,
  onChange,
  disabled,
  onProductCreated,
}: ProductComboboxProps) {
  const { t, direction } = useI18n();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [showQuickAdd, setShowQuickAdd] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number; width: number; above: boolean } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const selected = products.find((p) => p.id === value);

  const filtered = products.filter((p) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      p.name.toLowerCase().includes(q) ||
      (p.barcode && p.barcode.toLowerCase().includes(q)) ||
      (p.brand && p.brand.toLowerCase().includes(q))
    );
  });

  const updatePosition = useCallback(() => {
    if (!open || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const spaceBelow = viewportHeight - rect.bottom;
    const spaceAbove = rect.top;
    const above = spaceBelow < ESTIMATED_DROPDOWN_HEIGHT && spaceAbove > spaceBelow;
    setPosition({
      top: above ? rect.top - DROPDOWN_GAP : rect.bottom + DROPDOWN_GAP,
      left: rect.left,
      width: rect.width,
      above,
    });
  }, [open]);

  useEffect(() => {
    if (!open) {
      setPosition(null);
      return;
    }
    updatePosition();
    const handleScroll = () => updatePosition();
    const handleResize = () => updatePosition();
    // Capture scroll events from any ancestor
    document.addEventListener("scroll", handleScroll, true);
    window.addEventListener("resize", handleResize);
    return () => {
      document.removeEventListener("scroll", handleScroll, true);
      window.removeEventListener("resize", handleResize);
    };
  }, [open, updatePosition]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        // Also check if click is inside the portal dropdown
        const portal = document.querySelector(".combobox-dropdown-portal");
        if (portal && portal.contains(e.target as Node)) return;
        setOpen(false);
        setSearch("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (open && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [open]);

  function handleSelect(productId: number) {
    onChange(productId);
    setOpen(false);
    setSearch("");
  }

  function handleProductCreated(product: Product) {
    if (onProductCreated) {
      onProductCreated(product);
    } else {
      onChange(product.id);
    }
    setShowQuickAdd(false);
    setOpen(false);
    setSearch("");
  }

  // Close dropdown when any modal is opened (via custom event)
  useEffect(() => {
    function handleCloseAll() {
      setOpen(false);
      setSearch("");
    }
    document.addEventListener("close-all-dropdowns", handleCloseAll);
    return () => document.removeEventListener("close-all-dropdowns", handleCloseAll);
  }, []);

  const dropdownContent = open && position ? (
    <div
      className="combobox-dropdown-portal"
      style={{
        top: position.above ? `${position.top}px` : `${position.top}px`,
        left: `${position.left}px`,
        width: `${position.width}px`,
        transformOrigin: position.above ? "bottom" : "top",
      }}
    >
      <div className="combobox-search-wrap">
        <Search size={15} className="combobox-search-icon" />
        <input
          ref={searchInputRef}
          className="combobox-search"
          type="text"
          placeholder={t("searchProducts")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setOpen(false);
            }
            if (e.key === "Enter" && filtered.length > 0) {
              handleSelect(filtered[0].id);
            }
          }}
        />
      </div>
      <div className="combobox-options">
        {filtered.length === 0 ? (
          <div className="combobox-no-results">
            {t("noProducts")}
          </div>
        ) : (
          filtered.map((product) => (
            <div
              key={product.id}
              className={`combobox-option ${
                product.id === value ? "selected" : ""
              }`}
              onClick={() => handleSelect(product.id)}
            >
              <div className="combobox-option-name">{product.name}</div>
              <div className="combobox-option-meta">
                {product.brand && <span>{product.brand}</span>}
                {product.barcode && <span>{product.barcode}</span>}
              </div>
            </div>
          ))
        )}
      </div>
      <div
        className="combobox-quick-add"
              onClick={() => {
                // Dispatch event to close all other dropdowns before opening modal
                document.dispatchEvent(new CustomEvent("close-all-dropdowns"));
                setShowQuickAdd(true);
              }}
      >
        <Plus size={15} />
        <span>{t("quickAddProduct")}</span>
      </div>
    </div>
  ) : null;

  return (
    <>
      <div className="combobox-container" ref={containerRef}>
        <div
          className={`combobox-trigger ${open ? "combobox-open" : ""}`}
          onClick={() => {
            if (!disabled) {
              setOpen(!open);
              if (!open) {
                // Position will be recalculated by the effect
              }
            }
          }}
          role="combobox"
          aria-expanded={open}
          tabIndex={disabled ? -1 : 0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              if (!disabled) setOpen(!open);
            }
            if (e.key === "Escape") {
              setOpen(false);
            }
          }}
        >
          <span className={`combobox-value ${!selected ? "placeholder" : ""}`}>
            {selected ? selected.name : t("chooseProduct")}
          </span>
          <ChevronDown size={16} className="combobox-arrow" />
        </div>
      </div>

      {open && position && createPortal(dropdownContent, document.body)}

      {showQuickAdd && (
        <QuickAddProductModal
          products={products}
          onCreated={handleProductCreated}
          onClose={() => setShowQuickAdd(false)}
        />
      )}
    </>
  );
}