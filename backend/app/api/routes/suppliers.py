from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.financial import PaymentCreate, PaymentRead, SupplierLedger
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from app.services import suppliers as supplier_service
from app.services import financials
from app.services.audit import record_audit
from app.services.auth import require_role

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

READ_ROLES = ("admin", "cashier", "manager", "accountant")
# Matches product create/update's role set, per the supplier/product parity
# called for in the auth-hardening task write-up.
WRITE_ROLES = ("admin", "manager")


@router.get("", response_model=list[SupplierRead])
async def list_suppliers(
    database: DatabaseSession,
    search: str | None = None,
    active_only: bool = True,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return supplier_service.list_suppliers(
        database,
        search=search,
        active_only=active_only,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    data: SupplierCreate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    supplier = supplier_service.create_supplier(database, data)
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="create",
        entity_type="supplier",
        entity_id=supplier.id,
        details=f"Created supplier {supplier.name}",
    )
    return supplier


@router.get("/{supplier_id}", response_model=SupplierRead)
async def get_supplier(
    supplier_id: int,
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    supplier = supplier_service.get_supplier(database, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@router.patch("/{supplier_id}", response_model=SupplierRead)
async def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    supplier = supplier_service.get_supplier(database, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    result = supplier_service.update_supplier(database, supplier, data)
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="update",
        entity_type="supplier",
        entity_id=supplier_id,
        details=f"Updated supplier {supplier.name}",
    )
    return result


@router.post("/{supplier_id}/payments", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
async def create_supplier_payment(
    supplier_id: int,
    data: PaymentCreate,
    database: DatabaseSession,
    # Matches customer payments' role set exactly, per the task write-up.
    current_user: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    supplier = supplier_service.get_supplier(database, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    try:
        payment = financials.record_supplier_payment(database, supplier, data)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="payment",
            entity_type="supplier_payment",
            entity_id=payment.id,
            details=f"Supplier {supplier.name}, amount={data.amount}",
        )
        return payment
    except financials.FinancialError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{supplier_id}/ledger", response_model=SupplierLedger)
async def get_supplier_ledger(
    supplier_id: int,
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    supplier = supplier_service.get_supplier(database, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {"supplier_id": supplier.id, "supplier_name": supplier.name, "balance": supplier.balance, "entries": financials.supplier_ledger(database, supplier)}
