"""Create the very first administrator on a fresh install.

A shop's database ships empty: `seed.py` and its year of demo trading are
deliberately not part of the Windows package, and this codebase has no
auth bypass, so an install with no users would be a locked door. The
installer runs this once, after `alembic upgrade head`, with the password
the shopkeeper typed into the wizard.

Usage (the installer's form — never put a password in argv, where any
other process on the machine can read it out of the command line):

    python -m app.bootstrap --username owner --full-name "..." \
        --password-file C:\\Users\\...\\Temp\\marketa-pw.txt

The password file is deleted as soon as it has been read, whether or not
the account ends up being created.
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.schemas.users import UserCreate
from app.services.auth import hash_password

# One statement, so the "is this database still empty?" test and the insert
# that depends on it cannot be separated by another connection's write. The
# check-then-act shape (`if not database.scalar(select(User)): create...`)
# would leave a window between the two in which a second caller also sees
# an empty table, and both would then create an owner account.
_INSERT_FIRST_ADMIN = text(
    "INSERT INTO users (username, password_hash, full_name, role, is_active) "
    "SELECT :username, :password_hash, :full_name, 'admin', :is_active "
    "WHERE NOT EXISTS (SELECT 1 FROM users)"
)


def create_first_admin(
    database: Session,
    *,
    username: str,
    password: str,
    full_name: str,
) -> bool:
    """Create an admin account, but only while the database has no users.

    Returns True when this call created the account and False when it found
    the table already populated and did nothing. Validation goes through
    `UserCreate`, so the wizard enforces exactly the username and password
    rules the API does.

    The guard is a single atomic statement (see `_INSERT_FIRST_ADMIN`).
    SQLite serializes writers, so there it is a hard guarantee. On
    PostgreSQL at READ COMMITTED two concurrent transactions could each see
    an empty table and each insert a *differently named* admin — the unique
    index on `username` only stops identical ones. That is not reachable
    from the installer, which runs this once in a single process before the
    service is started, but it is the reason not to lift this function into
    a request path without a table-level lock.
    """
    data = UserCreate(
        username=username,
        password=password,
        full_name=full_name,
        role="admin",
    )
    result = database.execute(
        _INSERT_FIRST_ADMIN,
        {
            "username": data.username,
            "password_hash": hash_password(data.password),
            "full_name": data.full_name,
            "is_active": True,
        },
    )
    database.commit()
    return result.rowcount == 1


def _decode_password(raw: bytes) -> str:
    """Decode a password file whoever wrote it.

    A Unicode NSIS installer's `FileWrite` emits UTF-16LE, so assuming
    UTF-8 here turned a perfectly good password into mojibake that then
    failed to log in — with nothing to suggest why. The byte-order mark
    settles it when present, and interleaved NUL bytes give away UTF-16
    when it is not.
    """
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    if b"\x00" in raw:
        return raw.decode("utf-16-le")
    return raw.decode("utf-8")


def _read_password(password_file: str | None) -> str:
    """The password, from a file the caller deletes-on-read, or stdin."""
    if password_file is None:
        return sys.stdin.readline().rstrip("\r\n")
    path = Path(password_file)
    try:
        # Strip only the line ending: a password may legitimately end in a
        # space, and `.strip()` would silently change it into another one.
        return _decode_password(path.read_bytes()).rstrip("\r\n")
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the first admin account on a fresh MARKETA install."
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument(
        "--password-file",
        help="File holding the password; read once, then deleted. "
        "Omit to read the password from stdin instead.",
    )
    args = parser.parse_args()

    password = _read_password(args.password_file)
    if not password:
        print("No password supplied.", file=sys.stderr)
        return 1

    database = SessionLocal()
    try:
        created = create_first_admin(
            database,
            username=args.username,
            password=password,
            full_name=args.full_name,
        )
    except ValidationError as error:
        # One line per problem, without pydantic's traceback framing —the
        # installer surfaces this text to a shopkeeper, not to a developer.
        for problem in error.errors():
            print(problem["msg"], file=sys.stderr)
        return 1
    finally:
        database.close()

    if created:
        print(f"Administrator {args.username!r} created.")
    else:
        print("Database already has users; left it alone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
