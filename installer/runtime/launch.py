"""Start MARKETA and open it in the shop's browser.

This is what both desktop shortcuts run. It is deliberately tolerant of
being clicked twice: the second click finds the port already answering and
just opens another browser tab instead of failing with "address already in
use", which is what a shopkeeper does when the first tab gets closed.
"""

import os
import socket
import sys
import threading
import time
import webbrowser

import marketa_runtime

_STARTUP_TIMEOUT_SECONDS = 60
_PID_FILE_NAME = "marketa.pid"


def _port_is_answering(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


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
        logger.info("Already running on port %s; opening a browser tab.", port)
        webbrowser.open(f"http://127.0.0.1:{port}/")
        return 0

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
