import { useEffect, useState } from "react";
import { TriangleAlert, X } from "lucide-react";

import { getChecks } from "../api";
import { useI18n } from "../i18n";
import { daysUntil } from "../lib/checkDates";
import { dismissReminder, isReminderDismissed } from "../lib/checkReminderDismiss";
import type { CheckRead } from "../types";

type CheckReminderBannerProps = {
  onViewChecks: () => void;
};

export function CheckReminderBanner({ onViewChecks }: CheckReminderBannerProps) {
  const { t, money } = useI18n();
  const [dueSoon, setDueSoon] = useState<CheckRead[]>([]);
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    getChecks({ status: "pending", sort: "due_asc" })
      .then((checks) => {
        const soon = checks.filter((check) => check.check_due_date && daysUntil(check.check_due_date) <= 7);
        setDueSoon(soon);
        const signature = soon.map((check) => check.id).sort((a, b) => a - b).join(",");
        setDismissed(soon.length === 0 || isReminderDismissed(signature));
      })
      .catch(() => setDueSoon([]));
  }, []);

  if (dismissed || dueSoon.length === 0) return null;

  const urgent = dueSoon.filter((check) => check.check_due_date && daysUntil(check.check_due_date) <= 1);
  const relevant = urgent.length > 0 ? urgent : dueSoon;
  const total = relevant.reduce((sum, check) => sum + Number(check.amount), 0);
  const signature = dueSoon.map((check) => check.id).sort((a, b) => a - b).join(",");
  const messageKey = urgent.length > 0 ? "checkReminderUrgent" : "checkReminderWeek";
  const message = t(messageKey).replace("{count}", String(relevant.length)).replace("{amount}", money(total));

  function handleDismiss() {
    dismissReminder(signature);
    setDismissed(true);
  }

  return (
    <div className={`feedback-banner ${urgent.length > 0 ? "error" : "warning"} check-reminder-banner`}>
      <TriangleAlert size={18} />
      <span>{message}</span>
      <button type="button" className="text-button" onClick={onViewChecks}>
        {t("checks")}
      </button>
      <button type="button" className="icon-button" onClick={handleDismiss} aria-label={t("dismiss")}>
        <X size={16} />
      </button>
    </div>
  );
}
