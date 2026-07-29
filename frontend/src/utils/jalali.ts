/**
 * Jalali (Shamsi) date conversion utilities.
 *
 * All Gregorian ↔ Jalali conversion is delegated to the well-tested
 * `jalaali-js` library.  No hand-rolled conversion math is used anywhere
 * in the app.
 *
 * Storage format: Gregorian ISO 8601 (e.g. "2026-07-25") on the backend
 * and in API responses.  Jalali is only used at the display/input layer.
 */

import * as jalaali from "jalaali-js";

// ─── Gregorian → Jalali ─────────────────────────────────────────────────────

/**
 * Convert a Gregorian date to Jalali (Shamsi).
 *
 * @returns `[year, month, day]` in the Jalali calendar.
 */
export function gregorianToJalali(
  gy: number,
  gm: number,
  gd: number,
): [number, number, number] {
  const r = jalaali.toJalaali(gy, gm, gd);
  return [r.jy, r.jm, r.jd];
}

/**
 * Convert a JavaScript `Date` to a Jalali date string `"YYYY/MM/DD"`.
 */
export function dateToJalaliStr(date: Date): string {
  const [jy, jm, jd] = gregorianToJalali(
    date.getFullYear(),
    date.getMonth() + 1,
    date.getDate(),
  );
  return formatJalali(jy, jm, jd);
}

/**
 * Return the current Jalali date as `"YYYY/MM/DD"`.
 */
export function todayJalali(): string {
  return dateToJalaliStr(new Date());
}

// ─── Jalali → Gregorian ─────────────────────────────────────────────────────

/**
 * Convert a Jalali date to Gregorian.
 *
 * @returns `[year, month, day]` in the Gregorian calendar.
 */
export function jalaliToGregorian(
  jy: number,
  jm: number,
  jd: number,
): [number, number, number] {
  const r = jalaali.toGregorian(jy, jm, jd);
  return [r.gy, r.gm, r.gd];
}

/**
 * Convert a Jalali date string `"YYYY/MM/DD"` to a Gregorian ISO string
 * `"YYYY-MM-DD"`.
 *
 * Returns `null` if the input is not a valid Jalali date.
 */
export function jalaliStrToGregorianIso(dateStr: string): string | null {
  const parsed = parseJalaliDateString(dateStr);
  if (!parsed) return null;
  if (!jalaali.isValidJalaaliDate(parsed.year, parsed.month, parsed.day)) return null;
  const [gy, gm, gd] = jalaliToGregorian(parsed.year, parsed.month, parsed.day);
  return `${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`;
}

/**
 * Convert a Gregorian ISO date string `"YYYY-MM-DD"` to a Jalali date string
 * `"YYYY/MM/DD"`.
 */
export function isoToJalaliStr(isoDate: string): string | null {
  const parts = isoDate.split("-");
  if (parts.length !== 3) return null;
  const [gy, gm, gd] = parts.map(Number);
  if (isNaN(gy) || isNaN(gm) || isNaN(gd)) return null;
  const [jy, jm, jd] = gregorianToJalali(gy, gm, gd);
  return formatJalali(jy, jm, jd);
}

// ─── Format / Parse ──────────────────────────────────────────────────────────

/**
 * Format a Jalali date as `"YYYY/MM/DD"`.
 */
export function formatJalali(
  year: number,
  month: number,
  day: number,
): string {
  return `${year}/${String(month).padStart(2, "0")}/${String(day).padStart(2, "0")}`;
}

/**
 * Parse a Jalali date string `"YYYY/MM/DD"` into its components.
 */
export function parseJalaliDateString(
  dateStr: string,
): { year: number; month: number; day: number } | null {
  const parts = dateStr.split("/");
  if (parts.length !== 3) return null;
  const year = parseInt(parts[0], 10);
  const month = parseInt(parts[1], 10);
  const day = parseInt(parts[2], 10);
  if (isNaN(year) || isNaN(month) || isNaN(day)) return null;
  return { year, month, day };
}

// ─── Calendar helpers ────────────────────────────────────────────────────────

/**
 * Return the number of days in a given Jalali month/year.
 */
export function getJalaliMonthDays(year: number, month: number): number {
  if (month <= 6) return 31;
  if (month <= 11) return 30;
  return jalaali.isLeapJalaaliYear(year) ? 30 : 29;
}

/**
 * Return the Persian (Jalali) month names.
 */
export function getJalaliMonths(): string[] {
  return [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
  ];
}

export type JalaliCalendarDay = {
  day: number;
  /** Gregorian ISO date (YYYY-MM-DD) for this Jalali day — matches API date fields. */
  iso: string;
  /** 0=Saturday .. 6=Friday (Persian week order). */
  weekday: number;
};

/**
 * Build a flat, week-padded calendar grid for a Jalali month: `null` cells
 * for the leading/trailing blanks so every row is a full week of 7. Weekday
 * offset uses the same `(getDay() + 1) % 7` convention as JalaliDatePicker
 * (Gregorian equivalent's day-of-week remapped to a Saturday-first week) —
 * there is no Jalali-native weekday primitive, so this is the same reliable
 * path used there, not new conversion math.
 */
export function getJalaliMonthGrid(year: number, month: number): (JalaliCalendarDay | null)[] {
  const dayCount = getJalaliMonthDays(year, month);
  const days: JalaliCalendarDay[] = [];
  for (let day = 1; day <= dayCount; day++) {
    const [gy, gm, gd] = jalaliToGregorian(year, month, day);
    const weekday = (new Date(gy, gm - 1, gd).getDay() + 1) % 7;
    const iso = `${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`;
    days.push({ day, iso, weekday });
  }
  const leading: null[] = Array.from({ length: days[0].weekday }, () => null);
  const grid: (JalaliCalendarDay | null)[] = [...leading, ...days];
  const trailing: null[] = Array.from({ length: (7 - (grid.length % 7)) % 7 }, () => null);
  return [...grid, ...trailing];
}

// ─── Deprecated aliases (preserve backward compatibility) ────────────────────

/** @deprecated Use `gregorianToJalali` instead. */
export function toJalali(gy: number, gm: number, gd: number): [number, number, number] {
  return gregorianToJalali(gy, gm, gd);
}

/** @deprecated Use `jalaliToGregorian` instead. */
export function toGregorian(jy: number, jm: number, jd: number): [number, number, number] {
  return jalaliToGregorian(jy, jm, jd);
}

/** @deprecated Use `dateToJalaliStr` instead. */
export function gregorianToJalaliStr(
  year: number,
  month: number,
  day: number,
): string {
  return formatJalali(...gregorianToJalali(year, month, day));
}