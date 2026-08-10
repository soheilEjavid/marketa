import { useCallback, useEffect, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, RefreshCw } from "lucide-react";

import { getInventoryTransactions } from "../api";
import { useI18n } from "../i18n";
import { formatQuantityWithUnit } from "../lib/quantity";
import type {
  InventoryTransaction,
  InventoryTransactionType,
} from "../types";

export function InventoryHistory() {
  const { locale, number, t } = useI18n();
  const [transactions, setTransactions] = useState<InventoryTransaction[]>([]);
  const [filter, setFilter] = useState<InventoryTransactionType | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadTransactions = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setTransactions(await getInventoryTransactions(filter || undefined));
    } catch {
      setError(t("apiError"));
    } finally {
      setLoading(false);
    }
  }, [filter, t]);

  useEffect(() => {
    loadTransactions();
  }, [loadTransactions]);

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("inventory")}</p>
          <h1>{t("inventoryTitle")}</h1>
          <p>{t("inventorySubtitle")}</p>
        </div>
        <div className="filter-actions">
          <select
            value={filter}
            onChange={(event) =>
              setFilter(event.target.value as InventoryTransactionType | "")
            }
          >
            <option value="">{t("allTypes")}</option>
            <option value="sale">{t("sale")}</option>
            <option value="purchase">{t("purchase")}</option>
            <option value="adjustment">{t("adjustment")}</option>
          </select>
          <button className="secondary-button" onClick={loadTransactions}>
            <RefreshCw size={17} className={loading ? "spin" : ""} />
            {t("retry")}
          </button>
        </div>
      </header>

      {error && <div className="feedback-banner error">{error}</div>}

      <section className="panel inventory-table">
        <div className="inventory-row inventory-head">
          <span>{t("product")}</span>
          <span>{t("type")}</span>
          <span>{t("change")}</span>
          <span>{t("reference")}</span>
          <span>{t("date")}</span>
        </div>
        {transactions.map((transaction) => {
          const positive = Number(transaction.quantity_change) > 0;
          return (
            <div className="inventory-row animated-line" key={transaction.id}>
              <div className="transaction-product">
                <span className={`transaction-icon ${positive ? "positive" : "negative"}`}>
                  {positive ? <ArrowUpRight size={17} /> : <ArrowDownLeft size={17} />}
                </span>
                <strong>{transaction.product_name}</strong>
              </div>
              <span className={`type-pill ${transaction.transaction_type}`}>
                {t(transaction.transaction_type)}
              </span>
              <strong className={positive ? "quantity-positive" : "quantity-negative"}>
                {positive ? "+" : ""}
                {formatQuantityWithUnit(
                  Number(transaction.quantity_change),
                  transaction.is_weighted,
                  transaction.is_weighted ? transaction.unit : null,
                  locale,
                  number,
                )}
              </strong>
              <span>
                {transaction.related_id
                  ? `#${number(transaction.related_id)}`
                  : "—"}
              </span>
              <time>
                {new Intl.DateTimeFormat(locale, {
                  dateStyle: "medium",
                  timeStyle: "short",
                }).format(new Date(transaction.timestamp))}
              </time>
            </div>
          );
        })}
        {!loading && !transactions.length && (
          <div className="empty-state">{t("noTransactions")}</div>
        )}
        {loading && <div className="empty-state">{t("loading")}</div>}
      </section>
    </main>
  );
}
