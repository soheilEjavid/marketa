import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useI18n } from "../i18n";
import {
  formatJalali,
  getJalaliMonthDays,
  getJalaliMonths,
  parseJalaliDateString,
  todayJalali,
  toGregorian,
  toJalali,
} from "../utils/jalali";

type JalaliDatePickerProps = {
  value: string;
  onChange: (isoDate: string) => void;
  placeholder?: string;
};

const DROPDOWN_GAP = 6;
const ESTIMATED_DROPDOWN_HEIGHT = 380;

const MODAL_ROOT = "modal-root";

export function JalaliDatePicker({
  value,
  onChange,
  placeholder,
}: JalaliDatePickerProps) {
  const { t, direction } = useI18n();
  const [open, setOpen] = useState(false);
  const [displayValue, setDisplayValue] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ top: number; left: number; width: number; above: boolean } | null>(null);

  // Calendar state — initialised to today's Jalali date
  const today = todayJalali();
  const todayParsed = parseJalaliDateString(today)!;
  const [viewYear, setViewYear] = useState(todayParsed.year);
  const [viewMonth, setViewMonth] = useState(todayParsed.month);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null);
  const [selectedDay, setSelectedDay] = useState<number | null>(null);

  // Initialize from value
  useEffect(() => {
    if (value) {
      // value is ISO date (e.g., 2026-07-25)
      const parts = value.split("-");
      if (parts.length === 3) {
        const [gy, gm, gd] = parts.map(Number);
        if (!isNaN(gy) && !isNaN(gm) && !isNaN(gd)) {
          const [jy, jm, jd] = toJalali(gy, gm, gd);
          setDisplayValue(formatJalali(jy, jm, jd));
          setSelectedYear(jy);
          setSelectedMonth(jm);
          setSelectedDay(jd);
          setViewYear(jy);
          setViewMonth(jm);
          return;
        }
      }
    }
    setDisplayValue("");
    setSelectedYear(null);
    setSelectedMonth(null);
    setSelectedDay(null);
  }, [value]);

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
        const portal = document.querySelector(".jalali-datepicker-dropdown-portal");
        if (portal && portal.contains(e.target as Node)) return;
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Close dropdown when any modal is opened (via custom event)
  useEffect(() => {
    function handleCloseAll() {
      setOpen(false);
    }
    document.addEventListener("close-all-dropdowns", handleCloseAll);
    return () => document.removeEventListener("close-all-dropdowns", handleCloseAll);
  }, []);

  const monthNames = getJalaliMonths();
  const daysInMonth = getJalaliMonthDays(viewYear, viewMonth);

  // Get first day offset for Jalali calendar (Saturday-based week)
  // JS getDay(): 0=Sun, 1=Mon, ..., 6=Sat
  // Jalali week: 0=Sat, 1=Sun, ..., 6=Fri  →  offset = (getDay() + 1) % 7
  const firstDayOffset = (() => {
    const [gy, gm, gd] = toGregorian(viewYear, viewMonth, 1);
    const d = new Date(gy, gm - 1, gd);
    return (d.getDay() + 1) % 7;
  })();

  // Jalali day names (Saturday-based order)
  const dayNames = ["ش", "ی", "د", "س", "چ", "پ", "ج"];

  function handleDayClick(day: number) {
    const isoDate = (() => {
      const [gy, gm, gd] = toGregorian(viewYear, viewMonth, day);
      return `${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`;
    })();
    onChange(isoDate);
    setSelectedYear(viewYear);
    setSelectedMonth(viewMonth);
    setSelectedDay(day);
    setOpen(false);
  }

  function prevMonth() {
    if (viewMonth === 1) {
      setViewYear(viewYear - 1);
      setViewMonth(12);
    } else {
      setViewMonth(viewMonth - 1);
    }
  }

  function nextMonth() {
    if (viewMonth === 12) {
      setViewYear(viewYear + 1);
      setViewMonth(1);
    } else {
      setViewMonth(viewMonth + 1);
    }
  }

  function handleTriggerClick() {
    setOpen(!open);
    if (!open) {
      if (selectedYear) {
        setViewYear(selectedYear);
        setViewMonth(selectedMonth || 1);
      }
    }
  }

  const calendarContent = open && position ? (
    <div
      className="jalali-datepicker-dropdown-portal"
      style={{
        top: `${position.top}px`,
        left: `${position.left}px`,
        width: `${position.width}px`,
        transformOrigin: position.above ? "bottom" : "top",
      }}
    >
      <div className="jalali-datepicker-header">
        <button
          type="button"
          className="jalali-datepicker-nav"
          onClick={prevMonth}
          aria-label="Previous month"
        >
          <ChevronRight size={16} />
        </button>
        <span className="jalali-datepicker-title">
          {monthNames[viewMonth - 1]} {viewYear}
        </span>
        <button
          type="button"
          className="jalali-datepicker-nav"
          onClick={nextMonth}
          aria-label="Next month"
        >
          <ChevronLeft size={16} />
        </button>
      </div>

      <div className="jalali-datepicker-day-names">
        {dayNames.map((name, i) => (
          <span key={i} className="jalali-datepicker-day-name">
            {name}
          </span>
        ))}
      </div>

      <div className="jalali-datepicker-days">
        {/* Empty cells for days before the 1st (Jalali: Saturday-based) */}
        {Array.from({ length: firstDayOffset }, (_, i) => (
          <span key={`empty-${i}`} className="jalali-datepicker-day empty" />
        ))}

        {/* Day cells */}
        {Array.from({ length: daysInMonth }, (_, i) => {
          const day = i + 1;
          const isToday =
            day === todayParsed.day &&
            viewMonth === todayParsed.month &&
            viewYear === todayParsed.year;
          const isSelected =
            day === selectedDay &&
            viewMonth === selectedMonth &&
            viewYear === selectedYear;

          return (
            <button
              key={day}
              type="button"
              className={`jalali-datepicker-day ${
                isToday ? "today" : ""
              } ${isSelected ? "selected" : ""}`}
              onClick={() => handleDayClick(day)}
            >
              {day}
            </button>
          );
        })}
      </div>

      <div className="jalali-datepicker-footer">
        <button
          type="button"
          className="jalali-datepicker-today-btn"
          onClick={() => {
            const [gy, gm, gd] = toGregorian(
              todayParsed.year,
              todayParsed.month,
              todayParsed.day
            );
            onChange(
              `${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`
            );
            setSelectedYear(todayParsed.year);
            setSelectedMonth(todayParsed.month);
            setSelectedDay(todayParsed.day);
            setViewYear(todayParsed.year);
            setViewMonth(todayParsed.month);
            setOpen(false);
          }}
        >
          {t("today")}
        </button>
        <button
          type="button"
          className="jalali-datepicker-clear-btn"
          onClick={() => {
            onChange("");
            setDisplayValue("");
            setSelectedYear(null);
            setSelectedMonth(null);
            setSelectedDay(null);
            setOpen(false);
          }}
        >
          {t("clear")}
        </button>
      </div>
    </div>
  ) : null;

  return (
    <>
      <div className="jalali-datepicker-container" ref={containerRef}>
        <div
          className="jalali-datepicker-trigger"
          onClick={handleTriggerClick}
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              handleTriggerClick();
            }
            if (e.key === "Escape") {
              setOpen(false);
            }
          }}
        >
          <CalendarDays size={16} className="jalali-datepicker-icon" />
          <span className={`jalali-datepicker-value ${!displayValue ? "placeholder" : ""}`}>
            {displayValue || placeholder || t("expiryDate")}
          </span>
        </div>
      </div>

      {open && position && createPortal(calendarContent, document.getElementById(MODAL_ROOT) ?? document.body)}
    </>
  );
}