from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """A timestamp that always arrives back tagged as UTC.

    Every instant in this database is UTC — `server_default=func.now()` is
    UTC on both SQLite and PostgreSQL. SQLite has nowhere to record that,
    so SQLAlchemy handed back a *naive* datetime, which Pydantic then
    serialized as "2026-08-04T22:58:00": no Z, no offset. The frontend's
    `new Date(...)` reads a string in that form as **local** time, so every
    timestamp in the interface was shown 3h30m early for a Tehran shop, and
    a sale rung up just after midnight appeared on the previous day.

    Nothing about storage changes here; the column is the same UTC
    timestamp it always was. This only stops the value losing the one fact
    about it that the reader needs.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            # A bare string carries no zone, so there is no honest way to
            # place it on the clock — and comparing one against this column
            # is how the whole class of bug this type exists to prevent got
            # in. Say so plainly rather than failing on a missing attribute.
            raise TypeError(
                f"{type(value).__name__} cannot be compared against a UTC timestamp "
                f"column: pass a datetime (naive is taken as UTC), not {value!r}."
            )
        # A naive value from application code means UTC here, by the same
        # convention the stored rows follow.
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now()
    )
