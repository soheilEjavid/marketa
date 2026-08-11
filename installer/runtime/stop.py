"""Stop a running MARKETA server.

Used by the "Stop MARKETA" shortcut and by the installer before it replaces
the program files — Windows will not overwrite a .exe or .pyd that a running
process still has open, so an update that skipped this would fail halfway
with a file-in-use error.
"""

import subprocess
import sys

import marketa_runtime

_PID_FILE_NAME = "marketa.pid"
_OUR_IMAGES = {"python.exe", "pythonw.exe"}


def _parse_tasklist_image(stdout: str) -> str | None:
    """The image name out of `tasklist /NH /FO CSV`, or None for no match.

    Parsed strictly, because tasklist reports "nothing matched" on *stdout*
    and with exit code 0: `INFO: No tasks are running which match the
    specified criteria.` Splitting that on commas yields the whole sentence
    as an "image name", which then looks like a PID belonging to another
    program — so a server that died without cleaning up produced "this PID
    belongs to INFO: No tasks are running..., not MARKETA" and a failure
    exit, instead of simply tidying the stale file away.

    A real row is CSV-quoted, so requiring the leading quote separates the
    two cases exactly.
    """
    for line in stdout.strip().splitlines():
        line = line.strip()
        if line.startswith('"'):
            return line.split(",")[0].strip('"') or None
    return None


def _image_name(pid: int) -> str | None:
    """The executable behind a PID, or None if nothing is running under it."""
    completed = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
        capture_output=True,
        text=True,
        check=False,
    )
    return _parse_tasklist_image(completed.stdout)


def main() -> int:
    data_directory = marketa_runtime.prepare()
    logger = marketa_runtime.configure_logging("marketa-stop")
    pid_file = data_directory / _PID_FILE_NAME

    if not pid_file.is_file():
        print("MARKETA does not appear to be running.")
        return 0

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        logger.warning("Unreadable PID file; removing it.")
        pid_file.unlink(missing_ok=True)
        return 0

    image = _image_name(pid)
    if image is None:
        # The server died without cleaning up (a power cut, say). The stale
        # file is the only thing left to tidy.
        logger.info("PID %s is not running; clearing the stale PID file.", pid)
        pid_file.unlink(missing_ok=True)
        print("MARKETA was not running; cleared a leftover PID file.")
        return 0
    if image.lower() not in _OUR_IMAGES:
        # Windows reuses PIDs. Killing whatever inherited this one — which
        # could be anything the shop is in the middle of — would be worse
        # than not stopping the server.
        logger.error("PID %s now belongs to %s; refusing to kill it.", pid, image)
        print(f"PID {pid} belongs to {image}, not MARKETA. Nothing was stopped.")
        pid_file.unlink(missing_ok=True)
        return 1

    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    pid_file.unlink(missing_ok=True)
    logger.info("Stopped MARKETA (PID %s).", pid)
    print("MARKETA stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
