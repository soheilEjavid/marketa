import { CalendarRange } from "lucide-react";

import { JalaliDatePicker } from "./JalaliDatePicker";
import { useI18n } from "../i18n";
import {
  getJalaliMonthDays,
  isoToJalaliStr,
  parseJalaliDateString,
  todayJalali,
  toGregorian,
} from "../utils/jalali";

export type PeriodPreset = "this-week" | "this-month" | "last-month" | "this-year" | "custom";

export type Period = {
  start: string; // ISO
  end: string; // ISO
  preset: PeriodPreset;
};

function iso(gy: number, gm: number, gd: number): string {
  return `${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`;
}

/** Presets are aligned to the **Jalali** calendar on purpose, not to rolling
 * N-day windows. A shopkeeper reconciles "مرداد" by hand; a figure covering
 * "the last 30 days" would never match what they computed, and a number that
 * never matches theirs is a number they stop trusting. */
export function resolvePeriod(preset: Exclude<PeriodPreset, "custom">): Period {
  const today = parseJalaliDateString(todayJalali())!;
  const { year: jy, month: jm, day: jd } = today;
  const endIso = iso(...toGregorian(jy, jm, jd));

  if (preset === "this-week") {
    // The Iranian week starts on Saturday. JS getDay(): 0=Sun … 6=Sat.
    const [gy, gm, gd] = toGregorian(jy, jm, jd);
    const todayDate = new Date(gy, gm - 1, gd);
    const sinceSaturday = (todayDate.getDay() + 1) % 7;
    const weekStart = new Date(gy, gm - 1, gd - sinceSaturday);
    return {
      start: iso(weekStart.getFullYear(), weekStart.getMonth() + 1, weekStart.getDate()),
      end: endIso,
      preset,
    };
  }

  if (preset === "this-month") {
    return { start: iso(...toGregorian(jy, jm, 1)), end: endIso, preset };
  }

  if (preset === "last-month") {
    const py = jm === 1 ? jy - 1 : jy;
    const pm = jm === 1 ? 12 : jm - 1;
    return {
      start: iso(...toGregorian(py, pm, 1)),
      end: iso(...toGregorian(py, pm, getJalaliMonthDays(py, pm))),
      preset,
    };
  }

  // this-year
  return { start: iso(...toGregorian(jy, 1, 1)), end: endIso, preset };
}

export function defaultPeriod(): Period {
  return resolvePeriod("this-month");
}

const PRESETS: { key: Exclude<PeriodPreset, "custom">; label: string }[] = [
  { key: "this-week", label: "periodThisWeek" },
  { key: "this-month", label: "periodThisMonth" },
  { key: "last-month", label: "periodLastMonth" },
  { key: "this-year", label: "periodThisYear" },
];

type PeriodSelectorProps = {
  value: Period;
  onChange: (period: Period) => void;
};

export function PeriodSelector({ value, onChange }: PeriodSelectorProps) {
  const { t } = useI18n();

  return (
    <div className="period-selector">
      <div className="period-presets">
        {PRESETS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className={`price-tier-button ${value.preset === key ? "price-tier-selected" : ""}`}
            onClick={() => onChange(resolvePeriod(key))}
          >
            {t(label)}
          </button>
        ))}
      </div>
      <div className="period-range">
        <JalaliDatePicker
          value={value.start}
          onChange={(start) => onChange({ ...value, start, preset: "custom" })}
        />
        <span>—</span>
        <JalaliDatePicker
          value={value.end}
          onChange={(end) => onChange({ ...value, end, preset: "custom" })}
        />
      </div>
    </div>
  );
}

/** The figures these selectors drive are money. Rendering them without saying
 * which days they cover is worse than not showing them at all -- a shopkeeper
 * cannot tell a monthly profit from a yearly one by looking. */
export function PeriodLabel({ period }: { period: Period }) {
  const { t } = useI18n();
  const preset = PRESETS.find((p) => p.key === period.preset);
  const range = `${isoToJalaliStr(period.start) ?? period.start} — ${isoToJalaliStr(period.end) ?? period.end}`;
  return (
    <span className="subtle-chip period-label">
      <CalendarRange size={13} strokeWidth={1.8} />
      {preset ? `${t(preset.label)}: ${range}` : range}
    </span>
  );
}
