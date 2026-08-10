import { useEffect, useState } from "react";
import { Minus, Plus } from "lucide-react";

import { useI18n } from "../i18n";
import { WEIGHT_STEP, formatQuantity, roundToWeightPrecision } from "../lib/quantity";

type QuantityInputProps = {
  quantity: number;
  /** Weighted products get a decimal field; counted ones keep the stepper. */
  isWeighted: boolean;
  /** Displayed beside a weighted field so "2.350" is never ambiguous. */
  unit?: string | null;
  /** Receives the desired absolute quantity. Clamping to stock and
   * dropping a line that reaches zero stay with the caller, which is
   * where that policy already lives. */
  onChange: (quantity: number) => void;
  /** Available stock, used to cap what can be typed into a weighted field.
   * The stepper path is left to the caller's own clamping, unchanged. */
  max?: number;
  /** Tighter sizing for the checkout cart's dense line rows. */
  compact?: boolean;
  disabled?: boolean;
};

/**
 * One quantity control for both kinds of product.
 *
 * A counted product keeps the +/- stepper it always had — same markup,
 * same classes, same behaviour, because nothing about counting changed.
 * A weighted product gets a decimal field instead: you cannot arrive at
 * 2.350 kg by pressing + three times, and rounding it to 2 would be the
 * shop giving away 350 grams.
 */
export function QuantityInput({
  quantity,
  isWeighted,
  unit,
  onChange,
  max,
  compact = false,
  disabled = false,
}: QuantityInputProps) {
  const { t, number, locale } = useI18n();

  // While the field has focus the raw keystrokes are the source of truth:
  // a controlled value reformatted on every change makes "2." or a
  // half-typed "0.05" impossible to type. Outside focus the prop wins, so
  // the field still follows changes made anywhere else.
  const [draft, setDraft] = useState<string | null>(null);

  useEffect(() => {
    if (draft === null) return;
    // A quantity changed from outside (stock clamp, line reset) while the
    // field is focused should still win over a stale draft.
    if (Number(draft) !== quantity) setDraft(null);
    // Intentionally keyed on `quantity` alone: re-running when `draft`
    // changes would wipe the draft on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quantity]);

  if (!isWeighted) {
    return (
      <div className={`quantity-control${compact ? " compact" : ""}`}>
        <button type="button" disabled={disabled} onClick={() => onChange(quantity - 1)}>
          <Minus size={compact ? 12 : 14} />
        </button>
        <span>{number(quantity)}</span>
        <button type="button" disabled={disabled} onClick={() => onChange(quantity + 1)}>
          <Plus size={compact ? 12 : 14} />
        </button>
      </div>
    );
  }

  function commit(raw: string) {
    setDraft(raw);
    if (raw.trim() === "") return; // mid-edit, not a value yet
    const parsed = Number(raw);
    if (!Number.isFinite(parsed) || parsed < 0) return;
    const rounded = roundToWeightPrecision(parsed);
    onChange(max !== undefined && rounded > max ? roundToWeightPrecision(max) : rounded);
  }

  function settle() {
    // An empty or unparseable field on blur means "no change", not "zero" —
    // clearing the box to retype should never silently zero a cart line.
    setDraft(null);
  }

  return (
    <div className={`quantity-control weighted${compact ? " compact" : ""}`}>
      <input
        type="number"
        inputMode="decimal"
        min={WEIGHT_STEP}
        step={WEIGHT_STEP}
        max={max}
        disabled={disabled}
        aria-label={t("weightLabel")}
        title={t("enterWeight")}
        value={draft ?? formatQuantityDraft(quantity)}
        onChange={(event) => commit(event.target.value)}
        onBlur={settle}
      />
      {unit && <span className="quantity-unit">{unit}</span>}
    </div>
  );

  /** The field's own text: plain digits, not locale-formatted — a Persian
   * numeral or a thousands separator is not something `type="number"`
   * accepts back. The locale-formatted reading is what
   * `formatQuantity` renders everywhere the value is displayed rather
   * than edited. */
  function formatQuantityDraft(value: number): string {
    return String(roundToWeightPrecision(value));
  }
}

/** Re-exported so callers that only display a quantity don't need to
 * reach past this module for the matching formatter. */
export { formatQuantity };
