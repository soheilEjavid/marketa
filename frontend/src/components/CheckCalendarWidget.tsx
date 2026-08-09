import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { getChecks } from "../api";
import { useI18n } from "../i18n";
import { getJalaliMonthGrid, getJalaliMonths, localIsoDate, parseJalaliDateString, todayJalali } from "../utils/jalali";
import type { CheckRead } from "../types";
import type { Page } from "./Sidebar";

type CheckCalendarWidgetProps = {
  onNavigate: (page: Page) => void;
};

const WEEKDAY_LABELS = ["ش", "ی", "د", "س", "چ", "پ", "ج"];

export function CheckCalendarWidget({ onNavigate }: CheckCalendarWidgetProps) {
  const { t, money } = useI18n();
  const todayParsed = parseJalaliDateString(todayJalali())!;
  const [viewYear, setViewYear] = useState(todayParsed.year);
  const [viewMonth, setViewMonth] = useState(todayParsed.month);
  const [checks, setChecks] = useState<CheckRead[]>([]);
  const [openDay, setOpenDay] = useState<string | null>(null);
  const widgetRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getChecks({ status: "pending" })
      .then(setChecks)
      .catch(() => setChecks([]));
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (widgetRef.current && !widgetRef.current.contains(event.target as Node)) {
        setOpenDay(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const byDate = useMemo(() => {
    const map = new Map<string, CheckRead[]>();
    for (const check of checks) {
      if (!check.check_due_date) continue;
      const list = map.get(check.check_due_date) ?? [];
      list.push(check);
      map.set(check.check_due_date, list);
    }
    return map;
  }, [checks]);

  const grid = useMemo(() => getJalaliMonthGrid(viewYear, viewMonth), [viewYear, viewMonth]);
  const months = getJalaliMonths();
  const todayIso = localIsoDate();

  function goToMonth(delta: number) {
    let month = viewMonth + delta;
    let year = viewYear;
    if (month < 1) {
      month = 12;
      year -= 1;
    } else if (month > 12) {
      month = 1;
      year += 1;
    }
    setViewMonth(month);
    setViewYear(year);
    setOpenDay(null);
  }

  return (
    <div className="check-calendar-widget" ref={widgetRef}>
      <div className="check-calendar-nav">
        <button type="button" className="icon-button" onClick={() => goToMonth(-1)} aria-label={t("previousMonth")}>
          <ChevronRight size={16} />
        </button>
        <strong>
          {months[viewMonth - 1]} {viewYear}
        </strong>
        <button type="button" className="icon-button" onClick={() => goToMonth(1)} aria-label={t("nextMonth")}>
          <ChevronLeft size={16} />
        </button>
      </div>

      <div className="check-calendar-grid">
        {WEEKDAY_LABELS.map((label) => (
          <span className="check-calendar-weekday" key={label}>
            {label}
          </span>
        ))}
        {grid.map((cell, index) => {
          if (!cell) return <span className="check-calendar-cell empty" key={`empty-${index}`} />;
          const dueChecks = byDate.get(cell.iso) ?? [];
          const isToday = cell.iso === todayIso;
          const isOpen = openDay === cell.iso;
          return (
            <div className="check-calendar-cell-wrap" key={cell.iso}>
              <button
                type="button"
                className={`check-calendar-cell ${dueChecks.length ? "has-checks" : ""} ${isToday ? "is-today" : ""}`}
                onClick={() => dueChecks.length > 0 && setOpenDay(isOpen ? null : cell.iso)}
              >
                {cell.day}
                {dueChecks.length > 0 && <span className="check-calendar-dot" />}
              </button>
              {isOpen && (
                <div className="check-calendar-popover">
                  {dueChecks.map((check) => (
                    <div className="check-calendar-popover-row" key={check.id}>
                      <span>{check.supplier_name ?? "—"}</span>
                      <strong>{money(Number(check.amount))}</strong>
                    </div>
                  ))}
                  <button type="button" className="text-button" onClick={() => onNavigate("checks")}>
                    {t("checks")}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
