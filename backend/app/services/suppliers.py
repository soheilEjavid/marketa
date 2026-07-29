from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entities import Supplier
from app.schemas.supplier import SupplierCreate, SupplierUpdate


def list_suppliers(
    database: Session,
    *,
    search: str | None = None,
    active_only: bool = True,
    offset: int = 0,
    limit: int = 100,
) -> list[Supplier]:
    query = select(Supplier).order_by(Supplier.name, Supplier.id)
    if active_only:
        query = query.where(Supplier.is_active.is_(True))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                Supplier.name.ilike(pattern),
                Supplier.contact_person.ilike(pattern),
                Supplier.phone.ilike(pattern),
            )
        )
    return list(database.scalars(query.offset(offset).limit(limit)))


def get_supplier(database: Session, supplier_id: int) -> Supplier | None:
    return database.get(Supplier, supplier_id)


def create_supplier(database: Session, data: SupplierCreate) -> Supplier:
    supplier = Supplier(**data.model_dump())
    database.add(supplier)
    database.commit()
    database.refresh(supplier)
    return supplier


def update_supplier(
    database: Session, supplier: Supplier, data: SupplierUpdate
) -> Supplier:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    database.commit()
    database.refresh(supplier)
    return supplier
