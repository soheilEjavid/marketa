"""Start MARKETA and open it in the shop's browser.

This is what both desktop shortcuts run. It is deliberately tolerant of
being clicked twice: the second click finds the port already answering and
just opens another browser tab instead of failing with "address already in
use", which is what a shopkeeper does when the first tab gets closed.
"""

import ctypes
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import marketa_runtime

_STARTUP_TIMEOUT_SECONDS = 60
_PID_FILE_NAME = "marketa.pid"

# Mirrors settings.api_v1_prefix + the health route. Checked before the app is
# imported, so it cannot be read from app.core.config at that point.
_HEALTH_PATH = "/api/v1/health"
_HEALTH_SERVICE = "marketa-api"


def _port_is_answering(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _marketa_is_answering(port: int) -> bool:
    """True only when the thing on this port is MARKETA itself.

    "Something is listening" is not the same claim, and conflating the two
    sends the shopkeeper's browser to whatever stranger holds the port while
    MARKETA never starts and nothing says so. Found exactly that way: a
    development server on another machine's port 8000, reachable through
    WSL's localhost forwarding, answered every probe convincingly.
    """
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{_HEALTH_PATH}", timeout=2
        ) as response:
            return json.load(response).get("service") == _HEALTH_SERVICE
    except Exception:
        return False


def _alert(message: str) -> None:
    """Tell the shopkeeper. The server runs windowless, so a log is not enough."""
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "MARKETA", 0x10)
    except AttributeError:
        # Not Windows — the console is the only place left to say it.
        print(message, file=sys.stderr)


def _open_when_ready(port: int) -> None:
    """Open the browser once the server accepts connections, not before.

    Opening immediately shows the shopkeeper a connection error for the
    second or two uvicorn needs to import the app and attach to the port.
    """
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _port_is_answering(port):
            webbrowser.open(f"http://127.0.0.1:{port}/")
            return
        time.sleep(0.3)


def main() -> int:
    data_directory = marketa_runtime.prepare()
    logger = marketa_runtime.configure_logging("marketa-launch")
    port = marketa_runtime.configured_port()

    if _port_is_answering(port):
        if _marketa_is_answering(port):
            logger.info("Already running on port %s; opening a browser tab.", port)
            webbrowser.open(f"http://127.0.0.1:{port}/")
            return 0
        logger.error("Port %s is held by something that is not MARKETA.", port)
        _alert(
            f"MARKETA cannot start: port {port} on this computer is already "
            f"in use by another program.\n\n"
            f"Change MARKETA_PORT in this file and try again:\n"
            f"{data_directory / '.env'}"
        )
        return 1

    # Imported only now: `prepare()` had to set the working directory first,
    # or app.core.config would look for .env in the wrong place.
    import uvicorn

    (data_directory / _PID_FILE_NAME).write_text(str(os.getpid()), encoding="utf-8")
    threading.Thread(target=_open_when_ready, args=(port,), daemon=True).start()

    logger.info("Starting MARKETA on port %s (data directory %s).", port, data_directory)
    try:
        uvicorn.run(
            "app.main:app",
            # Loopback only. One shop, one till, one machine: there is no
            # reason for this to be reachable from the neighbourhood's wifi,
            # and the login page is the only thing standing in front of the
            # whole ledger.
            host="127.0.0.1",
            port=port,
            log_config=None,
            access_log=False,
        )
    finally:
        (data_directory / _PID_FILE_NAME).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
