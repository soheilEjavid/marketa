import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Plus, UserCog } from "lucide-react";

import { createUser, getErrorMessage, getUsers, setUserActive } from "../api";
import { useI18n } from "../i18n";
import type { UserCreate, UserSummary } from "../types";

const ROLES: UserCreate["role"][] = ["admin", "cashier", "manager", "inventory_manager", "accountant"];

const emptyForm: UserCreate = {
  username: "",
  password: "",
  full_name: "",
  role: "cashier",
};

export function Users() {
  const { t } = useI18n();
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<UserCreate>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      setUsers(await getUsers(!showInactive));
    } catch {
      setError(t("apiError"));
    } finally {
      setLoading(false);
    }
  }, [showInactive, t]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      const created = await createUser(form);
      setMessage(`${t("userCreated")}: ${created.full_name}`);
      setForm(emptyForm);
      loadUsers();
    } catch (err) {
      setError(getErrorMessage(err, t));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleToggleActive(user: UserSummary) {
    setError("");
    try {
      await setUserActive(user.id, !user.is_active);
      loadUsers();
    } catch (err) {
      setError(getErrorMessage(err, t));
    }
  }

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("userManagement")}</p>
          <h1>{t("userManagement")}</h1>
        </div>
      </header>

      {error && <div className="feedback-banner error">{error}</div>}
      {message && <div className="feedback-banner success">{message}</div>}

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-heading">
          <h2>
            <UserCog size={18} style={{ verticalAlign: "middle", marginInlineEnd: 6 }} />
            {t("newUser")}
          </h2>
        </div>
        <form className="form-grid" onSubmit={handleSubmit}>
          <label className="field">
            <span>{t("username")}</span>
            <input
              value={form.username}
              onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
              required
              minLength={3}
            />
          </label>
          <label className="field">
            <span>{t("password")}</span>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              required
              minLength={8}
            />
          </label>
          <label className="field">
            <span>{t("fullName")}</span>
            <input
              value={form.full_name}
              onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
              required
            />
          </label>
          <label className="field">
            <span>{t("role")}</span>
            <select
              value={form.role}
              onChange={(e) => setForm((f) => ({ ...f, role: e.target.value as UserCreate["role"] }))}
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {t(role)}
                </option>
              ))}
            </select>
          </label>
          <div className="form-actions full-span">
            <button className="primary-button" type="submit" disabled={submitting}>
              <Plus size={16} />
              {submitting ? t("loading") : t("createUser")}
            </button>
          </div>
        </form>
      </section>

      <section className="panel report-table-wrap">
        <div className="panel-heading">
          <h2>{t("users")}</h2>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            {t("showInactive")}
          </label>
        </div>
        <div className="report-table">
          <div className="report-table-row report-cols-4 report-head">
            <span className="report-header-cell">{t("fullName")}</span>
            <span className="report-header-cell">{t("username")}</span>
            <span className="report-header-cell">{t("role")}</span>
            <span className="report-header-cell" />
          </div>
          {loading ? (
            <div className="empty-state compact">{t("loading")}</div>
          ) : users.length > 0 ? (
            users.map((user) => (
              <div className="report-table-row report-cols-4 animated-line" key={user.id}>
                <strong>{user.full_name}</strong>
                <span className="muted-text">{user.username}</span>
                <span>{t(user.role)}</span>
                <button
                  type="button"
                  className={`text-button ${user.is_active ? "" : "quantity-positive"}`}
                  onClick={() => handleToggleActive(user)}
                >
                  {user.is_active ? t("deactivate") : t("reactivate")}
                </button>
              </div>
            ))
          ) : (
            <div className="empty-state compact">{t("noData")}</div>
          )}
        </div>
      </section>
    </main>
  );
}
