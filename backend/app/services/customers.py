from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate


class DuplicateNationalIdError(ValueError):
    pass


def list_customers(
    database: Session,
    *,
    search: str | None = None,
    active_only: bool = True,
    offset: int = 0,
    limit: int = 100,
) -> list[Customer]:
    query = select(Customer).order_by(Customer.full_name, Customer.id)
    if active_only:
        query = query.where(Customer.is_active.is_(True))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                Customer.full_name.ilike(pattern),
                Customer.phone.ilike(pattern),
                Customer.national_id.ilike(pattern),
            )
        )
    return list(database.scalars(query.offset(offset).limit(limit)))


def get_customer(database: Session, customer_id: int) -> Customer | None:
    return database.get(Customer, customer_id)


def create_customer(database: Session, data: CustomerCreate) -> Customer:
    customer = Customer(**data.model_dump())
    database.add(customer)
    return _commit(database, customer)


def update_customer(
    database: Session, customer: Customer, data: CustomerUpdate
) -> Customer:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    return _commit(database, customer)


def _commit(database: Session, customer: Customer) -> Customer:
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise DuplicateNationalIdError(
            "National ID is already assigned to another customer"
        ) from error
    database.refresh(customer)
    return customer
