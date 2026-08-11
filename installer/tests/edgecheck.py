"""The Windows-only edge cases: PID reuse, stale PID files, port conflicts."""

import http.server
import json
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import launch
import marketa_runtime

DATA = marketa_runtime.data_dir()
PID_FILE = DATA / "marketa.pid"
PYTHON = str(marketa_runtime.APP_DIR / "python" / "python.exe")
failures = []


def check(label, function):
    try:
        detail = function()
    except Exception as error:
        failures.append(label)
        print(f"FAIL  {label}\n      {type(error).__name__}: {error}")
    else:
        print(f"ok    {label}{f'  [{detail}]' if detail else ''}")


def run_stop():
    completed = subprocess.run(
        [PYTHON, str(marketa_runtime.APP_DIR / "stop.py")],
        capture_output=True,
        text=True,
    )
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def stale_pid_is_cleaned_up():
    """A PID nothing is running under: tidy the file, report nothing to stop."""
    PID_FILE.write_text("999999", encoding="utf-8")
    code, output = run_stop()
    assert code == 0, f"exit {code}: {output}"
    assert not PID_FILE.exists(), "the stale PID file was left behind"
    return output.splitlines()[-1] if output else "no output"


def reused_pid_is_not_killed():
    """A PID that now belongs to another program must never be killed.

    Windows recycles PIDs. If MARKETA died without cleaning up and the
    number was handed to something the shop is in the middle of using,
    killing it would be worse than failing to stop a server.
    """
    victim = subprocess.Popen(
        ["ping.exe", "-n", "60", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.5)
        PID_FILE.write_text(str(victim.pid), encoding="utf-8")
        code, output = run_stop()
        assert code == 1, f"expected exit 1, got {code}: {output}"
        assert "ping" in output.lower(), output
        assert victim.poll() is None, "stop.py killed an unrelated process"
        return f"refused to kill PID {victim.pid} (ping.exe), exit 1"
    finally:
        victim.kill()
        PID_FILE.unlink(missing_ok=True)


def foreign_service_on_the_port_is_detected():
    """Something listening is not the same as MARKETA listening."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"service": "not-marketa"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 8099), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        time.sleep(0.3)
        assert launch._port_is_answering(8099) is True, "the probe missed a live port"
        assert launch._marketa_is_answering(8099) is False, (
            "a foreign service was mistaken for MARKETA"
        )
        return "port answers, but is correctly not taken for MARKETA"
    finally:
        server.shutdown()


def marketa_is_recognised_when_it_is_marketa():
    """The positive case, so the check above is not just always-False."""
    process = subprocess.Popen(
        [str(marketa_runtime.APP_DIR / "python" / "pythonw.exe"),
         str(marketa_runtime.APP_DIR / "launch.py")],
    )
    try:
        deadline = time.monotonic() + 60
        port = marketa_runtime.configured_port()
        while time.monotonic() < deadline:
            if launch._marketa_is_answering(port):
                return f"recognised MARKETA on port {port}"
            time.sleep(0.5)
        raise AssertionError(f"MARKETA never came up on port {port}")
    finally:
        subprocess.run([PYTHON, str(marketa_runtime.APP_DIR / "stop.py")],
                       capture_output=True)
        process.wait(timeout=30)


check("a stale PID file is cleaned up, not acted on", stale_pid_is_cleaned_up)
check("a reused PID belonging to another program is refused", reused_pid_is_not_killed)
check("a foreign service on the port is not mistaken for MARKETA",
      foreign_service_on_the_port_is_detected)
check("MARKETA itself is recognised on its port", marketa_is_recognised_when_it_is_marketa)

print()
if failures:
    print(f"{len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print("all edge-case checks passed")
