import { useCallback, useEffect, useMemo, useState, type ChangeEvent } from "react";
import { Banknote, ImagePlus, Plus, Receipt, Wallet } from "lucide-react";

import {
  ApiError,
  createExpense,
  createSalaryAdvance,
  createSalaryPayment,
  getErrorMessage,
  getExpenseCategories,
  getExpenses,
  getSalaryAdvances,
  getSalaryPayments,
  getUsers,
  updateExpense,
} from "../api";
import { JalaliDatePicker } from "../components/JalaliDatePicker";
import { Modal } from "../components/Modal";
import { useI18n } from "../i18n";
import { canViewSalaries } from "../permissions";
import { getSession } from "../session";
import { isoToJalaliStr } from "../utils/jalali";
import type { Expense, ExpensePaymentMethod, SalaryAdvance, SalaryPayment, UserSummary } from "../types";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

// Mirrors ProductFormModal.tsx's own resizeImageToDataUrl — kept local
// rather than extracted, to avoid touching that unrelated file for this
// feature.
function resizeImageToDataUrl(file: File, maxDimension: number, quality: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("read failed"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("decode failed"));
      img.onload = () => {
        const scale = Math.min(1, maxDimension / Math.max(img.width, img.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("canvas unsupported"));
          return;
        }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL("image/jpeg", quality));
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);
  });
}

type ExpenseTab = "general" | "salary";

function AddExpenseModal({
  categories,
  onClose,
  onSaved,
}: {
  categories: string[];
  onClose: () => void;
  onSaved: (expense: Expense) => void;
}) {
  const { t } = useI18n();
  const [category, setCategory] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState("");
  const [description, setDescription] = useState("");
  const [isRecurring, setIsRecurring] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<ExpensePaymentMethod>("cash");
  const [receiptImageUrl, setReceiptImageUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleReceiptChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_IMAGE_BYTES) {
      setError(t("apiError"));
      return;
    }
    try {
      // Simple photo upload only — no OCR wiring. The future connection
      // point for reading receipts automatically is invoice-scanner.ts
      // (already used for purchase-invoice scanning); this stays untouched
      // and out of scope for this feature, per docs/expense-management.md.
      const dataUrl = await resizeImageToDataUrl(file, 640, 0.82);
      setReceiptImageUrl(dataUrl);
    } catch {
      setError(t("apiError"));
    }
  }

  async function handleSubmit() {
    if (!category.trim() || !amount || !date) return;
    setSaving(true);
    setError("");
    try {
      const expense = await createExpense({
        category: category.trim(),
        amount: Number(amount),
        date,
        description: description.trim() || null,
        is_recurring: isRecurring,
        payment_method: paymentMethod,
        receipt_image_url: receiptImageUrl,
      });
      onSaved(expense);
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, t));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal onClose={onClose}>
      <div className="party-form" style={{ width: "min(480px, 100%)" }} onMouseDown={(e) => e.stopPropagation()}>
        <div className="panel-heading">
          <h2>{t("addExpense")}</h2>
        </div>

        {error && <div className="feedback-banner error">{error}</div>}

        <label className="field">
          <span>{t("expenseCategory")}</span>
          <input
            list="expense-category-suggestions"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            autoFocus
          />
          <datalist id="expense-category-suggestions">
            {categories.map((name) => (
              <option value={name} key={name} />
            ))}
          </datalist>
        </label>

        <label className="field">
          <span>{t("expenseAmount")}</span>
          <input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>

        <label className="field">
          <span>{t("expenseDate")}</span>
          <JalaliDatePicker value={date} onChange={setDate} />
        </label>

        <label className="field">
          <span>{t("expenseDescription")} ({t("optional")})</span>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
        </label>

        <label className="field">
          <span>{t("expensePaymentMethod")}</span>
          <select value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value as ExpensePaymentMethod)}>
            <option value="cash">{t("paymentMethodCash")}</option>
            <option value="bank">{t("paymentMethodBank")}</option>
          </select>
        </label>

        <label className="checkbox-field">
          <input type="checkbox" checked={isRecurring} onChange={(e) => setIsRecurring(e.target.checked)} />
          <span>{t("isRecurringExpense")}</span>
        </label>

        <label className="field">
          <span>{t("receiptImage")} ({t("optional")})</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {receiptImageUrl ? (
              <img src={receiptImageUrl} alt="" style={{ width: 56, height: 56, objectFit: "cover", borderRadius: 8 }} />
            ) : (
              <span className="product-avatar" style={{ width: 56, height: 56 }}>
                <ImagePlus size={18} />
              </span>
            )}
            <label className="secondary-button" style={{ cursor: "pointer" }}>
              {t("uploadReceipt")}
              <input type="file" accept="image/*" onChange={handleReceiptChange} style={{ display: "none" }} />
            </label>
          </div>
        </label>

        <div className="form-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            {t("cancel")}
          </button>
          <button type="button" className="primary-button" disabled={saving} onClick={handleSubmit}>
            {saving ? t("loading") : t("save")}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function AddSalaryAdvanceModal({
  employees,
  onClose,
  onSaved,
}: {
  employees: UserSummary[];
  onClose: () => void;
  onSaved: (advance: SalaryAdvance) => void;
}) {
  const { t } = useI18n();
  const [employeeId, setEmployeeId] = useState<number | "">("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    if (!employeeId || !amount || !date) return;
    setSaving(true);
    setError("");
    try {
      const advance = await createSalaryAdvance({
        employee_id: Number(employeeId),
        amount: Number(amount),
        date,
        notes: notes.trim() || null,
      });
      onSaved(advance);
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, t));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal onClose={onClose}>
      <div className="party-form" style={{ width: "min(420px, 100%)" }} onMouseDown={(e) => e.stopPropagation()}>
        <div className="panel-heading">
          <h2>{t("addSalaryAdvance")}</h2>
        </div>

        {error && <div className="feedback-banner error">{error}</div>}

        <label className="field">
          <span>{t("employee")}</span>
          <select value={employeeId} onChange={(e) => setEmployeeId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">{t("selectEmployee")}</option>
            {employees.map((employee) => (
              <option value={employee.id} key={employee.id}>
                {employee.full_name}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>{t("salaryAdvanceAmount")}</span>
          <input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>

        <label className="field">
          <span>{t("expenseDate")}</span>
          <JalaliDatePicker value={date} onChange={setDate} />
        </label>

        <label className="field">
          <span>{t("expenseDescription")} ({t("optional")})</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        </label>

        <div className="form-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            {t("cancel")}
          </button>
          <button type="button" className="primary-button" disabled={saving} onClick={handleSubmit}>
            {saving ? t("loading") : t("save")}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function AddSalaryPaymentModal({
  employees,
  unsettledByEmployee,
  onClose,
  onSaved,
}: {
  employees: UserSummary[];
  unsettledByEmployee: Map<number, number>;
  onClose: () => void;
  onSaved: (payment: SalaryPayment) => void;
}) {
  const { t, number, money } = useI18n();
  const [employeeId, setEmployeeId] = useState<number | "">("");
  const [periodYear, setPeriodYear] = useState("1405");
  const [periodMonth, setPeriodMonth] = useState("1");
  const [baseAmount, setBaseAmount] = useState("");
  const [bonusAmount, setBonusAmount] = useState("0");
  const [otherDeductions, setOtherDeductions] = useState("0");
  const [paymentMethod, setPaymentMethod] = useState<ExpensePaymentMethod>("cash");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const unsettledAdvanceTotal = employeeId ? unsettledByEmployee.get(Number(employeeId)) ?? 0 : 0;

  async function handleSubmit() {
    if (!employeeId || !baseAmount) return;
    setSaving(true);
    setError("");
    try {
      const payment = await createSalaryPayment({
        employee_id: Number(employeeId),
        period_year: Number(periodYear),
        period_month: Number(periodMonth),
        base_amount: Number(baseAmount),
        bonus_amount: Number(bonusAmount) || 0,
        other_deductions_amount: Number(otherDeductions) || 0,
        payment_method: paymentMethod,
        notes: notes.trim() || null,
      });
      onSaved(payment);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(t("duplicateSalaryPaymentError"));
      } else {
        setError(getErrorMessage(err, t));
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal onClose={onClose}>
      <div className="party-form" style={{ width: "min(480px, 100%)" }} onMouseDown={(e) => e.stopPropagation()}>
        <div className="panel-heading">
          <h2>{t("addSalaryPayment")}</h2>
        </div>

        {error && <div className="feedback-banner error">{error}</div>}

        <label className="field">
          <span>{t("employee")}</span>
          <select value={employeeId} onChange={(e) => setEmployeeId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">{t("selectEmployee")}</option>
            {employees.map((employee) => (
              <option value={employee.id} key={employee.id}>
                {employee.full_name}
              </option>
            ))}
          </select>
        </label>

        <div className="field-row">
          <label className="field">
            <span>{t("salaryPeriodYear")}</span>
            <input type="number" value={periodYear} onChange={(e) => setPeriodYear(e.target.value)} />
          </label>
          <label className="field">
            <span>{t("salaryPeriodMonth")}</span>
            <input type="number" min="1" max="12" value={periodMonth} onChange={(e) => setPeriodMonth(e.target.value)} />
          </label>
        </div>

        <label className="field">
          <span>{t("baseSalary")}</span>
          <input type="number" min="0" step="0.01" value={baseAmount} onChange={(e) => setBaseAmount(e.target.value)} />
        </label>

        <label className="field">
          <span>{t("bonusAmount")}</span>
          <input type="number" min="0" step="0.01" value={bonusAmount} onChange={(e) => setBonusAmount(e.target.value)} />
        </label>

        <label className="field">
          <span>{t("otherDeductions")}</span>
          <input
            type="number"
            min="0"
            step="0.01"
            value={otherDeductions}
            onChange={(e) => setOtherDeductions(e.target.value)}
          />
          {unsettledAdvanceTotal > 0 && (
            <small className="field-hint">
              {t("foldedAdvancesNote")} ({money(unsettledAdvanceTotal)})
            </small>
          )}
        </label>

        <label className="field">
          <span>{t("expensePaymentMethod")}</span>
          <select value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value as ExpensePaymentMethod)}>
            <option value="cash">{t("paymentMethodCash")}</option>
            <option value="bank">{t("paymentMethodBank")}</option>
          </select>
        </label>

        <label className="field">
          <span>{t("expenseDescription")} ({t("optional")})</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        </label>

        <div className="form-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            {t("cancel")}
          </button>
          <button type="button" className="primary-button" disabled={saving} onClick={handleSubmit}>
            {saving ? t("loading") : t("save")}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export function Expenses() {
  const { t, money, number } = useI18n();
  const role = getSession()?.role ?? "";
  // The "حقوق و دستمزد" tab is genuinely absent from the DOM for non-admins
  // — not CSS-hidden — because `tab` can never become "salary" for them
  // (the button that would set it doesn't render) and the render branch
  // below is gated by this same boolean, not just the button.
  const canSeeSalaryTab = canViewSalaries(role);

  const [tab, setTab] = useState<ExpenseTab>("general");

  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [expensesLoading, setExpensesLoading] = useState(true);
  const [showAddExpense, setShowAddExpense] = useState(false);

  const [employees, setEmployees] = useState<UserSummary[]>([]);
  const [advances, setAdvances] = useState<SalaryAdvance[]>([]);
  const [payments, setPayments] = useState<SalaryPayment[]>([]);
  const [salaryLoading, setSalaryLoading] = useState(true);
  const [showAddAdvance, setShowAddAdvance] = useState(false);
  const [showAddPayment, setShowAddPayment] = useState(false);

  const loadExpenses = useCallback(async () => {
    setExpensesLoading(true);
    try {
      const [expenseRows, categoryRows] = await Promise.all([getExpenses(), getExpenseCategories()]);
      setExpenses(expenseRows);
      setCategories(categoryRows);
    } catch {
      setExpenses([]);
    } finally {
      setExpensesLoading(false);
    }
  }, []);

  useEffect(() => {
    loadExpenses();
  }, [loadExpenses]);

  const loadSalaryData = useCallback(async () => {
    if (!canSeeSalaryTab) return;
    setSalaryLoading(true);
    try {
      const [employeeRows, advanceRows, paymentRows] = await Promise.all([
        getUsers(true),
        getSalaryAdvances(),
        getSalaryPayments(),
      ]);
      setEmployees(employeeRows);
      setAdvances(advanceRows);
      setPayments(paymentRows);
    } catch {
      setAdvances([]);
      setPayments([]);
    } finally {
      setSalaryLoading(false);
    }
  }, [canSeeSalaryTab]);

  useEffect(() => {
    loadSalaryData();
  }, [loadSalaryData]);

  const unsettledByEmployee = useMemo(() => {
    const map = new Map<number, number>();
    for (const advance of advances) {
      if (advance.settled_in_payment_id !== null) continue;
      map.set(advance.employee_id, (map.get(advance.employee_id) ?? 0) + Number(advance.amount));
    }
    return map;
  }, [advances]);

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("expenses")}</p>
          <h1>{t("expenses")}</h1>
        </div>
      </header>

      <div className="tabs" role="tablist" aria-label={t("expenses")}>
        <button className={`tab ${tab === "general" ? "active" : ""}`} role="tab" onClick={() => setTab("general")}>
          <Receipt size={17} strokeWidth={1.8} />
          {t("generalExpensesTab")}
        </button>
        {canSeeSalaryTab && (
          <button className={`tab ${tab === "salary" ? "active" : ""}`} role="tab" onClick={() => setTab("salary")}>
            <Wallet size={17} strokeWidth={1.8} />
            {t("salaryPaymentsTab")}
          </button>
        )}
      </div>

      {tab === "general" && (
        <section className="panel report-table-wrap">
          <div className="panel-heading">
            <h2>{t("generalExpensesTab")}</h2>
            <button type="button" className="primary-button" onClick={() => setShowAddExpense(true)}>
              <Plus size={18} />
              {t("addExpense")}
            </button>
          </div>

          <div className="report-table">
            <div className="report-table-row report-cols-5 report-head">
              <span className="report-header-cell">{t("expenseCategory")}</span>
              <span className="report-header-cell">{t("expenseAmount")}</span>
              <span className="report-header-cell">{t("expenseDate")}</span>
              <span className="report-header-cell">{t("expensePaymentMethod")}</span>
              <span className="report-header-cell" />
            </div>
            {expensesLoading ? (
              <div className="empty-state compact">{t("loading")}</div>
            ) : expenses.length > 0 ? (
              expenses.map((expense) => (
                <div className="report-table-row report-cols-5 animated-line" key={expense.id}>
                  <strong>
                    {expense.category}
                    {expense.is_recurring && (
                      <span className="subtle-chip" style={{ marginInlineStart: 6 }}>
                        {t("isRecurringExpense")}
                      </span>
                    )}
                  </strong>
                  <span>{money(Number(expense.amount))}</span>
                  <span className="report-date-cell">{isoToJalaliStr(expense.date)}</span>
                  <span className="muted-text">
                    {expense.payment_method === "cash" ? t("paymentMethodCash") : t("paymentMethodBank")}
                  </span>
                  {expense.receipt_image_url ? (
                    <img
                      src={expense.receipt_image_url}
                      alt=""
                      style={{ width: 32, height: 32, objectFit: "cover", borderRadius: 6 }}
                    />
                  ) : (
                    <span />
                  )}
                </div>
              ))
            ) : (
              <div className="empty-state compact">{t("noExpenses")}</div>
            )}
          </div>
        </section>
      )}

      {tab === "salary" && canSeeSalaryTab && (
        <>
          <section className="panel report-table-wrap">
            <div className="panel-heading">
              <h2>{t("salaryAdvances")}</h2>
              <button type="button" className="secondary-button" onClick={() => setShowAddAdvance(true)}>
                <Banknote size={16} />
                {t("addSalaryAdvance")}
              </button>
            </div>
            <div className="report-table">
              <div className="report-table-row report-cols-4 report-head">
                <span className="report-header-cell">{t("employee")}</span>
                <span className="report-header-cell">{t("salaryAdvanceAmount")}</span>
                <span className="report-header-cell">{t("expenseDate")}</span>
                <span className="report-header-cell" />
              </div>
              {salaryLoading ? (
                <div className="empty-state compact">{t("loading")}</div>
              ) : advances.length > 0 ? (
                advances.map((advance) => (
                  <div className="report-table-row report-cols-4 animated-line" key={advance.id}>
                    <strong>{advance.employee_name}</strong>
                    <span>{money(Number(advance.amount))}</span>
                    <span className="report-date-cell">{isoToJalaliStr(advance.date)}</span>
                    <span className={`metric-badge ${advance.settled_in_payment_id ? "metric-badge-neutral" : "metric-badge-danger"}`}>
                      {advance.settled_in_payment_id ? t("settledBadge") : t("unsettledBadge")}
                    </span>
                  </div>
                ))
              ) : (
                <div className="empty-state compact">{t("noSalaryAdvances")}</div>
              )}
            </div>
          </section>

          <section className="panel report-table-wrap" style={{ marginTop: 16 }}>
            <div className="panel-heading">
              <h2>{t("salaryPayments")}</h2>
              <button type="button" className="primary-button" onClick={() => setShowAddPayment(true)}>
                <Plus size={18} />
                {t("addSalaryPayment")}
              </button>
            </div>
            <div className="report-table">
              <div className="report-table-row report-cols-5 report-head">
                <span className="report-header-cell">{t("employee")}</span>
                <span className="report-header-cell">{t("baseSalary")}</span>
                <span className="report-header-cell">{t("deductionsAmount")}</span>
                <span className="report-header-cell">{t("netSalary")}</span>
                <span className="report-header-cell" />
              </div>
              {salaryLoading ? (
                <div className="empty-state compact">{t("loading")}</div>
              ) : payments.length > 0 ? (
                payments.map((payment) => (
                  <div className="report-table-row report-cols-5 animated-line" key={payment.id}>
                    <strong>{payment.employee_name}</strong>
                    <span>{money(Number(payment.base_amount))}</span>
                    <span className="quantity-negative">{money(Number(payment.deductions_amount))}</span>
                    <strong className="metric-badge metric-badge-success">{money(Number(payment.net_amount))}</strong>
                    <span className="muted-text">
                      {number(payment.period_year)}/{number(payment.period_month)}
                    </span>
                  </div>
                ))
              ) : (
                <div className="empty-state compact">{t("noSalaryPayments")}</div>
              )}
            </div>
          </section>
        </>
      )}

      {showAddExpense && (
        <AddExpenseModal
          categories={categories}
          onClose={() => setShowAddExpense(false)}
          onSaved={(expense) => setExpenses((current) => [expense, ...current])}
        />
      )}
      {showAddAdvance && (
        <AddSalaryAdvanceModal
          employees={employees}
          onClose={() => setShowAddAdvance(false)}
          onSaved={(advance) => setAdvances((current) => [advance, ...current])}
        />
      )}
      {showAddPayment && (
        <AddSalaryPaymentModal
          employees={employees}
          unsettledByEmployee={unsettledByEmployee}
          onClose={() => setShowAddPayment(false)}
          onSaved={(payment) => {
            setPayments((current) => [payment, ...current]);
            loadSalaryData();
          }}
        />
      )}
    </main>
  );
}
