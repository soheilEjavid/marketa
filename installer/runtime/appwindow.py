"""Open MARKETA in its own window, not in a browser tab.

A till should look like a till: no address bar, no back button, no tabs the
shopkeeper can lose the shop behind. Chromium's `--app=` mode gives exactly
that window, and Edge is on every standard Windows 10/11 install, so this
costs the payload nothing — no second runtime, no Node build step.

Two things about it are not optional:

**A dedicated `--user-data-dir`.** Without one, launching `msedge --app=...`
while Edge is already running hands the new window to the existing browser
process and the process we spawned exits immediately, with status 0. Measured
on a real machine: seven Edge processes running, our spawned process gone
within six seconds. Anything waiting on that process to learn when the window
closed would conclude the shopkeeper had closed it one second after startup.
With its own profile directory the process is a genuine parent and lives as
long as the window.

**The page has to declare an icon.** Chromium takes the window and taskbar
icon from the page's favicon; a custom `.lnk` icon does not change it, because
the taskbar button belongs to the running window rather than to whatever
launched it. `frontend/public/favicon.svg` is that icon.
"""

import ctypes
import logging
import os
import subprocess
import winreg
from ctypes import wintypes
from pathlib import Path

import marketa_runtime

logger = logging.getLogger("marketa-appwindow")

_APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"

# Edge first: it is present on every supported Windows without anyone
# installing anything. Chrome second, for a machine whose Edge has been
# stripped out by an enterprise image.
_BROWSERS = (
    ("Microsoft Edge", "msedge.exe", r"Microsoft\Edge\Application\msedge.exe"),
    ("Google Chrome", "chrome.exe", r"Google\Chrome\Application\chrome.exe"),
)


def _from_registry(executable: str) -> Path | None:
    """The path Windows itself records for a browser, or None.

    The documented lookup, and the reason not to hardcode a directory:
    on the machine this was developed against, Edge lives under
    `Program Files (x86)` and Chrome under `Program Files`. Guessing either
    way would be wrong half the time.
    """
    for access in (winreg.KEY_READ, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, f"{_APP_PATHS}\\{executable}", 0, access
            ) as key:
                recorded, _ = winreg.QueryValueEx(key, None)
        except OSError:
            continue
        candidate = Path(recorded.strip('"'))
        if candidate.is_file():
            return candidate
    return None


def _from_disk(relative: str) -> Path | None:
    """The usual install locations, for a browser with no registry entry."""
    roots = [
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramFiles"),
        os.environ.get("LOCALAPPDATA"),
    ]
    for root in roots:
        if not root:
            continue
        candidate = Path(root) / relative
        if candidate.is_file():
            return candidate
    return None


def find_browser() -> tuple[str, Path] | None:
    """A Chromium browser to host the window, as (name, path), or None."""
    for name, executable, relative in _BROWSERS:
        found = _from_registry(executable) or _from_disk(relative)
        if found is not None:
            logger.info("Using %s at %s.", name, found)
            return name, found
    logger.warning("Found neither Edge nor Chrome; no app window is possible.")
    return None


def open_window(url: str, browser: Path) -> subprocess.Popen:
    """Open `url` as a standalone window and return the browser process."""
    profile = marketa_runtime.data_dir() / "browser-profile"
    profile.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            str(browser),
            f"--app={url}",
            # Its own profile — see the module docstring. This is what makes
            # the process worth waiting on, and it keeps the shop's session
            # out of whatever the owner browses in their own Edge.
            f"--user-data-dir={profile}",
            # A till is 1366x768 as often as it is anything else, so a fixed
            # window size can be taller than the screen it opens on.
            "--start-maximized",
            "--no-first-run",
            "--no-default-browser-check",
            # Edge otherwise floats a "Translate page from Persian?" bubble
            # over the till every time it opens — seen doing exactly that.
            # The interface is Persian on purpose, and one stray click would
            # leave the shop running a machine-translated till.
            "--disable-features=Translate,TranslateUI,msEdgeTranslate",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _windows_of_process(pid: int) -> list[int]:
    """Visible top-level window handles belonging to `pid`."""
    handles: list[int] = []
    user32 = ctypes.windll.user32

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            handles.append(hwnd)
        return True

    user32.EnumWindows(collect, 0)
    return handles


def _window_title(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def focus_window(pid: int) -> bool:
    """Bring an already-open MARKETA window to the front.

    What a desktop application does when its icon is clicked twice: the
    second click finds the window rather than making another one.
    """
    user32 = ctypes.windll.user32
    handles = _windows_of_process(pid)
    # Chromium keeps an untitled helper window that also reports itself as
    # visible; raising that one would appear to do nothing at all. The window
    # the shopkeeper means is the one wearing the page's title.
    handles.sort(key=lambda hwnd: _window_title(hwnd) == "")
    for hwnd in handles:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE, in case it was minimised
        if user32.SetForegroundWindow(hwnd):
            return True
    return False
