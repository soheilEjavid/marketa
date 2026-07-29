import { useEffect, useState } from "react";
import { PlayCircle, Trash2 } from "lucide-react";

import { discardSale, getHeldSales } from "../api";
import { useI18n } from "../i18n";
import type { Sale } from "../types";
import { dateToJalaliStr } from "../utils/jalali";

type HeldSalesTabProps = {
  onResume: (sale: Sale) => void;
};

export function HeldSalesTab({ onResume }: HeldSalesTabProps) {
  const { t, money, number } = useI18n();
  const [sales, setSales] = useState<Sale[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);

  function load() {
    setLoading(true);
    getHeldSales()
      .then(setSales)
      .catch(() => setSales([]))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleDiscard(sale: Sale) {
    setBusyId(sale.id);
    try {
      await discardSale(sale.id);
      setSales((current) => current.filter((item) => item.id !== sale.id));
    } catch {
      // Leave the row in place so the cashier can retry.
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
      <div className="inventory-table">
        <div className="inventory-row inventory-head held-sales-columns">
          <span>{t("invoice")}</span>
          <span>{t("date")}</span>
          <span>{t("items")}</span>
          <span>{t("total")}</span>
          <span />
        </div>

        {loading ? (
          <div className="empty-state compact">{t("loading")}</div>
        ) : sales.length === 0 ? (
          <div className="empty-state compact">{t("noHeldSales")}</div>
        ) : (
          sales.map((sale) => (
            <div className="inventory-row held-sales-columns animated-line" key={sale.id}>
              <span>{sale.invoice_number}</span>
              <span>{dateToJalaliStr(new Date(sale.created_at))}</span>
              <span className="muted-text">{number(sale.items.length)}</span>
              <strong>{money(Number(sale.total))}</strong>
              <div className="action-buttons">
                <button
                  className="icon-button"
                  title={t("resumeSale")}
                  aria-label={t("resumeSale")}
                  onClick={() => onResume(sale)}
                >
                  <PlayCircle size={16} />
                </button>
                <button
                  className="icon-button danger"
                  title={t("discardSale")}
                  aria-label={t("discardSale")}
                  disabled={busyId === sale.id}
                  onClick={() => handleDiscard(sale)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
