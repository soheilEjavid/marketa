import { useEffect, useRef, useState, type MouseEvent } from "react";
import { createPortal } from "react-dom";
import {
  Award,
  BarChart3,
  ChevronsLeft,
  ChevronsRight,
  ContactRound,
  Factory,
  Landmark,
  Languages,
  LayoutDashboard,
  LogOut,
  Package,
  PackagePlus,
  ReceiptText,
  ShoppingBasket,
  UserCog,
  Wallet,
} from "lucide-react";

import { useI18n } from "../i18n";
import { canManageExpenses, canManageUsers, canViewChecks, canViewInventoryHistory, canViewReports } from "../permissions";
import type { Session } from "../session";

export type Page =
  | "dashboard"
  | "sales"
  | "purchases"
  | "products"
  | "inventory"
  | "customers"
  | "loyalty-club"
  | "suppliers"
  | "checks"
  | "reports"
  | "expenses"
  | "users";

type NavItem = {
  page: Page;
  label: string;
  icon: typeof LayoutDashboard;
  visible: (role: string) => boolean;
};

type NavGroup = {
  // Omitted entirely for a standalone top-level item (e.g. dashboard) —
  // matching the "5-7 scannable top-level destinations" sidebar UX
  // convention instead of 11 flat, ungrouped items (see styles.css's
  // nav-group-label rule for the visual treatment).
  groupLabel?: string;
  items: NavItem[];
};

// `visible` mirrors the backend's real read-role set for each page (see
// permissions.ts) — a role that can't call the underlying endpoints
// doesn't get a dead-end nav item pointing at them.
const navigationGroups: NavGroup[] = [
  {
    items: [{ page: "dashboard", label: "dashboard", icon: LayoutDashboard, visible: () => true }],
  },
  {
    groupLabel: "navGroupSalesPurchases",
    items: [
      { page: "sales", label: "sales", icon: ShoppingBasket, visible: () => true },
      { page: "purchases", label: "purchases", icon: PackagePlus, visible: () => true },
    ],
  },
  {
    groupLabel: "navGroupCatalog",
    items: [
      { page: "products", label: "products", icon: Package, visible: () => true },
      { page: "inventory", label: "inventory", icon: ReceiptText, visible: canViewInventoryHistory },
    ],
  },
  {
    groupLabel: "navGroupParties",
    items: [
      { page: "customers", label: "customers", icon: ContactRound, visible: () => true },
      { page: "loyalty-club", label: "loyaltyProgram", icon: Award, visible: canViewReports },
      { page: "suppliers", label: "suppliers", icon: Factory, visible: () => true },
    ],
  },
  {
    groupLabel: "navGroupFinance",
    items: [
      { page: "checks", label: "checks", icon: Landmark, visible: canViewChecks },
      { page: "reports", label: "reports", icon: BarChart3, visible: canViewReports },
      { page: "expenses", label: "expenses", icon: Wallet, visible: canManageExpenses },
    ],
  },
  {
    groupLabel: "navGroupManagement",
    items: [{ page: "users", label: "users", icon: UserCog, visible: canManageUsers }],
  },
];

type SidebarProps = {
  activePage: Page;
  onNavigate: (page: Page) => void;
  session: Session;
  onLogout: () => void;
};

const COLLAPSE_STORAGE_KEY = "marketa-sidebar-collapsed";
const SIDEBAR_WIDTH_EXPANDED = "236px";
const SIDEBAR_WIDTH_COLLAPSED = "76px";
const COLLAPSED_TOOLTIP_LEFT = 88; // SIDEBAR_WIDTH_COLLAPSED (76) + a small gap

export function Sidebar({ activePage, onNavigate, session, onLogout }: SidebarProps) {
  const { language, setLanguage, t } = useI18n();
  const navRef = useRef<HTMLElement>(null);
  // Only true when the nav list actually has more content below the fold
  // — the scroll-fade hint (see .nav-scroll-fade) stays hidden whenever
  // everything already fits, instead of always covering the last item.
  const [hasMoreBelow, setHasMoreBelow] = useState(false);
  // Persisted per-browser (not per-user account) — a click-driven choice,
  // not hover-driven: hover-to-expand on a line-of-business app that's
  // open all day means the sidebar jitters open every time the mouse
  // passes the edge, which is more annoying than useful here.
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1");
  // Collapsed-mode tooltip — rendered through a portal (like
  // CustomerCombobox's dropdown) rather than a CSS ::after, because the
  // real target sits inside <nav>'s own scroll container: any
  // position:absolute popup overflowing that box gets clipped the moment
  // overflow-y:auto is set (overflow-x silently computes to auto too, per
  // the CSS overflow spec, once either axis isn't visible).
  const [tooltip, setTooltip] = useState<{ label: string; top: number } | null>(null);

  useEffect(() => {
    localStorage.setItem(COLLAPSE_STORAGE_KEY, collapsed ? "1" : "0");
    // .app-shell's grid-template-columns reads this variable (see
    // styles.css) — Sidebar owns the collapse state, so it's simplest for
    // it to also own the one CSS variable the parent grid track needs,
    // rather than lifting collapsed state up into App.tsx.
    document.documentElement.style.setProperty(
      "--sidebar-width",
      collapsed ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH_EXPANDED,
    );
    if (!collapsed) setTooltip(null);
  }, [collapsed]);

  useEffect(() => {
    const el = navRef.current;
    if (!el) return;

    function updateFade() {
      if (!el) return;
      setHasMoreBelow(el.scrollHeight - el.scrollTop - el.clientHeight > 1);
    }

    updateFade();
    el.addEventListener("scroll", updateFade);
    window.addEventListener("resize", updateFade);
    return () => {
      el.removeEventListener("scroll", updateFade);
      window.removeEventListener("resize", updateFade);
    };
    // Re-measure whenever the visible item set (role) or the collapsed
    // layout (row sizing changes) could have changed the overflow.
  }, [session.role, collapsed]);

  function showTooltip(event: MouseEvent<HTMLElement>, label: string) {
    if (!collapsed) return;
    const rect = event.currentTarget.getBoundingClientRect();
    setTooltip({ label, top: rect.top + rect.height / 2 });
  }

  function hideTooltip() {
    setTooltip(null);
  }

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <button
        type="button"
        className="sidebar-toggle"
        onClick={() => setCollapsed((current) => !current)}
        aria-label={t(collapsed ? "expandSidebar" : "collapseSidebar")}
        title={t(collapsed ? "expandSidebar" : "collapseSidebar")}
      >
        {collapsed ? <ChevronsRight size={14} /> : <ChevronsLeft size={14} />}
      </button>

      <div className="brand">
        <span className="brand-mark">{session.fullName.charAt(0)}</span>
        <div className="brand-text">
          <strong>{session.fullName}</strong>
          <small>{t(session.role)}</small>
        </div>
      </div>
      <div className="nav-wrap">
        <nav ref={navRef}>
          {navigationGroups.map((group, groupIndex) => {
            const visibleItems = group.items.filter(({ visible }) => visible(session.role));
            if (visibleItems.length === 0) return null;
            return (
              <div className="nav-group" key={group.groupLabel ?? `top-${groupIndex}`}>
                {group.groupLabel && <span className="nav-group-label">{t(group.groupLabel)}</span>}
                {visibleItems.map(({ page, label, icon: Icon }) => (
                  <button
                    className={`nav-item ${activePage === page ? "active" : ""}`}
                    key={page}
                    onClick={() => onNavigate(page)}
                    onMouseEnter={(event) => showTooltip(event, t(label))}
                    onMouseLeave={hideTooltip}
                  >
                    <Icon size={19} strokeWidth={1.8} />
                    <span className="nav-item-label">{t(label)}</span>
                  </button>
                ))}
              </div>
            );
          })}
        </nav>
        <div className={`nav-scroll-fade ${hasMoreBelow ? "visible" : ""}`} aria-hidden="true" />
      </div>
      <div className="sidebar-footer">
        <div
          className="system-status"
          onMouseEnter={(event) => showTooltip(event, `${t("systemOnline")} — ${t("localStore")}`)}
          onMouseLeave={hideTooltip}
        >
          <span className="status-dot" />
          <div className="system-status-text">
            <strong>{t("systemOnline")}</strong>
            <small>{t("localStore")}</small>
          </div>
        </div>
        <button
          className="language-button"
          onClick={() => setLanguage(language === "fa" ? "en" : "fa")}
          onMouseEnter={(event) => showTooltip(event, t("switchLanguage"))}
          onMouseLeave={hideTooltip}
        >
          <Languages size={16} />
          <span className="nav-item-label">{t("switchLanguage")}</span>
        </button>
        <button
          className="language-button is-logout"
          onClick={onLogout}
          onMouseEnter={(event) => showTooltip(event, t("logout"))}
          onMouseLeave={hideTooltip}
        >
          <LogOut size={16} />
          <span className="nav-item-label">{t("logout")}</span>
        </button>
      </div>

      {collapsed &&
        tooltip &&
        createPortal(
          <div className="sidebar-tooltip" style={{ top: tooltip.top, left: COLLAPSED_TOOLTIP_LEFT }}>
            {tooltip.label}
          </div>,
          document.body,
        )}
    </aside>
  );
}
