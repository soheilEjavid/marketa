"""The shop's own clock, and the trading day measured on it.

Timestamps are stored in UTC — that is right, and none of this changes it.
What was wrong is that every daily figure was cut on the *UTC* calendar day
while the shopkeeper reads it as their own. For a Tehran shop that is a
3h30m disagreement: a sale rung up at 01:00 on Mordad 14 lands at 21:30 UTC
on Mordad 13 and was filed under the day before, on the receipt and in the
report alike.

Two separate ideas live here, and both are needed:

* **The store's time zone** turns a stored UTC instant into the wall clock
  the shopkeeper was looking at.
* **The day boundary** decides which trading day that wall clock belongs
  to. At the default of local midnight the trading day and the calendar day
  are the same thing. A shop open until 2am sets the boundary to 3, and
  what it sells after midnight stays on the day the shift began.

`business_day()` is the SQL side, used wherever a query used to say
`func.date(SomeModel.created_at)`. `business_day_now()` and
`to_business_day()` are the Python side, for "today" and for turning a
single timestamp into its trading day.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Date, func
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement, FunctionElement

from app.core.config import settings


def store_zone() -> ZoneInfo:
    return ZoneInfo(settings.store_timezone)


def boundary_hour() -> int:
    return settings.store_day_boundary_hour


def to_business_day(moment: datetime) -> date:
    """Which trading day a single instant belongs to.

    A naive datetime is taken as UTC, which is what every naive timestamp in
    this database is — SQLite writes `func.now()` as a bare UTC string.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo("UTC"))
    local = moment.astimezone(store_zone())
    return (local - timedelta(hours=boundary_hour())).date()


def business_day_now() -> date:
    """The trading day currently in progress — the replacement for the
    `datetime.now(UTC).date()` that used to stand in for 'today'."""
    return to_business_day(datetime.now(ZoneInfo("UTC")))


def business_day_bounds(day: date) -> tuple[datetime, datetime]:
    """The UTC half-open interval [start, end) covering one trading day.

    Used where a query needs a range over the raw timestamp column rather
    than a grouping key — comparing instants directly lets an index do the
    work, which `business_day()` cannot.
    """
    zone = store_zone()
    start_local = datetime.combine(day, datetime.min.time(), tzinfo=zone) + timedelta(
        hours=boundary_hour()
    )
    return (
        start_local.astimezone(ZoneInfo("UTC")),
        (start_local + timedelta(days=1)).astimezone(ZoneInfo("UTC")),
    )


class business_day(FunctionElement):  # noqa: N801 - reads as SQL, not a class
    """SQL for the trading day of a stored UTC timestamp column.

    Drop-in replacement for `func.date(column)`, which silently meant "the
    UTC calendar day". Compiles per dialect because converting a time zone
    is one of the few things SQL engines do not agree on.
    """

    type = Date()
    name = "business_day"

    # Not cacheable: the compiled SQL bakes in the store's UTC offset and
    # day boundary, which are configuration rather than part of the
    # statement. With caching on, a shared engine happily reuses SQL built
    # under the previous boundary and buckets sales into the wrong trading
    # day — silently, and only once the setting has been changed. The cost
    # is recompiling these few report queries; the alternative is a report
    # that disagrees with the setting it is supposed to obey.
    inherit_cache = False

    def __init__(self, column: ColumnElement) -> None:
        super().__init__(column)


@compiles(business_day, "postgresql")
def _business_day_postgresql(element, compiler, **kw) -> str:
    """`AT TIME ZONE` resolves each row against the zone's own history, so a
    daylight-saving change years back is still converted correctly."""
    column = list(element.clauses)[0]
    zone = settings.store_timezone.replace("'", "''")
    shifted = f"(({compiler.process(column, **kw)}) AT TIME ZONE 'UTC' AT TIME ZONE '{zone}')"
    if boundary_hour():
        shifted = f"({shifted} - interval '{boundary_hour()} hours')"
    return f"CAST({shifted} AS DATE)"


@compiles(business_day, "sqlite")
def _business_day_sqlite(element, compiler, **kw) -> str:
    """SQLite carries no time-zone database, so the offset is resolved in
    Python and passed as a fixed number of minutes. That is exact for Iran,
    which has had no daylight saving since 2022; for a zone that still
    observes it, rows on the far side of a transition would be off by an
    hour — one more reason PostgreSQL is the production target.
    """
    column = list(element.clauses)[0]
    offset = store_zone().utcoffset(datetime.now()) or timedelta(0)
    minutes = int(offset.total_seconds() // 60) - boundary_hour() * 60
    sign = "+" if minutes >= 0 else "-"
    return f"date({compiler.process(column, **kw)}, '{sign}{abs(minutes)} minutes')"


def utc_date(column: ColumnElement) -> ColumnElement:
    """The old behaviour, for the handful of columns that genuinely carry a
    calendar date rather than an instant (Expense.date, a cheque's due date)
    — those were typed by a human as a day and need no conversion."""
    return func.date(column)
