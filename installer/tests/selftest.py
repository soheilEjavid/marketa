"""Does the packaged runtime actually work on this Windows machine?

Run with the payload's own interpreter, from the payload root:

    python\\python.exe tests\\selftest.py

Checks the things a Linux dry run cannot: that the embeddable interpreter
finds the vendored wheels at all, that the compiled extensions load, and
that Asia/Tehran resolves — which needs the bundled tzdata, because Windows
ships no IANA time-zone database.
"""

import sys
import traceback

failures = []


def check(label, function):
    try:
        detail = function()
    except Exception:
        failures.append(label)
        print(f"FAIL  {label}")
        print("      " + traceback.format_exc().strip().replace("\n", "\n      "))
    else:
        print(f"ok    {label}{f'  [{detail}]' if detail else ''}")


print(f"interpreter: {sys.version.split()[0]}  ({sys.executable})")
print(f"sys.path: {sys.path}")
print()

check("import fastapi", lambda: __import__("fastapi").__version__)
check("import uvicorn", lambda: __import__("uvicorn").__version__)
check("import sqlalchemy", lambda: __import__("sqlalchemy").__version__)
check("import alembic", lambda: __import__("alembic").__version__)
check("import pydantic (compiled _pydantic_core)", lambda: __import__("pydantic").VERSION)
check("import bcrypt (compiled _bcrypt.pyd)", lambda: __import__("bcrypt").__version__)
check("import greenlet (compiled)", lambda: __import__("greenlet").__version__)
check("import httptools (compiled)", lambda: "loaded")
check("import websockets (compiled speedups)", lambda: "loaded")
check("import jwt", lambda: __import__("jwt").__version__)
check("import sqlite3 (stdlib, needs sqlite3.dll)", lambda: __import__("sqlite3").sqlite_version)
# The payload root has to be importable too: a ._pth file replaces the normal
# sys.path computation, including the rule that would add the script's own
# directory, so without a `..` entry in it neither of these can be found.
check("import marketa_runtime (the payload root is on sys.path)", lambda: "found")
check("import app.main (the application itself)", lambda: "found")


def tehran():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M %z")


check("zoneinfo can resolve Asia/Tehran (needs the tzdata wheel)", tehran)


def bcrypt_roundtrip():
    import bcrypt

    hashed = bcrypt.hashpw("رمزOwner@123".encode(), bcrypt.gensalt())
    assert bcrypt.checkpw("رمزOwner@123".encode(), hashed)
    return "hash + verify"


check("bcrypt hashes and verifies a Persian password", bcrypt_roundtrip)

print()
if failures:
    print(f"{len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print("all runtime checks passed")
