"""Path, configuration and logging wiring for the packaged Windows install.

The package keeps the program and the shop's data deliberately apart. The
program lives under Program Files and an update **replaces it wholesale**;
the database, the `.env` and the logs live under ProgramData and are never
touched by an update or an uninstall. Every entry point therefore has to do
the same two things before importing anything from `app`:

* put the program directory on `sys.path`, because the embedded Python has
  no site-packages entry for it, and
* make the data directory the working directory, because
  `app.core.config` reads `.env` relative to the process's CWD — get this
  wrong and the app starts with no SECRET_KEY and dies, or worse, quietly
  creates a second empty `marketa.db` wherever the shortcut happened to
  point.

Nothing here imports `app`; that is the caller's job, after `prepare()`.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

_DEFAULT_DATA_DIR = Path(r"C:\ProgramData\MARKETA")

# Written by configure.py so the program can find the data directory the
# shopkeeper chose. Kept as a plain file rather than a registry key so that
# a support person can read and correct it with Notepad. It is written by
# Python rather than by the installer on purpose: a Unicode NSIS script's
# FileWrite emits UTF-16, which every reader here would have to know about.
_DATA_DIR_POINTER = APP_DIR / "data_dir.txt"


def record_data_dir(path: Path) -> None:
    """Point this installation at `path` for all future runs."""
    _DATA_DIR_POINTER.write_text(str(path), encoding="utf-8")

DEFAULT_PORT = 8000


def data_dir() -> Path:
    """Where this install keeps the database, `.env`, logs and backups."""
    override = os.environ.get("MARKETA_DATA_DIR")
    if override:
        return Path(override)
    if _DATA_DIR_POINTER.is_file():
        # utf-8-sig, not utf-8: a support person who opens this in Notepad
        # and saves it back gets a byte-order mark for free, and that mark
        # would otherwise end up as the first character of the path.
        recorded = _DATA_DIR_POINTER.read_text(encoding="utf-8-sig").strip()
        if recorded:
            return Path(recorded)
    return _DEFAULT_DATA_DIR


def prepare() -> Path:
    """Make the process ready to import and run `app`. Returns the data dir."""
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    target = data_dir()
    target.mkdir(parents=True, exist_ok=True)
    os.chdir(target)
    return target


def configure_logging(name: str) -> logging.Logger:
    """Log to a rotating file under the data directory.

    The server runs windowless, so anything written to stdout is written to
    nowhere. When the shop rings up and says "it stopped working", this file
    is the only account of what happened.
    """
    log_dir = data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / f"{name}.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return logging.getLogger(name)


def configured_port() -> int:
    """The port from `.env`, or the default.

    Read by hand rather than through `app.core.config`: the port is needed
    before the app is importable, and a shopkeeper who has to change it
    should not have to learn a second configuration file.
    """
    env_file = data_dir() / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "MARKETA_PORT":
                try:
                    return int(value.strip())
                except ValueError:
                    break
    return DEFAULT_PORT
