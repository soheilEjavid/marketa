import { useEffect, useState } from "react";
import { Clock, Lock, Unlock, X } from "lucide-react";

import { closeShift, getCurrentShift, getUsers, openShift } from "../api";
import { useI18n } from "../i18n";
import { Modal } from "./Modal";
import type { CashierShift, UserSummary } from "../types";

const LAST_CASHIER_KEY = "marketa-last-cashier-id";

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function CashierShiftBar() {
  const { t, money } = useI18n();
  const [shift, setShift] = useState<CashierShift | null>(null);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showOpenForm, setShowOpenForm] = useState(false);
  const [showCloseForm, setShowCloseForm] = useState(false);
  const [closeResult, setCloseResult] = useState<CashierShift | null>(null);
  const [cashierId, setCashierId] = useState<number | "">("");
  const [openingCash, setOpeningCash] = useState("");
  const [closingCash, setClosingCash] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function load() {
    setLoading(true);
    Promise.all([getCurrentShift(), getUsers()])
      .then(([currentShift, userList]) => {
        setShift(currentShift);
        setUsers(userList);
        const savedId = Number(localStorage.getItem(LAST_CASHIER_KEY) || "");
        if (!currentShift && savedId && userList.some((user) => user.id === savedId)) {
          setCashierId(savedId);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleOpen() {
    if (!cashierId || !openingCash.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const opened = await openShift(Number(cashierId), Number(openingCash));
      localStorage.setItem(LAST_CASHIER_KEY, String(cashierId));
      setShift(opened);
      setShowOpenForm(false);
      setOpeningCash("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("apiError"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleClose() {
    if (!shift || !closingCash.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const closed = await closeShift(shift.id, Number(closingCash));
      setCloseResult(closed);
      setShift(null);
      setShowCloseForm(false);
      setClosingCash("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("apiError"));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return null;

  return (
    <div className="cashier-shift-bar">
      {shift ? (
        <>
          <span className="shift-status-pill open">
            <Unlock size={14} /> {shift.cashier_name}
          </span>
          <span className="shift-time">
            <Clock size={12} /> {formatTime(shift.opened_at)}
          </span>
          <button type="button" className="secondary-button" onClick={() => setShowCloseForm(true)}>
            {t("closeShift")}
          </button>
        </>
      ) : (
        <>
          <span className="shift-status-pill closed">
            <Lock size={14} /> {t("noOpenShift")}
          </span>
          <button type="button" className="secondary-button" onClick={() => setShowOpenForm(true)}>
            {t("openShift")}
          </button>
        </>
      )}

      {showOpenForm && (
        <Modal onClose={() => setShowOpenForm(false)}>
          <div
            className="party-form"
            style={{ width: "min(420px, 100%)" }}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="panel-heading">
              <h2>{t("openShift")}</h2>
              <button className="icon-button" onClick={() => setShowOpenForm(false)} aria-label={t("cancel")}>
                <X size={18} />
              </button>
            </div>
            {error && <div className="feedback-banner error">{error}</div>}
            <label className="field">
              <span>{t("cashier")}</span>
              <select
                value={cashierId}
                onChange={(event) => setCashierId(event.target.value ? Number(event.target.value) : "")}
              >
                <option value="">{t("chooseCashier")}</option>
                {users.map((user) => (
                  <option value={user.id} key={user.id}>
                    {user.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t("openingCash")}</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={openingCash}
                onChange={(event) => setOpeningCash(event.target.value)}
              />
            </label>
            <div className="form-actions">
              <button className="secondary-button" onClick={() => setShowOpenForm(false)}>
                {t("cancel")}
              </button>
              <button
                className="primary-button"
                disabled={submitting || !cashierId || !openingCash.trim()}
                onClick={handleOpen}
              >
                {submitting ? t("loading") : t("openShift")}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {showCloseForm && shift && (
        <Modal onClose={() => setShowCloseForm(false)}>
          <div
            className="party-form"
            style={{ width: "min(420px, 100%)" }}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="panel-heading">
              <h2>{t("closeShift")}</h2>
              <button className="icon-button" onClick={() => setShowCloseForm(false)} aria-label={t("cancel")}>
                <X size={18} />
              </button>
            </div>
            {error && <div className="feedback-banner error">{error}</div>}
            <label className="field">
              <span>{t("countedCash")}</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={closingCash}
                onChange={(event) => setClosingCash(event.target.value)}
              />
            </label>
            <div className="form-actions">
              <button className="secondary-button" onClick={() => setShowCloseForm(false)}>
                {t("cancel")}
              </button>
              <button className="primary-button" disabled={submitting || !closingCash.trim()} onClick={handleClose}>
                {submitting ? t("loading") : t("closeShift")}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {closeResult && (
        <Modal onClose={() => setCloseResult(null)}>
          <div
            className="party-form"
            style={{ width: "min(420px, 100%)" }}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="panel-heading">
              <h2>{t("shiftClosedTitle")}</h2>
              <button className="icon-button" onClick={() => setCloseResult(null)} aria-label={t("cancel")}>
                <X size={18} />
              </button>
            </div>
            <div className="shift-close-summary">
              <div>
                <span>{t("expectedCash")}</span>
                <strong>{money(Number(closeResult.expected_cash))}</strong>
              </div>
              <div>
                <span>{t("countedCash")}</span>
                <strong>{money(Number(closeResult.closing_cash))}</strong>
              </div>
              <div>
                <span>{t("difference")}</span>
                <strong
                  className={
                    Number(closeResult.difference) < 0
                      ? "quantity-negative"
                      : Number(closeResult.difference) > 0
                        ? "quantity-positive"
                        : ""
                  }
                >
                  {money(Number(closeResult.difference))}
                </strong>
              </div>
            </div>
            <div className="form-actions">
              <button className="primary-button" onClick={() => setCloseResult(null)}>
                {t("gotIt")}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
