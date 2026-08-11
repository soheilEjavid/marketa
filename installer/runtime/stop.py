"""Stop a running MARKETA server.

Used by the "Stop MARKETA" shortcut and by the installer before it replaces
the program files — Windows will not overwrite a .exe or .pyd that a running
process still has open, so an update that skipped this would fail halfway
with a file-in-use error.
"""

import subprocess
import sys

import marketa_runtime


def _close_the_window(logger) -> None:
    """Close the app window first, so it never shows a dead server.

    Ordered before the server on purpose: kill the server first and the
    window is left displaying a connection error, which reads as a crash
    rather than as the shop being closed for the night.
    """
    window_pid = marketa_runtime.running_window_pid()
    if window_pid is None:
        marketa_runtime.window_pid_file().unlink(missing_ok=True)
        return
    subprocess.run(["taskkill", "/PID", str(window_pid), "/T", "/F"], check=False)
    marketa_runtime.window_pid_file().unlink(missing_ok=True)
    logger.info("Closed the MARKETA window (PID %s).", window_pid)


def main() -> int:
    marketa_runtime.prepare()
    logger = marketa_runtime.configure_logging("marketa-stop")
    pid_file = marketa_runtime.pid_file()

    _close_the_window(logger)

    if not pid_file.is_file():
        print("MARKETA does not appear to be running.")
        return 0

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        logger.warning("Unreadable PID file; removing it.")
        pid_file.unlink(missing_ok=True)
        return 0

    image = marketa_runtime.process_image_name(pid)
    if image is None:
        # The server died without cleaning up (a power cut, say). The stale
        # file is the only thing left to tidy.
        logger.info("PID %s is not running; clearing the stale PID file.", pid)
        pid_file.unlink(missing_ok=True)
        print("MARKETA was not running; cleared a leftover PID file.")
        return 0
    if image.lower() not in marketa_runtime.SERVER_IMAGES:
        # Windows reuses PIDs. Killing whatever inherited this one — which
        # could be anything the shop is in the middle of — would be worse
        # than not stopping the server.
        logger.error("PID %s now belongs to %s; refusing to kill it.", pid, image)
        print(f"PID {pid} belongs to {image}, not MARKETA. Nothing was stopped.")
        pid_file.unlink(missing_ok=True)
        return 1

    killed = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    # taskkill's exit code is not decoration. It fails with "Access is denied"
    # when the server was started with higher privileges than this process —
    # which used to happen because the installer's finish page ran it
    # elevated. Reporting success anyway told the shopkeeper the shop was
    # closed while it was still serving, and deleting the PID file below
    # would have left that server with nothing recording it at all.
    if killed.returncode != 0:
        detail = (killed.stderr or killed.stdout).strip().splitlines()
        logger.error(
            "Could not stop PID %s: %s", pid, detail[-1] if detail else "unknown error"
        )
        print(
            f"MARKETA (PID {pid}) could not be stopped:\n"
            f"{detail[-1] if detail else 'unknown error'}\n\n"
            "If it was started with administrator rights, stop it from an "
            "administrator command prompt, or restart the computer."
        )
        return 1

    pid_file.unlink(missing_ok=True)
    logger.info("Stopped MARKETA (PID %s).", pid)
    print("MARKETA stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
