import { useEffect, useRef, useState } from "react";
import type { InputHTMLAttributes } from "react";

import { currencyFactor, useI18n } from "../i18n";

/**
 * A money field that groups its digits as you type — ۱٬۲۵۰٬۰۰۰ rather than
 * 1250000.
 *
 * It has to be a text input: `type="number"` refuses to render a separator,
 * which is why every amount in this app was a wall of digits at the one
 * moment it matters most, when somebody is keying a price off a supplier's
 * invoice and needs to see at a glance whether they typed six zeros or
 * seven. `inputMode="decimal"` still brings up the numeric keypad on a
 * phone, so nothing is lost on the counter.
 *
 * Persian and Arabic-Indic digits are accepted alongside Latin ones — a
 * Persian keyboard produces ۱۲۳ and the shopkeeper should not have to care.
 * The caret is put back where the typist left it, counted in digits rather
 * than characters, so inserting one digit mid-number does not send the
 * cursor to the end the moment a separator appears.
 */

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> & {
  /** Always in toman, the stored unit — never the displayed one. */
  value: number | null | undefined;
  /** Hands back toman too, whatever unit the field is currently showing. */
  onChange: (value: number | null) => void;
  /** Whole units only (quantities of people, points); default allows decimals. */
  integer?: boolean;
  /**
   * Set false for a field that is not money — a quantity, a count of days —
   * so the toman/rial preference leaves it alone.
   */
  currencyAware?: boolean;
};

const PERSIAN_ZERO = 0x06f0;
const ARABIC_ZERO = 0x0660;

/** Latin, Persian and Arabic-Indic digits all fold to 0-9. */
function toLatinDigits(text: string): string {
  return text.replace(/[۰-۹٠-٩]/g, (char) => {
    const code = char.charCodeAt(0);
    const base = code >= PERSIAN_ZERO ? PERSIAN_ZERO : ARABIC_ZERO;
    return String(code - base);
  });
}

/** Everything that is not a digit or the one decimal point we keep. */
function extractNumeric(text: string, integer: boolean): string {
  const latin = toLatinDigits(text).replace(/[٫٬]/g, (c) => (c === "٫" ? "." : ""));
  const cleaned = latin.replace(integer ? /[^0-9]/g : /[^0-9.]/g, "");
  if (integer) return cleaned;
  // A second point is a typo, not a second decimal place.
  const [whole, ...rest] = cleaned.split(".");
  return rest.length ? `${whole}.${rest.join("")}` : whole;
}

function countDigits(text: string): number {
  return (toLatinDigits(text).match(/[0-9]/g) ?? []).length;
}

export function AmountInput({
  value,
  onChange,
  integer = false,
  currencyAware = true,
  ...rest
}: Props) {
  const { locale, currency } = useI18n();
  const factor = currencyAware ? currencyFactor(currency) : 1;
  const inputRef = useRef<HTMLInputElement>(null);
  const caretDigitsRef = useRef<number | null>(null);

  /** Stored toman -> the unit on screen. */
  function toDisplay(stored: number): number {
    return stored * factor;
  }

  /** What was typed -> toman. Rounded to the two decimals every money
   *  column in this app carries, so dividing by ten never leaves a tail. */
  function toStored(shown: number): number {
    return Math.round((shown / factor) * 100) / 100;
  }

  /** Group the whole part, leave a half-typed decimal tail alone. */
  function format(raw: string): string {
    if (raw === "") return "";
    const [whole, decimals] = raw.split(".");
    const grouped = whole === "" ? "" : Number(whole).toLocaleString(locale);
    if (decimals === undefined) return grouped;
    const localDecimalPoint = (1.1).toLocaleString(locale).replace(/[\d]/g, "");
    const localDecimals = Number(`0.${decimals || 0}`)
      .toLocaleString(locale, { minimumFractionDigits: decimals.length, maximumFractionDigits: 20 })
      .slice(1 + localDecimalPoint.length);
    return `${grouped}${localDecimalPoint}${localDecimals}`;
  }

  const [text, setText] = useState(() =>
    value === null || value === undefined ? "" : format(String(toDisplay(value))),
  );

  // Follow the value when the form changes it from the outside (a reset, a
  // scanned invoice filling the line in) — but never while the field is
  // being typed into, or the reformat would fight the typist.
  useEffect(() => {
    if (document.activeElement === inputRef.current) return;
    setText(value === null || value === undefined ? "" : format(String(toDisplay(value))));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, locale, factor]);

  // Put the caret back after React has painted the regrouped text.
  useEffect(() => {
    const input = inputRef.current;
    const target = caretDigitsRef.current;
    if (!input || target === null) return;
    caretDigitsRef.current = null;
    let seen = 0;
    let position = input.value.length;
    for (let index = 0; index < input.value.length; index++) {
      if (/[0-9۰-۹٠-٩]/.test(input.value[index])) {
        seen++;
        if (seen === target) {
          position = index + 1;
          break;
        }
      }
    }
    if (target === 0) position = 0;
    input.setSelectionRange(position, position);
  }, [text]);

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const caret = event.target.selectionStart ?? event.target.value.length;
    caretDigitsRef.current = countDigits(event.target.value.slice(0, caret));

    const raw = extractNumeric(event.target.value, integer);
    setText(format(raw));

    if (raw === "" || raw === ".") {
      onChange(null);
      return;
    }
    const parsed = Number(raw);
    onChange(Number.isNaN(parsed) ? null : toStored(parsed));
  }

  return (
    <input
      {...rest}
      ref={inputRef}
      type="text"
      inputMode={integer ? "numeric" : "decimal"}
      autoComplete="off"
      value={text}
      onChange={handleChange}
    />
  );
}
