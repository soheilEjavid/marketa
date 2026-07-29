import { useEffect, useState } from "react";

import { getCheckSummary } from "../api";
import { useI18n } from "../i18n";
import type { CheckSummary } from "../types";

export function CheckTotalsWidget() {
  const { t, money } = useI18n();
  const [summary, setSummary] = useState<CheckSummary | null>(null);

  useEffect(() => {
    getCheckSummary()
      .then(setSummary)
      .catch(() => setSummary(null));
  }, []);

  return (
    <div className="check-totals-widget">
      <div className="check-totals-row">
        <span>{t("dueThisWeek")}</span>
        <strong>{summary ? money(Number(summary.due_this_week)) : "—"}</strong>
      </div>
      <div className="check-totals-row">
        <span>{t("dueThisMonth")}</span>
        <strong>{summary ? money(Number(summary.due_this_month)) : "—"}</strong>
      </div>
    </div>
  );
}
