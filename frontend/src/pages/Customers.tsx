import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Pencil, Plus, Search, ScrollText, X } from "lucide-react";

import {
  createCustomer,
  getCustomers,
  updateCustomer,
} from "../api";
import { JalaliDatePicker } from "../components/JalaliDatePicker";
import { useI18n } from "../i18n";
import { Modal } from "../components/Modal";
import type { Customer, CustomerInput } from "../types";

type CustomersProps = {
  onViewLedger: (customerId: number, customerName: string) => void;
};

const emptyForm: CustomerInput = {
  full_name: "",
  phone: "",
  national_id: "",
  address: "",
  notes: "",
  credit_limit: 0,
  is_active: true,
  birth_date: "",
};

export function Customers({ onViewLedger }: CustomersProps) {
  const { money, t } = useI18n();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [query, setQuery] = useState("");
  const [form, setForm] = useState<CustomerInput>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadCustomers = useCallback(async (search = "") => {
    setLoading(true);
    setError("");
    try {
      setCustomers(await getCustomers(search));
    } catch {
      setError(t("apiError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    const timeout = window.setTimeout(() => loadCustomers(query), 250);
    return () => window.clearTimeout(timeout);
  }, [loadCustomers, query]);

  function openCreate() {
    setForm(emptyForm);
    setEditingId(null);
    setMessage("");
    setShowForm(true);
  }

  function openEdit(customer: Customer) {
    setForm({
      full_name: customer.full_name,
      phone: customer.phone ?? "",
      national_id: customer.national_id ?? "",
      address: customer.address ?? "",
      notes: customer.notes ?? "",
      credit_limit: Number(customer.credit_limit),
      is_active: customer.is_active,
      birth_date: customer.birth_date ?? "",
    });
    setEditingId(customer.id);
    setMessage("");
    setShowForm(true);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const payload = { ...form, birth_date: form.birth_date || null };
      if (editingId) {
        await updateCustomer(editingId, payload);
      } else {
        await createCustomer(payload);
      }
      setShowForm(false);
      setMessage(t("customerSaved"));
      await loadCustomers(query);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : t("apiError"),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("customers")}</p>
          <h1>{t("customerTitle")}</h1>
          <p>{t("customerSubtitle")}</p>
        </div>
        <button className="primary-button" onClick={openCreate}>
          <Plus size={18} />
          {t("addCustomer")}
        </button>
      </header>

      {message && <div className="feedback-banner success">{message}</div>}
      {error && <div className="feedback-banner error">{error}</div>}

      <section className="panel party-panel">
        <label className="search-field">
          <Search size={18} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("searchCustomers")}
          />
        </label>
        <div className="party-table">
          <div className="party-row party-head customer-columns">
            <span>{t("fullName")}</span>
            <span>{t("phone")}</span>
            <span>{t("creditLimit")}</span>
            <span>{t("balance")}</span>
            <span>{t("status")}</span>
            <span />
          </div>
          {customers.map((customer) => (
            <div className="party-row customer-columns animated-line" key={customer.id}>
              <div>
                <strong>{customer.full_name}</strong>
                <small>{customer.national_id ?? "—"}</small>
              </div>
              <span>{customer.phone ?? "—"}</span>
              <span>{money(Number(customer.credit_limit))}</span>
              <strong>{money(Number(customer.balance))}</strong>
              <span className={`status-pill ${customer.is_active ? "active" : ""}`}>
                {t(customer.is_active ? "active" : "inactive")}
              </span>
              <div className="action-buttons">
                <button className="icon-button" onClick={() => onViewLedger(customer.id, customer.full_name)} title={t("ledger")}>
                  <ScrollText size={16} />
                </button>
                <button className="icon-button" onClick={() => openEdit(customer)}>
                  <Pencil size={16} />
                </button>
              </div>
            </div>
          ))}
          {!loading && !customers.length && (
            <div className="empty-state">{t("noCustomers")}</div>
          )}
          {loading && <div className="empty-state">{t("loading")}</div>}
        </div>
      </section>

      {showForm && (
        <Modal onClose={() => setShowForm(false)}>
          <form
            className="party-form"
            onSubmit={submit}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="panel-heading">
              <h2>{t(editingId ? "editCustomer" : "addCustomer")}</h2>
              <button type="button" className="icon-button" onClick={() => setShowForm(false)}>
                <X size={18} />
              </button>
            </div>
            <div className="form-grid">
              <label className="field">
                <span>{t("fullName")}</span>
                <input
                  required
                  minLength={2}
                  value={form.full_name}
                  onChange={(event) => setForm({ ...form, full_name: event.target.value })}
                />
              </label>
              <label className="field">
                <span>{t("phone")}</span>
                <input
                  value={form.phone ?? ""}
                  onChange={(event) => setForm({ ...form, phone: event.target.value })}
                />
              </label>
              <label className="field">
                <span>{t("nationalId")}</span>
                <input
                  value={form.national_id ?? ""}
                  onChange={(event) => setForm({ ...form, national_id: event.target.value })}
                />
              </label>
              <label className="field">
                <span>{t("creditLimit")}</span>
                <input
                  type="number"
                  min="0"
                  value={form.credit_limit}
                  onChange={(event) => setForm({ ...form, credit_limit: Number(event.target.value) })}
                />
              </label>
              <label className="field">
                <span>{t("birthDate")} ({t("optional")})</span>
                <JalaliDatePicker
                  value={form.birth_date ?? ""}
                  onChange={(isoDate) => setForm({ ...form, birth_date: isoDate })}
                />
              </label>
              <label className="field full-span">
                <span>{t("address")}</span>
                <textarea
                  value={form.address ?? ""}
                  onChange={(event) => setForm({ ...form, address: event.target.value })}
                />
              </label>
              <label className="field full-span">
                <span>{t("notes")}</span>
                <textarea
                  value={form.notes ?? ""}
                  onChange={(event) => setForm({ ...form, notes: event.target.value })}
                />
              </label>
              <label className="checkbox-field full-span">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                />
                <span>{t("active")}</span>
              </label>
            </div>
            <div className="form-actions">
              <button type="button" className="secondary-button" onClick={() => setShowForm(false)}>
                {t("cancel")}
              </button>
              <button className="primary-button" disabled={submitting}>
                {submitting ? t("loading") : t("save")}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </main>
  );
}
