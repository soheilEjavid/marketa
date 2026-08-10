"""The migrations and the models must describe the same schema.

Every other test builds its schema with `Base.metadata.create_all()` — fast,
and fine for exercising business logic, but it means the 24 Alembic
migrations are never executed by the suite at all. Models and migrations
could drift apart indefinitely and everything would still be green;
`db/migration_check.py` only logs at startup and deliberately does not block.

This is the one test that actually runs `alembic upgrade head`, against a
throwaway database, and asserts the result matches the models. It runs once
rather than per-test, so it costs the suite a second, not a minute.
"""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.command import upgrade
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from app.core.config import settings
from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Diff kinds that mean a migration is genuinely missing or wrong: a table
# or column that exists on one side and not the other. This is the failure
# this test is here to catch — a model field added without a migration.
#
# Three other diff kinds show up against this schema and are deliberately
# not asserted on, because they are either unrepresentable on SQLite or
# pre-existing and benign:
#
# * modify_type on every Enum column — SQLite has no enum type and stores
#   them as VARCHAR, so reflection can never match the model. Noise.
# * modify_nullable on every created_at/updated_at/paid_at — these are real:
#   the migrations declare them with server_default=now() but without
#   nullable=False, while TimestampMixin declares them non-optional. The
#   server default means they are never actually null, and rewriting 24
#   already-applied migrations to chase the flag would risk far more than
#   it fixes. Left alone knowingly.
# * unique-constraint/index shape on `sales.invoice_number` and
#   `users.username` — reflection reports the same uniqueness twice, once
#   as a constraint and once as an index, and disagrees with itself.
STRUCTURAL = frozenset({"add_table", "remove_table", "add_column", "remove_column"})


def _describe(diff) -> str:
    """compare_metadata() yields either a tuple or a list of tuples."""
    if isinstance(diff, list):
        return " / ".join(_describe(entry) for entry in diff)
    kind = diff[0]
    if kind in {"add_table", "remove_table"}:
        return f"{kind}: {diff[1].name}"
    if kind in {"add_column", "remove_column"}:
        return f"{kind}: {diff[2]}.{diff[3].name}"
    return f"{kind}: {diff[2]}.{diff[3]}"


def _structural(diff) -> bool:
    if isinstance(diff, list):
        return any(_structural(entry) for entry in diff)
    return diff[0] in STRUCTURAL


def test_migrations_produce_the_models_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "migration_check.db"
    url = f"sqlite:///{database_path}"

    # alembic/env.py reads settings.database_url at run time, so pointing
    # the setting at a throwaway file is enough to redirect the upgrade
    # without touching the real development database.
    monkeypatch.setattr(settings, "database_url", url)

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    upgrade(alembic_cfg, "head")

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    drift = [_describe(diff) for diff in differences if _structural(diff)]
    assert not drift, (
        "The Alembic migrations and app/models/entities.py disagree. "
        "Either a model changed without a migration, or a migration is wrong:\n  "
        + "\n  ".join(drift)
    )
