import { useState, type FormEvent } from "react";
import { Sparkles, UserPlus, X } from "lucide-react";

import { createCustomer, getErrorMessage } from "../api";
import { useI18n } from "../i18n";
import { Modal } from "./Modal";
import type { Customer } from "../types";

type QuickAddLoyaltyCustomerButtonProps = {
  saleTotal: number;
  onCustomerCreated: (customer: Customer) => void;
};

/**
 * The post-checkout "register this customer for the loyalty club" CTA —
 * lives in ReceiptView's action row, right beside "شروع فروش جدید" (see
 * Sales.tsx). Creating a customer here never touches the already-closed
 * sale (no customer_id attach, no retroactive points) — it only sets
 * Customer.loyalty_member for their *next* purchase.
 */
export function QuickAddLoyaltyCustomerButton({ saleTotal, onCustomerCreated }: QuickAddLoyaltyCustomerButtonProps) {
  const { t, money } = useI18n();
  const [open, setOpen] = useState(false);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<Customer | null>(null);

  function close() {
    setOpen(false);
    setFullName("");
    setPhone("");
    setError("");
    setCreated(null);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!fullName.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const customer = await createCustomer({
        full_name: fullName.trim(),
        phone: phone.trim() || null,
        credit_limit: 0,
        is_active: true,
        loyalty_member: true,
      });
      onCustomerCreated(customer);
      setCreated(customer);
    } catch (submitError) {
      setError(getErrorMessage(submitError, t));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <button type="button" className="quick-add-loyalty-button no-print" onClick={() => setOpen(true)}>
        <span className="quick-add-loyalty-icon">
          <UserPlus size={17} />
        </span>
        {t("registerCustomerQuick")}
        <Sparkles size={14} className="quick-add-loyalty-sparkle" />
      </button>

      {open && (
        <Modal onClose={close}>
          <div className="party-form quick-add-loyalty-form" onMouseDown={(event) => event.stopPropagation()}>
            <div className="panel-heading">
              <h2>
                <Sparkles size={17} style={{ verticalAlign: "middle", marginInlineEnd: 6, color: "var(--orange-dark)" }} />
                {t("registerCustomerQuick")}
              </h2>
              <button type="button" className="icon-button" onClick={close} aria-label={t("cancel")}>
                <X size={18} />
              </button>
            </div>

            {created ? (
              <>
                <div className="feedback-banner success">
                  {t("loyaltyQuickAddSuccess").replace("{name}", created.full_name)}
                </div>
                <div className="form-actions">
                  <button type="button" className="primary-button" onClick={close}>
                    {t("gotIt")}
                  </button>
                </div>
              </>
            ) : (
              <form onSubmit={handleSubmit} className="form-grid">
                <p className="quick-add-loyalty-context full-span">
                  {t("loyaltyEnrollmentSuggestion").replace("{total}", money(saleTotal))}
                </p>
                {error && <div className="feedback-banner error full-span">{error}</div>}
                <label className="field">
                  <span>{t("fullName")}</span>
                  <input
                    required
                    minLength={2}
                    autoFocus
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>{t("phone")} ({t("optional")})</span>
                  <input value={phone} onChange={(event) => setPhone(event.target.value)} />
                </label>
                <small className="muted-text full-span">{t("loyaltyQuickAddNoRetroactivePoints")}</small>
                <div className="form-actions full-span">
                  <button type="button" className="secondary-button" onClick={close}>
                    {t("cancel")}
                  </button>
                  <button className="primary-button" disabled={submitting || !fullName.trim()}>
                    {submitting ? t("loading") : t("save")}
                  </button>
                </div>
              </form>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
