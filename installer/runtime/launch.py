"""Start MARKETA and open it in its own window.

What both shortcuts run. Three behaviours matter to a shopkeeper, and each
one was a decision:

**One window, not a tab.** The interface opens as a standalone Chromium
window with no address bar and no tabs (see `appwindow.py`). A till that can
be navigated away from, or lost behind a browser tab, is a till that gets
support calls.

**Closing the window stops the server.** The whole package is built so the
shop starts *one* thing; it should therefore stop one thing. A server left
running behind a closed window is invisible — nothing on screen, nothing in
the tray — and the shopkeeper would have to learn a second shortcut to be
rid of it. The shutdown is uvicorn's graceful one, so a sale that is
mid-request when the window closes still finishes rather than being cut in
half. This only applies when there is a window process to watch: if no
Chromium browser exists and we fall back to the default browser, the server
stays up, because a browser tab closing is not something we can observe and
guessing would kill the server at the wrong moment.

**Clicking the shortcut twice gives one window.** The second click finds the
existing window and raises it.
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

import appwindow
import marketa_runtime

_STARTUP_TIMEOUT_SECONDS = 60

# A browser that dies this fast did not open a window — it failed. Treated as
# "no window to watch" rather than as the shopkeeper closing it, so that a
# broken browser invocation cannot shut the server down a second after it
# started.
_WINDOW_FAILED_WITHIN_SECONDS = 5

# Mirrors settings.api_v1_prefix + the health route. Checked before the app is
# imported, so it cannot be read from app.core.config at that point.
_HEALTH_PATH = "/api/v1/health"
_HEALTH_SERVICE = "marketa-api"


def _port_is_answering(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _marketa_is_answering(port: int) -> bool:
    """True only when the thing on this port is a MARKETA server."""
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


def _wait_for_port(port: int) -> bool:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _port_is_answering(port):
            return True
        time.sleep(0.3)
    return False


def _open_the_window(port: int, logger) -> "object | None":
    """Open the app window; returns the browser process, or None.

    None means "there is no process whose lifetime represents the window",
    which is the signal not to tie the server's life to it.
    """
    url = f"http://127.0.0.1:{port}/"
    browser = appwindow.find_browser()
    if browser is None:
        logger.warning(
            "No Chromium browser found; falling back to the default browser, "
            "and leaving the server running after it is closed."
        )
        webbrowser.open(url)
        return None

    _, executable = browser
    started = time.monotonic()
    process = appwindow.open_window(url, executable)
    marketa_runtime.window_pid_file().write_text(str(process.pid), encoding="utf-8")

    # Give a hand-off or a bad invocation a moment to reveal itself.
    time.sleep(1.0)
    if process.poll() is not None and time.monotonic() - started < _WINDOW_FAILED_WITHIN_SECONDS:
        logger.error(
            "The browser exited immediately (status %s); falling back to the "
            "default browser and leaving the server running.",
            process.returncode,
        )
        marketa_runtime.window_pid_file().unlink(missing_ok=True)
        webbrowser.open(url)
        return None
    return process


def _run_window(port: int, server, logger) -> None:
    """Open the window, then shut the server down when it closes."""
    if not _wait_for_port(port):
        logger.error("The server did not start listening; shutting down.")
        server.should_exit = True
        return

    process = _open_the_window(port, logger)
    if process is None:
        return

    process.wait()
    logger.info("The MARKETA window was closed; shutting the server down.")
    marketa_runtime.window_pid_file().unlink(missing_ok=True)
    # Graceful: uvicorn finishes what it is serving before it stops.
    server.should_exit = True


def _reopen_for_running_server(port: int, logger) -> int:
    """Raise the existing window, or give the running server a new one."""
    window_pid = marketa_runtime.running_window_pid()
    if window_pid is not None and appwindow.focus_window(window_pid):
        logger.info("Raised the existing window (PID %s).", window_pid)
        return 0
    logger.info("Server already running; opening a window for it.")
    _open_the_window(port, logger)
    return 0


def main() -> int:
    data_directory = marketa_runtime.prepare()
    logger = marketa_runtime.configure_logging("marketa-launch")
    port = marketa_runtime.configured_port()

    # Our own server, from our own PID file — not "something on the port that
    # says it is MARKETA". See marketa_runtime.running_server_pid().
    own_pid = marketa_runtime.running_server_pid()
    if own_pid is not None:
        logger.info("Already running as PID %s.", own_pid)
        return _reopen_for_running_server(port, logger)

    if _port_is_answering(port):
        other = "another MARKETA" if _marketa_is_answering(port) else "another program"
        logger.error(
            "Port %s is held by %s, and it is not this installation's server.",
            port,
            other,
        )
        _alert(
            f"MARKETA cannot start: port {port} on this computer is already "
            f"in use by {other}.\n\n"
            f"Close that program, or change MARKETA_PORT in this file and try "
            f"again:\n{data_directory / '.env'}"
        )
        return 1

    # Imported only now: `prepare()` had to set the working directory first,
    # or app.core.config would look for .env in the wrong place.
    import uvicorn

    # uvicorn.Server rather than uvicorn.run(): the window watcher needs
    # something it can ask to stop, and run() offers no handle on the server.
    server = uvicorn.Server(
        uvicorn.Config(
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
    )

    marketa_runtime.pid_file().write_text(str(os.getpid()), encoding="utf-8")
    threading.Thread(target=_run_window, args=(port, server, logger), daemon=True).start()

    logger.info("Starting MARKETA on port %s (data directory %s).", port, data_directory)
    try:
        server.run()
    finally:
        marketa_runtime.pid_file().unlink(missing_ok=True)
        marketa_runtime.window_pid_file().unlink(missing_ok=True)
        logger.info("MARKETA stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
