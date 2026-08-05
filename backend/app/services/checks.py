from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import CheckStatus, PaymentMethod, Supplier, SupplierPayment


class CheckError(ValueError):
    pass


def _base_query():
    return (
        select(SupplierPayment)
        .where(SupplierPayment.method == PaymentMethod.CHECK)
        .options(selectinload(SupplierPayment.supplier), selectinload(SupplierPayment.purchase))
    )


def list_checks(
    database: Session,
    *,
    status: CheckStatus | None = None,
    sort: str = "due_asc",
    search: str | None = None,
    limit: int = 200,
) -> list[SupplierPayment]:
    query = _base_query()
    if status is not None:
        query = query.where(SupplierPayment.check_status == status)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.outerjoin(Supplier, SupplierPayment.supplier_id == Supplier.id).where(
            Supplier.name.ilike(pattern)
        )

    if sort == "due_desc":
        query = query.order_by(SupplierPayment.check_due_date.desc().nulls_last())
    elif sort == "amount_desc":
        query = query.order_by(SupplierPayment.amount.desc())
    else:
        query = query.order_by(SupplierPayment.check_due_date.asc().nulls_last())

    # Bounded because this list only ever grows: a shop writing a few
    # cheques a week accumulates thousands over a few years, and both the
    # payload and the rendered table grew linearly with no ceiling. The
    # default is generous enough that a real shop sees everything it cares
    # about, and the status filter above narrows it further.
    return list(database.scalars(query.limit(limit)))


def get_check(database: Session, check_id: int) -> SupplierPayment | None:
    return database.scalar(
        _base_query().where(SupplierPayment.id == check_id)
    )


def update_check_status(
    database: Session, check: SupplierPayment, new_status: CheckStatus
) -> SupplierPayment:
    if check.method != PaymentMethod.CHECK:
        raise CheckError("This payment line is not a check")
    check.check_status = new_status
    database.commit()
    database.refresh(check)
    return check


def check_totals(database: Session) -> dict[str, Decimal]:
    """Total pending-check amount due within a rolling 7-day / 30-day window
    from today, counting anything overdue-but-still-pending as already due
    (the window is "due_date <= today + N days", not a strict future range).

    This is the single shared calculation for both the Check Management page
    summary bar and the dashboard totals widget — do not recompute this
    elsewhere.
    """
    today = date.today()
    pending = list(
        database.scalars(
            _base_query().where(SupplierPayment.check_status == CheckStatus.PENDING)
        )
    )
    week_cutoff = today + timedelta(days=7)
    month_cutoff = today + timedelta(days=30)
    due_this_week = sum(
        (line.amount for line in pending if line.check_due_date and line.check_due_date <= week_cutoff),
        Decimal("0"),
    )
    due_this_month = sum(
        (line.amount for line in pending if line.check_due_date and line.check_due_date <= month_cutoff),
        Decimal("0"),
    )
    return {"due_this_week": due_this_week, "due_this_month": due_this_month}


def to_check_read(payment: SupplierPayment) -> dict:
    return {
        "id": payment.id,
        "supplier_id": payment.supplier_id,
        "supplier_name": payment.supplier.name if payment.supplier else None,
        "purchase_id": payment.purchase_id,
        "purchase_invoice_number": payment.purchase.invoice_number if payment.purchase else None,
        "amount": payment.amount,
        "check_number": payment.check_number,
        "check_bank_name": payment.check_bank_name,
        "check_due_date": payment.check_due_date,
        "check_status": payment.check_status,
        "notes": payment.notes,
        "paid_at": payment.paid_at,
    }
