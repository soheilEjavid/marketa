"""Bring the shop's database up to the schema this build expects.

Run by the installer on every install and every update, before the service
is started. Two things make it more than a call to `alembic upgrade head`:

**It backs up first.** `app/db/migration_check.py` only *logs* schema drift
and never blocks startup, on purpose — so if a migration fails halfway and
we carried on regardless, the app would come up against a half-migrated
database and misbehave quietly rather than refuse to start. The backup, and
restoring it on failure, is what turns that into a safe stopping point.

**It fails loudly.** A non-zero exit tells the installer to stop and say so,
rather than leaving a shop to discover the problem mid-sale.
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import marketa_runtime

_BACKUPS_TO_KEEP = 10


def _sqlite_path(database_url: str) -> Path | None:
    """The file behind a sqlite URL, or None for any other backend."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return None
    return Path(database_url[len(prefix) :]).resolve()


def _back_up(database: Path, backups: Path) -> Path:
    """A consistent copy of the database, using SQLite's own backup API.

    A plain file copy of a database that is mid-write — or that has a
    journal alongside it — can produce a corrupt file that only reveals
    itself when it is needed. The backup API takes a proper snapshot.
    """
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backups / f"marketa-{stamp}-pre-update.db"
    source_connection = sqlite3.connect(database)
    try:
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
    finally:
        source_connection.close()
    return destination


def _prune(backups: Path) -> None:
    """Keep the most recent pre-update backups; a shop's disk is not free."""
    existing = sorted(backups.glob("marketa-*-pre-update.db"))
    for stale in existing[:-_BACKUPS_TO_KEEP]:
        stale.unlink(missing_ok=True)


def _upgrade() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(marketa_runtime.APP_DIR / "alembic.ini"))
    # Both paths are relative in the repo's alembic.ini and the working
    # directory here is the *data* directory, not the program directory.
    config.set_main_option(
        "script_location", str(marketa_runtime.APP_DIR / "alembic")
    )
    config.set_main_option("prepend_sys_path", str(marketa_runtime.APP_DIR))
    # env.py overrides sqlalchemy.url from app.core.config, so the .env in
    # the data directory decides which database this touches.
    command.upgrade(config, "head")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate the MARKETA database.")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the pre-migration backup (for a first install, where "
        "there is nothing to lose yet).",
    )
    args = parser.parse_args()

    marketa_runtime.prepare()
    logger = marketa_runtime.configure_logging("marketa-migrate")

    from app.core.config import settings

    database = _sqlite_path(settings.database_url)
    backup: Path | None = None

    if args.no_backup or database is None or not database.is_file():
        if database is None:
            # PostgreSQL: a file copy is meaningless and pg_dump is not
            # bundled. Say so rather than implying a safety net exists.
            logger.warning(
                "Database is not SQLite; no backup was taken. Back it up "
                "yourself before running this."
            )
    else:
        backup = _back_up(database, database.parent / "backups")
        logger.info("Backed the database up to %s.", backup)

    try:
        _upgrade()
    except Exception:
        logger.exception("Migration failed.")
        if backup is not None and database is not None:
            # Put the shop back exactly where it was. The half-migrated
            # database is the one thing we must not leave behind.
            shutil.copy2(backup, database)
            logger.error("Restored the database from %s.", backup)
            print(
                f"Migration failed; the database was restored from {backup}.",
                file=sys.stderr,
            )
        else:
            print("Migration failed.", file=sys.stderr)
        return 1

    if backup is not None:
        _prune(backup.parent)
    logger.info("Database is at the current schema.")
    print("Database is at the current schema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
