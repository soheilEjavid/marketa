"""Startup schema-drift check.

The app no longer calls Base.metadata.create_all() — schema is owned
entirely by Alembic now. create_all() used to silently paper over a
database that was missing a column or table (it only ever *adds* what's
missing, never reports it), which is exactly how the real dev database
ended up a full migration behind without anyone noticing. This module
replaces that silent patching with a loud, impossible-to-miss log instead.
"""

import logging
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

logger = logging.getLogger("marketa")

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def check_migration_drift(engine: Engine) -> None:
    """Compare the database's current Alembic revision against the repo's
    migration head. Only logs — deliberately does not raise or block
    startup, on the principle that a serious dev-time problem should be
    surfaced loudly rather than made into a refusal to run.
    """
    try:
        alembic_cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
        script = ScriptDirectory.from_config(alembic_cfg)
        head_revision = script.get_current_head()

        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_revision = context.get_current_revision()
    except Exception:
        logger.exception(
            "Could not determine migration status — this usually means the "
            "database has no alembic_version table at all (never migrated). "
            "Run `alembic upgrade head` before starting the app."
        )
        return

    if current_revision != head_revision:
        banner = (
            "\n"
            + "!" * 78 + "\n"
            + "! DATABASE SCHEMA IS BEHIND THE LATEST MIGRATION.".ljust(77) + "!\n"
            + f"! current revision: {current_revision!r}".ljust(77) + "!\n"
            + f"! expected (head):  {head_revision!r}".ljust(77) + "!\n"
            + "! The app no longer auto-creates/patches schema at startup —".ljust(77) + "!\n"
            + "! run `alembic upgrade head` before using this database.".ljust(77) + "!\n"
            + "!" * 78
        )
        logger.error(banner)
        print(banner)  # noqa: T201 - intentionally loud, must be impossible to miss
