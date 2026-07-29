import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Pencil, Plus, Search, ScrollText, X } from "lucide-react";

import {
  createSupplier,
  getSuppliers,
  updateSupplier,
} from "../api";
import { useI18n } from "../i18n";
import { Modal } from "../components/Modal";
import type { Supplier, SupplierInput } from "../types";

type SuppliersProps = {
  onViewLedger: (supplierId: number, supplierName: string) => void;
};

const emptyForm: SupplierInput = {
  name: "",
  contact_person: "",
  phone: "",
  address: "",
  notes: "",
  is_active: true,
};

export function Suppliers({ onViewLedger }: SuppliersProps) {
  const { money, t } = useI18n();
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [query, setQuery] = useState("");
  const [form, setForm] = useState<SupplierInput>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadSuppliers = useCallback(async (search = "") => {
    setLoading(true);
    setError("");
    try {
      setSuppliers(await getSuppliers(search));
    } catch {
      setError(t("apiError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    const timeout = window.setTimeout(() => loadSuppliers(query), 250);
    return () => window.clearTimeout(timeout);
  }, [loadSuppliers, query]);

  function openCreate() {
    setForm(emptyForm);
    setEditingId(null);
    setMessage("");
    setShowForm(true);
  }

  function openEdit(supplier: Supplier) {
    setForm({
      name: supplier.name,
      contact_person: supplier.contact_person ?? "",
      phone: supplier.phone ?? "",
      address: supplier.address ?? "",
      notes: supplier.notes ?? "",
      is_active: supplier.is_active,
    });
    setEditingId(supplier.id);
    setMessage("");
    setShowForm(true);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      if (editingId) {
        await updateSupplier(editingId, form);
      } else {
        await createSupplier(form);
      }
      setShowForm(false);
      setMessage(t("supplierSaved"));
      await loadSuppliers(query);
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
          <p className="eyebrow">{t("suppliers")}</p>
          <h1>{t("supplierTitle")}</h1>
          <p>{t("supplierSubtitle")}</p>
        </div>
        <button className="primary-button" onClick={openCreate}>
          <Plus size={18} />
          {t("addSupplier")}
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
            placeholder={t("searchSuppliers")}
          />
        </label>
        <div className="party-table">
          <div className="party-row party-head supplier-columns">
            <span>{t("supplierName")}</span>
            <span>{t("contactPerson")}</span>
            <span>{t("phone")}</span>
            <span>{t("balance")}</span>
            <span>{t("status")}</span>
            <span />
          </div>
          {suppliers.map((supplier) => (
            <div className="party-row supplier-columns animated-line" key={supplier.id}>
              <strong>{supplier.name}</strong>
              <span>{supplier.contact_person ?? "—"}</span>
              <span>{supplier.phone ?? "—"}</span>
              <strong>{money(Number(supplier.balance))}</strong>
              <span className={`status-pill ${supplier.is_active ? "active" : ""}`}>
                {t(supplier.is_active ? "active" : "inactive")}
              </span>
              <div className="action-buttons">
                <button className="icon-button" onClick={() => onViewLedger(supplier.id, supplier.name)} title={t("ledger")}>
                  <ScrollText size={16} />
                </button>
                <button className="icon-button" onClick={() => openEdit(supplier)}>
                  <Pencil size={16} />
                </button>
              </div>
            </div>
          ))}
          {!loading && !suppliers.length && (
            <div className="empty-state">{t("noSuppliers")}</div>
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
              <h2>{t(editingId ? "editSupplier" : "addSupplier")}</h2>
              <button type="button" className="icon-button" onClick={() => setShowForm(false)}>
                <X size={18} />
              </button>
            </div>
            <div className="form-grid">
              <label className="field">
                <span>{t("supplierName")}</span>
                <input
                  required
                  minLength={2}
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
              </label>
              <label className="field">
                <span>{t("contactPerson")}</span>
                <input
                  value={form.contact_person ?? ""}
                  onChange={(event) => setForm({ ...form, contact_person: event.target.value })}
                />
              </label>
              <label className="field full-span">
                <span>{t("phone")}</span>
                <input
                  value={form.phone ?? ""}
                  onChange={(event) => setForm({ ...form, phone: event.target.value })}
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
