"""Stop a running MARKETA server.

Used by the "Stop MARKETA" shortcut and by the installer before it replaces
the program files — Windows will not overwrite a .exe or .pyd that a running
process still has open, so an update that skipped this would fail halfway
with a file-in-use error.
"""

import subprocess
import sys

import marketa_runtime

def main() -> int:
    marketa_runtime.prepare()
    logger = marketa_runtime.configure_logging("marketa-stop")
    pid_file = marketa_runtime.pid_file()

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

    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    pid_file.unlink(missing_ok=True)
    logger.info("Stopped MARKETA (PID %s).", pid)
    print("MARKETA stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
