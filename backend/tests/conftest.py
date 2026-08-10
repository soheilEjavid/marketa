"""Shared test setup.

**Foreign keys.** `app/db/session.py` turns on SQLite's `foreign_keys`
pragma with a listener bound to its own engine instance. Every test file
builds its own `create_engine("sqlite://")`, so that listener never fired
and the entire suite ran with referential integrity switched *off* while
the app ran with it on — a test could write an orphan row and pass where
the real database would reject it. Listening on the `Engine` class instead
of one instance covers every engine created anywhere in the test process,
including the ones individual tests build for themselves, without any of
them having to opt in.

The `db_session` fixture below is for new tests; the pragma above applies
to old and new alike.
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.base import Base


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    # PostgreSQL enforces foreign keys unconditionally and has no such
    # pragma, so this must only ever touch SQLite connections.
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@pytest.fixture
def db_engine() -> Engine:
    """A fresh in-memory database with the full schema, foreign keys on."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Session:
    """A session on `db_engine`, closed for you at the end of the test."""
    with Session(db_engine) as session:
        yield session
