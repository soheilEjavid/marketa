from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import Customer, CustomerPayment, PaymentStatus, Purchase, Sale, Supplier, SupplierPayment
from app.schemas.financial import PaymentCreate

class FinancialError(ValueError): pass

def payment_status(total: Decimal, paid: Decimal) -> PaymentStatus:
    if paid <= 0: return PaymentStatus.UNPAID
    if paid >= total: return PaymentStatus.PAID
    return PaymentStatus.PARTIAL

def record_customer_payment(database: Session, customer: Customer, data: PaymentCreate, *, commit: bool = True) -> CustomerPayment:
    sale = database.get(Sale, data.document_id) if data.document_id else None
    if data.document_id and (sale is None or sale.customer_id != customer.id):
        raise FinancialError("Sale does not belong to this customer")
    if sale and data.amount > sale.remaining_amount:
        raise FinancialError("Payment cannot exceed the remaining sale amount")
    # Same guard for an unallocated payment (no document_id, paid against the
    # overall balance) — previously only the sale-specific path above was
    # checked, so an unallocated overpayment silently clamped the balance to
    # zero via max(0, ...) below with no error and no record of the excess.
    if sale is None and data.amount > customer.balance:
        raise FinancialError("Payment cannot exceed the customer's outstanding balance")
    payment = CustomerPayment(customer=customer, sale=sale, amount=data.amount, method=data.method, reference=data.reference, notes=data.notes)
    database.add(payment)
    if sale:
        sale.paid_amount += data.amount
        sale.remaining_amount = sale.total - sale.paid_amount
        sale.payment_status = payment_status(sale.total, sale.paid_amount)
    customer.balance = max(Decimal("0"), customer.balance - data.amount)
    if commit:
        database.commit(); database.refresh(payment)
    return payment

def record_supplier_payment(database: Session, supplier: Supplier, data: PaymentCreate, *, commit: bool = True) -> SupplierPayment:
    purchase = database.get(Purchase, data.document_id) if data.document_id else None
    if data.document_id and (purchase is None or purchase.supplier_id != supplier.id):
        raise FinancialError("Purchase does not belong to this supplier")
    if purchase and data.amount > purchase.remaining_amount:
        raise FinancialError("Payment cannot exceed the remaining purchase amount")
    # Same guard as record_customer_payment for the unallocated case — see
    # that function's comment.
    if purchase is None and data.amount > supplier.balance:
        raise FinancialError("Payment cannot exceed the supplier's outstanding balance")
    payment = SupplierPayment(supplier=supplier, purchase=purchase, amount=data.amount, method=data.method, reference=data.reference, notes=data.notes)
    database.add(payment)
    if purchase:
        purchase.paid_amount += data.amount
        purchase.remaining_amount = purchase.total - purchase.paid_amount
        purchase.payment_status = payment_status(purchase.total, purchase.paid_amount)
    supplier.balance = max(Decimal("0"), supplier.balance - data.amount)
    if commit:
        database.commit(); database.refresh(payment)
    return payment

def customer_ledger(database: Session, customer: Customer) -> list[dict]:
    events = []
    for sale in database.scalars(select(Sale).where(Sale.customer_id == customer.id)):
        events.append((sale.created_at, 0, {"id": f"sale-{sale.id}", "entry_type": "sale", "reference": sale.invoice_number, "description": "فاکتور فروش", "debit": sale.total, "credit": Decimal("0"), "payment_status": sale.payment_status}))
    for payment in database.scalars(select(CustomerPayment).where(CustomerPayment.customer_id == customer.id)):
        events.append((payment.paid_at, 1, {"id": f"payment-{payment.id}", "entry_type": "payment", "reference": payment.reference or f"REC-{payment.id:05d}", "description": "دریافت از مشتری", "debit": Decimal("0"), "credit": payment.amount, "payment_status": None}))
    balance = Decimal("0"); result = []
    for occurred_at, _, entry in sorted(events, key=lambda item: (item[0], item[1])):
        balance += entry["debit"] - entry["credit"]
        result.append({**entry, "occurred_at": occurred_at, "running_balance": balance})
    return result

def supplier_ledger(database: Session, supplier: Supplier) -> list[dict]:
    events = []
    for purchase in database.scalars(select(Purchase).where(Purchase.supplier_id == supplier.id)):
        events.append((purchase.created_at, 0, {"id": f"purchase-{purchase.id}", "entry_type": "purchase", "reference": purchase.invoice_number, "description": "فاکتور خرید", "debit": purchase.total, "credit": Decimal("0"), "payment_status": purchase.payment_status}))
    for payment in database.scalars(select(SupplierPayment).where(SupplierPayment.supplier_id == supplier.id)):
        events.append((payment.paid_at, 1, {"id": f"payment-{payment.id}", "entry_type": "payment", "reference": payment.reference or f"PAY-{payment.id:05d}", "description": "پرداخت به تأمین‌کننده", "debit": Decimal("0"), "credit": payment.amount, "payment_status": None}))
    balance = Decimal("0"); result = []
    for occurred_at, _, entry in sorted(events, key=lambda item: (item[0], item[1])):
        balance += entry["debit"] - entry["credit"]
        result.append({**entry, "occurred_at": occurred_at, "running_balance": balance})
    return result
