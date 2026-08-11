"""The desktop-window behaviour, on Windows, end to end.

Run from the payload root with the payload's own interpreter:

    python\\python.exe tests\\windowcheck.py

Starts the server the way a shortcut does, then checks the three things the
window has to get right: it is an app window rather than a browser tab,
clicking the shortcut again gives one window and not two, and closing the
window takes the server down with it.
"""

import socket
import subprocess
import sys
import time

import appwindow
import marketa_runtime

# A Windows console is cp1252 by default, and every interesting thing this
# prints — window titles, the shop's name — is Persian. Without this the
# check that just passed dies while reporting that it passed.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

failures = []
PYTHONW = str(marketa_runtime.APP_DIR / "python" / "pythonw.exe")
PYTHON = str(marketa_runtime.APP_DIR / "python" / "python.exe")
LAUNCH = str(marketa_runtime.APP_DIR / "launch.py")
PORT = marketa_runtime.configured_port()


def check(label, function):
    try:
        detail = function()
    except Exception as error:
        failures.append(label)
        print(f"FAIL  {label}\n      {type(error).__name__}: {error}")
    else:
        print(f"ok    {label}{f'  [{detail}]' if detail else ''}")


def port_answering(port=None):
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port or PORT)) == 0


def wait_until(predicate, timeout, interval=0.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def command_line_of(pid):
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip()


def window_titles(pid):
    import ctypes

    titles = []
    user32 = ctypes.windll.user32
    for hwnd in appwindow._windows_of_process(pid):
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        titles.append(buffer.value)
    return titles


print(f"port from .env: {PORT}")
found = appwindow.find_browser()
print(f"browser discovery: {found}")
if found is None:
    print("FAIL  no Chromium browser found; the rest cannot be checked")
    sys.exit(1)
print()

server = subprocess.Popen([PYTHONW, LAUNCH])


def server_comes_up():
    assert wait_until(port_answering, 90), f"nothing listening on {PORT}"
    return f"listening on 127.0.0.1:{PORT}"


def window_opens():
    assert wait_until(lambda: marketa_runtime.running_window_pid() is not None, 60), (
        "no window process was recorded"
    )
    pid = marketa_runtime.running_window_pid()
    time.sleep(3)  # let the window map and the page load
    return f"browser PID {pid}"


def it_is_an_app_window_not_a_tab():
    pid = marketa_runtime.running_window_pid()
    command = command_line_of(pid)
    assert "--app=" in command, f"not an app-mode window: {command}"
    # Its own profile is what keeps this process alive to be watched at all.
    assert "--user-data-dir=" in command, f"no dedicated profile: {command}"
    titles = window_titles(pid)
    return f"--app + own profile; window title {titles!r}"


def the_window_shows_marketa():
    titles = [title for title in window_titles(marketa_runtime.running_window_pid()) if title]
    assert titles, "the window has no title yet"
    # The page's own <title>, with no browser chrome appended to it.
    ours = [title for title in titles if "مارکتا" in title]
    assert ours, titles
    # Nothing else should be floating over the till — a translate offer
    # counts as something else.
    assert len(titles) == len(ours), f"an extra window is on top: {titles}"
    return ours[0]


def second_launch_gives_one_window():
    pid_before = marketa_runtime.running_window_pid()
    windows_before = len(appwindow._windows_of_process(pid_before))
    again = subprocess.run([PYTHON, LAUNCH], capture_output=True, text=True, timeout=120)
    assert again.returncode == 0, f"exit {again.returncode}: {again.stderr}"
    time.sleep(3)
    pid_after = marketa_runtime.running_window_pid()
    windows_after = len(appwindow._windows_of_process(pid_after))
    assert pid_after == pid_before, f"a second browser process appeared: {pid_after}"
    assert windows_after == windows_before, (
        f"window count went from {windows_before} to {windows_after}"
    )
    return f"same PID {pid_after}, still {windows_after} window"


def closing_the_window_stops_the_server():
    pid = marketa_runtime.running_window_pid()
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                   capture_output=True, check=False)
    assert wait_until(lambda: not port_answering(), 45), "the server kept listening"
    assert wait_until(lambda: not marketa_runtime.pid_file().exists(), 20), (
        "the server PID file was left behind"
    )
    assert not marketa_runtime.window_pid_file().exists(), (
        "the window PID file was left behind"
    )
    return "server stopped, both PID files cleaned up"


try:
    check("the server comes up", server_comes_up)
    check("an app window opens", window_opens)
    check("it is an app window, not a browser tab", it_is_an_app_window_not_a_tab)
    check("the window is showing MARKETA", the_window_shows_marketa)
    check("launching again gives one window, not two", second_launch_gives_one_window)
    check("closing the window stops the server", closing_the_window_stops_the_server)
finally:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=20)
        except subprocess.TimeoutExpired:
            server.kill()

print()
if failures:
    print(f"{len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print("all window checks passed")
