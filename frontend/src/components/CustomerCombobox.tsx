import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Search } from "lucide-react";
import type { Customer } from "../types";
import { useI18n } from "../i18n";

type CustomerComboboxProps = {
  value: number | null;
  customers: Customer[];
  onChange: (customerId: number) => void;
  disabled?: boolean;
};

const DROPDOWN_GAP = 6;
const ESTIMATED_DROPDOWN_HEIGHT = 320;

export function CustomerCombobox({
  value,
  customers,
  onChange,
  disabled,
}: CustomerComboboxProps) {
  const { t, money } = useI18n();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [position, setPosition] = useState<{ top: number; left: number; width: number; above: boolean } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const selected = customers.find((c) => c.id === value);

  const filtered = customers.filter((c) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      c.full_name.toLowerCase().includes(q) ||
      (c.phone && c.phone.toLowerCase().includes(q))
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

  function handleSelect(customerId: number) {
    onChange(customerId);
    setOpen(false);
    setSearch("");
  }

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
        top: `${position.top}px`,
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
          placeholder={t("searchCustomers")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
            if (e.key === "Enter" && filtered.length > 0) handleSelect(filtered[0].id);
          }}
        />
      </div>
      <div className="combobox-options">
        {filtered.length === 0 ? (
          <div className="combobox-no-results">{t("noCustomers")}</div>
        ) : (
          filtered.map((customer) => (
            <div
              key={customer.id}
              className={`combobox-option ${customer.id === value ? "selected" : ""}`}
              onClick={() => handleSelect(customer.id)}
            >
              <div className="combobox-option-name">{customer.full_name}</div>
              <div className="combobox-option-meta">
                {customer.phone && <span>{customer.phone}</span>}
                {Number(customer.balance) > 0 && <span>{money(Number(customer.balance))}</span>}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  ) : null;

  return (
    <>
      <div className="combobox-container" ref={containerRef}>
        <div
          className={`combobox-trigger ${open ? "combobox-open" : ""}`}
          onClick={() => {
            if (!disabled) setOpen(!open);
          }}
          role="combobox"
          aria-expanded={open}
          tabIndex={disabled ? -1 : 0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              if (!disabled) setOpen(!open);
            }
            if (e.key === "Escape") setOpen(false);
          }}
        >
          <span className={`combobox-value ${!selected ? "placeholder" : ""}`}>
            {selected ? selected.full_name : t("chooseCustomer")}
          </span>
          <ChevronDown size={16} className="combobox-arrow" />
        </div>
      </div>

      {open && position && createPortal(dropdownContent, document.body)}
    </>
  );
}
