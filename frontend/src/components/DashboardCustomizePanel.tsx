import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Settings2 } from "lucide-react";
import { useI18n } from "../i18n";
import { DASHBOARD_WIDGETS, type WidgetId } from "../lib/dashboardWidgets";

type DashboardCustomizePanelProps = {
  visibility: Record<WidgetId, boolean>;
  onToggle: (id: WidgetId, visible: boolean) => void;
};

const DROPDOWN_GAP = 8;
const ESTIMATED_PANEL_HEIGHT = 420;

export function DashboardCustomizePanel({ visibility, onToggle }: DashboardCustomizePanelProps) {
  const { t, direction } = useI18n();
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number; above: boolean } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const updatePosition = useCallback(() => {
    if (!open || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const spaceBelow = viewportHeight - rect.bottom;
    const above = spaceBelow < ESTIMATED_PANEL_HEIGHT && rect.top > spaceBelow;
    setPosition({
      top: above ? rect.top - DROPDOWN_GAP : rect.bottom + DROPDOWN_GAP,
      left: direction === "rtl" ? rect.right - 300 : rect.left,
      above,
    });
  }, [open, direction]);

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
      if (triggerRef.current && triggerRef.current.contains(e.target as Node)) return;
      const portal = document.querySelector(".dashboard-customize-portal");
      if (portal && portal.contains(e.target as Node)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    function handleCloseAll() {
      setOpen(false);
    }
    document.addEventListener("close-all-dropdowns", handleCloseAll);
    return () => document.removeEventListener("close-all-dropdowns", handleCloseAll);
  }, []);

  const panelContent = open && position ? (
    <div
      className="dashboard-customize-portal"
      style={{
        top: `${position.top}px`,
        left: `${position.left}px`,
        transformOrigin: position.above ? "bottom" : "top",
      }}
    >
      <div className="dashboard-customize-header">
        <strong>{t("customizeDashboard")}</strong>
      </div>
      <div className="dashboard-customize-list">
        {DASHBOARD_WIDGETS.map((widget) => (
          <label className="checkbox-field dashboard-customize-item" key={widget.id}>
            <input
              type="checkbox"
              checked={visibility[widget.id] ?? true}
              onChange={(event) => onToggle(widget.id, event.target.checked)}
            />
            <span>{t(widget.labelKey)}</span>
          </label>
        ))}
        <div className="dashboard-customize-item dashboard-customize-disabled">
          <input type="checkbox" checked={false} disabled />
          <span>
            {t("profitVsExpensesTitle")}
            <small className="dashboard-customize-badge">{t("comingSoon")}</small>
          </span>
        </div>
      </div>
    </div>
  ) : null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="secondary-button"
        onClick={() => {
          document.dispatchEvent(new CustomEvent("close-all-dropdowns"));
          setOpen((current) => !current);
        }}
      >
        <Settings2 size={16} />
        {t("customizeDashboard")}
      </button>
      {open && position && createPortal(panelContent, document.getElementById("modal-root") ?? document.body)}
    </>
  );
}
