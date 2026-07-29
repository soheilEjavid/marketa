import { PartyPopper, X } from "lucide-react";

import { useI18n } from "../i18n";

export type PostCheckoutLoyaltyPrompt =
  | { type: "celebrate"; customerName: string }
  | { type: "suggest"; saleTotal: number };

type PostCheckoutLoyaltyPromptProps = {
  prompt: PostCheckoutLoyaltyPrompt;
  onDismiss: () => void;
};

/**
 * Post-checkout loyalty notice for LoyaltySettings.min_invoice_total_for_membership
 * — purely informational text, never touching the sale that was just
 * closed. "celebrate": this exact sale crossed the threshold for its
 * already-attached customer (services/sales.py sets
 * Sale.loyalty_membership_just_earned). "suggest": no customer was
 * attached but the total qualifies — the actual quick-add action lives
 * next to "شروع فروش جدید" (see QuickAddLoyaltyCustomerButton), this is
 * just the heads-up banner.
 */
export function PostCheckoutLoyaltyPrompt({ prompt, onDismiss }: PostCheckoutLoyaltyPromptProps) {
  const { t, money } = useI18n();

  return (
    <div className="loyalty-checkout-banner" style={{ marginBottom: 12 }}>
      <span style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "space-between" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {prompt.type === "celebrate" && <PartyPopper size={16} />}
          {prompt.type === "celebrate"
            ? t("loyaltyMembershipEarnedCelebration").replace("{name}", prompt.customerName)
            : t("loyaltyEnrollmentSuggestion").replace("{total}", money(prompt.saleTotal))}
        </span>
        <button type="button" className="icon-button tiny" onClick={onDismiss} aria-label={t("dismiss")}>
          <X size={14} />
        </button>
      </span>
    </div>
  );
}
