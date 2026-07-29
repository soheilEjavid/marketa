import { useState } from "react";
import { Check, Pencil, Plus, X } from "lucide-react";

import { createCategory, getErrorMessage, updateCategory } from "../api";
import { useI18n } from "../i18n";
import { Modal } from "./Modal";
import type { Category } from "../types";

type CategoryManagerModalProps = {
  categories: Category[];
  onClose: () => void;
  onCategoriesChanged: (categories: Category[]) => void;
};

type RowDraft = {
  name: string;
  description: string;
};

function toDraft(category: Category): RowDraft {
  return {
    name: category.name,
    description: category.description ?? "",
  };
}

/**
 * The only place in the app that can reach PATCH /categories/{id} — before
 * this existed, category editing (name/description) was backend-only;
 * category creation only ever set `name` via the quick-add flow in
 * ProductFormModal. Purely a catalog concept — no loyalty program fields
 * belong here (see services/loyalty.py — points earn from a product's own
 * margin/override only, never from its category).
 */
export function CategoryManagerModal({ categories, onClose, onCategoriesChanged }: CategoryManagerModalProps) {
  const { t } = useI18n();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<RowDraft>({ name: "", description: "" });
  const [savingId, setSavingId] = useState<number | null>(null);
  const [rowError, setRowError] = useState("");

  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  function startEdit(category: Category) {
    setEditingId(category.id);
    setDraft(toDraft(category));
    setRowError("");
  }

  async function saveEdit(categoryId: number) {
    setSavingId(categoryId);
    setRowError("");
    try {
      const updated = await updateCategory(categoryId, {
        name: draft.name.trim(),
        description: draft.description.trim() || null,
      });
      onCategoriesChanged(categories.map((category) => (category.id === categoryId ? updated : category)));
      setEditingId(null);
    } catch (error) {
      setRowError(getErrorMessage(error, t));
    } finally {
      setSavingId(null);
    }
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    setCreating(true);
    setCreateError("");
    try {
      const category = await createCategory({ name: newName.trim() });
      onCategoriesChanged([...categories, category]);
      setNewName("");
    } catch (error) {
      setCreateError(getErrorMessage(error, t));
    } finally {
      setCreating(false);
    }
  }

  return (
    <Modal onClose={onClose}>
      <div className="party-form" style={{ width: "min(560px, 100%)" }} onMouseDown={(event) => event.stopPropagation()}>
        <div className="panel-heading">
          <h2>{t("manageCategories")}</h2>
          <button className="icon-button" onClick={onClose} aria-label={t("cancel")}>
            <X size={18} />
          </button>
        </div>

        {categories.length === 0 ? (
          <p className="empty-state compact">{t("noCategories")}</p>
        ) : (
          <div className="report-table">
            <div className="report-table-row report-cols-3 report-head">
              <span className="report-header-cell">{t("categoryName")}</span>
              <span className="report-header-cell">{t("description")}</span>
              <span className="report-header-cell" />
            </div>
            {categories.map((category) => {
              const isEditing = editingId === category.id;
              return (
                <div className="report-table-row report-cols-3 animated-line" key={category.id}>
                  {isEditing ? (
                    <>
                      <input
                        value={draft.name}
                        onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                      />
                      <input
                        value={draft.description}
                        onChange={(event) =>
                          setDraft((current) => ({ ...current, description: event.target.value }))
                        }
                      />
                      <div style={{ display: "flex", gap: 6 }}>
                        <button
                          className="icon-button"
                          disabled={savingId === category.id}
                          onClick={() => saveEdit(category.id)}
                          aria-label={t("save")}
                        >
                          <Check size={16} />
                        </button>
                        <button
                          className="icon-button"
                          onClick={() => setEditingId(null)}
                          aria-label={t("cancel")}
                        >
                          <X size={16} />
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <strong>{category.name}</strong>
                      <span className="muted-text">{category.description || "—"}</span>
                      <button className="icon-button" onClick={() => startEdit(category)} aria-label={t("edit")}>
                        <Pencil size={16} />
                      </button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {rowError && <div className="feedback-banner error">{rowError}</div>}

        <div className="panel-heading" style={{ marginTop: 16 }}>
          <h2 style={{ fontSize: 14 }}>{t("addCategory")}</h2>
        </div>
        <div className="form-grid">
          {createError && <div className="feedback-banner error full-span">{createError}</div>}
          <label className="field">
            <span>{t("categoryName")}</span>
            <input value={newName} onChange={(event) => setNewName(event.target.value)} />
          </label>
          <div className="form-actions full-span">
            <button className="primary-button" type="button" disabled={creating || !newName.trim()} onClick={handleCreate}>
              <Plus size={16} /> {creating ? t("loading") : t("addCategory")}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
