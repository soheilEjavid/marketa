from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.schemas.supplier import SupplierCreate, SupplierUpdate
from app.services.customers import (
    DuplicateNationalIdError,
    create_customer,
    list_customers,
    update_customer,
)
from app.services.suppliers import (
    create_supplier,
    list_suppliers,
    update_supplier,
)


def test_customer_lifecycle_search_and_national_id_uniqueness() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        customer = create_customer(
            database,
            CustomerCreate(
                full_name="فروشگاه نمونه رضایی",
                phone="09121234567",
                national_id="0012345678",
                credit_limit=Decimal("2500000"),
            ),
        )
        update_customer(
            database,
            customer,
            CustomerUpdate(notes="مشتری اعتباری خوش‌حساب"),
        )

        matches = list_customers(database, search="رضایی")
        assert matches == [customer]
        assert customer.balance == Decimal("0.00")
        assert customer.notes == "مشتری اعتباری خوش‌حساب"

        with pytest.raises(DuplicateNationalIdError):
            create_customer(
                database,
                CustomerCreate(
                    full_name="مشتری دوم",
                    national_id="0012345678",
                ),
            )


def test_supplier_lifecycle_and_active_filter() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        supplier = create_supplier(
            database,
            SupplierCreate(
                name="پخش مواد غذایی بهار",
                contact_person="علی اکبری",
                phone="02155550000",
            ),
        )
        update_supplier(
            database, supplier, SupplierUpdate(is_active=False)
        )

        assert list_suppliers(database, search="بهار") == []
        assert list_suppliers(
            database, search="اکبری", active_only=False
        ) == [supplier]


def test_party_names_cannot_be_blank() -> None:
    with pytest.raises(ValidationError):
        CustomerCreate(full_name="  ")
    with pytest.raises(ValidationError):
        SupplierCreate(name=" ")
