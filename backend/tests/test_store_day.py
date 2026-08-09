"""A sale belongs to the day the shopkeeper thinks it does.

Timestamps are stored in UTC, but every daily figure used to be cut on the
*UTC* calendar day while being read as local. For a Tehran shop that is a
3h30m disagreement: a sale rung up at 01:00 lands at 21:30 UTC the previous
day and was filed there — on the receipt and in the report alike.

These pin both halves: the wall clock the API reports, and which trading day
each report attributes a sale to, at the default boundary (local midnight)
and at a shifted one (a shop trading past midnight).
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core import store_time
from app.core.config import Settings
from app.models.base import Base
from app.models.entities import Product, Sale
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.schemas.sale import SaleRead
from app.services.dashboard import get_summary
from app.services.reports import daily_sales_summary
from app.services.sales import process_sale

TEHRAN = ZoneInfo("Asia/Tehran")


@pytest.fixture
def tehran_store(monkeypatch):
    """A shop in Tehran whose trading day ends at local midnight."""
    monkeypatch.setattr(store_time.settings, "store_timezone", "Asia/Tehran", raising=False)
    monkeypatch.setattr(store_time.settings, "store_day_boundary_hour", 0, raising=False)
    return store_time


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _product(database: Session) -> Product:
    product = Product(
        name="شیر",
        purchase_price=Decimal("60000"),
        sale_price=Decimal("100000"),
        stock_quantity=Decimal("1000"),
        low_stock_threshold=Decimal("2"),
        is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


def _sale_at(database: Session, product: Product, local_time: datetime, invoice: str) -> Sale:
    """Ring up a sale at a wall-clock time in the shop, stored as the UTC
    instant it really was."""
    sale = process_sale(
        database,
        SaleCreate(
            invoice_number=invoice,
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1"))],
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("100000"))],
        ),
    )
    stamp = local_time.replace(tzinfo=TEHRAN).astimezone(UTC)
    database.get(Sale, sale.id).created_at = stamp
    database.commit()
    return sale


# ── The wall clock the API reports ───────────────────────────────────────

def test_the_api_says_which_zone_its_timestamps_are_in(tehran_store) -> None:
    with _session() as database:
        product = _product(database)
        # 00:01 on Mordad 14 — the case that used to be filed a day early.
        _sale_at(database, product, datetime(2026, 8, 5, 0, 1), "S-1")
        sale = database.scalar(select(Sale))

        assert sale.created_at.tzinfo is not None, (
            "a naive timestamp serializes with no offset, and the browser then "
            "reads UTC as local"
        )
        payload = SaleRead.model_validate(sale).model_dump_json()
        assert '"created_at":"2026-08-04T20:31:00Z"' in payload
        # Which is what the shopkeeper's own clock said at the time.
        assert sale.created_at.astimezone(TEHRAN).strftime("%Y-%m-%d %H:%M") == "2026-08-05 00:01"


# ── Which trading day a sale lands on ────────────────────────────────────

@pytest.mark.parametrize(
    ("local_time", "expected_day"),
    [
        (datetime(2026, 8, 4, 23, 59), date(2026, 8, 4)),  # last minute of the day
        (datetime(2026, 8, 5, 0, 1), date(2026, 8, 5)),    # first minute of the next
        (datetime(2026, 8, 5, 2, 30), date(2026, 8, 5)),   # the small hours
        (datetime(2026, 8, 5, 12, 0), date(2026, 8, 5)),   # the middle of the day
    ],
)
def test_a_sale_lands_on_the_local_calendar_day(tehran_store, local_time, expected_day) -> None:
    with _session() as database:
        product = _product(database)
        _sale_at(database, product, local_time, "S-1")

        rows = daily_sales_summary(database, from_date=date(2026, 8, 3), to_date=date(2026, 8, 6))
        assert [row["date"] for row in rows] == [expected_day]
        assert rows[0]["total_sales"] == Decimal("100000.00")


def test_the_dashboard_and_the_report_agree_on_the_same_sale(tehran_store) -> None:
    with _session() as database:
        product = _product(database)
        _sale_at(database, product, datetime(2026, 8, 5, 1, 15), "S-1")

        report = daily_sales_summary(database, from_date=date(2026, 8, 4), to_date=date(2026, 8, 5))
        assert [row["date"] for row in report] == [date(2026, 8, 5)]

        # The dashboard's seven-day trend must file it on that same day.
        trend = {row["date"]: row["sales"] for row in get_summary(database)["sales_trend"]}
        if date(2026, 8, 5) in trend:  # only when the run is near that date
            assert trend[date(2026, 8, 5)] == Decimal("100000.00")
            assert trend.get(date(2026, 8, 4), Decimal("0")) == Decimal("0")


def test_a_late_night_shop_keeps_after_midnight_sales_on_the_same_trading_day(monkeypatch) -> None:
    """A shop trading until 2am sets the boundary to 3, and what it sells
    after midnight stays on the day the shift began."""
    monkeypatch.setattr(store_time.settings, "store_timezone", "Asia/Tehran", raising=False)
    monkeypatch.setattr(store_time.settings, "store_day_boundary_hour", 3, raising=False)

    with _session() as database:
        product = _product(database)
        _sale_at(database, product, datetime(2026, 8, 4, 22, 0), "S-EVENING")
        _sale_at(database, product, datetime(2026, 8, 5, 1, 30), "S-AFTER-MIDNIGHT")
        _sale_at(database, product, datetime(2026, 8, 5, 9, 0), "S-NEXT-MORNING")

        rows = daily_sales_summary(database, from_date=date(2026, 8, 3), to_date=date(2026, 8, 6))
        by_day = {row["date"]: row["total_sales"] for row in rows}

        assert by_day[date(2026, 8, 4)] == Decimal("200000.00"), (
            "the 22:00 and the 01:30 sale are one night's trading"
        )
        assert by_day[date(2026, 8, 5)] == Decimal("100000.00")


def test_the_default_boundary_is_local_midnight(monkeypatch) -> None:
    monkeypatch.setattr(store_time.settings, "store_timezone", "Asia/Tehran", raising=False)
    monkeypatch.setattr(store_time.settings, "store_day_boundary_hour", 0, raising=False)

    start, end = store_time.business_day_bounds(date(2026, 8, 5))
    assert start == datetime(2026, 8, 4, 20, 30, tzinfo=UTC), "Tehran midnight is 20:30 UTC"
    assert end - start == timedelta(days=1)


# ── The settings themselves ──────────────────────────────────────────────

def test_an_unknown_time_zone_is_refused_at_startup() -> None:
    with pytest.raises(ValueError, match="not a known IANA time zone"):
        Settings(secret_key="x" * 32, store_timezone="Mars/Olympus_Mons")


def test_a_boundary_in_the_middle_of_trading_is_refused() -> None:
    with pytest.raises(ValueError, match="between 0 and 11"):
        Settings(secret_key="x" * 32, store_day_boundary_hour=18)


def test_changing_the_boundary_is_not_served_from_the_statement_cache(monkeypatch) -> None:
    """The compiled SQL bakes in the offset and boundary, so it must not be
    cached across a change to either. One engine, two settings — the shape
    the per-test engines elsewhere in this file would hide."""
    monkeypatch.setattr(store_time.settings, "store_timezone", "Asia/Tehran", raising=False)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        product = _product(database)
        _sale_at(database, product, datetime(2026, 8, 5, 1, 30), "S-1")

        monkeypatch.setattr(store_time.settings, "store_day_boundary_hour", 0, raising=False)
        at_midnight = [row["date"] for row in daily_sales_summary(
            database, from_date=date(2026, 8, 3), to_date=date(2026, 8, 6))]

        monkeypatch.setattr(store_time.settings, "store_day_boundary_hour", 3, raising=False)
        at_three = [row["date"] for row in daily_sales_summary(
            database, from_date=date(2026, 8, 3), to_date=date(2026, 8, 6))]

        assert at_midnight == [date(2026, 8, 5)]
        assert at_three == [date(2026, 8, 4)], "stale cached SQL would repeat the first answer"


def test_a_naive_timestamp_is_read_as_utc(tehran_store) -> None:
    """Every stored row predating this change is naive and means UTC."""
    assert store_time.to_business_day(datetime(2026, 8, 4, 20, 31)) == date(2026, 8, 5)
    assert store_time.to_business_day(datetime(2026, 8, 4, 20, 29)) == date(2026, 8, 4)
