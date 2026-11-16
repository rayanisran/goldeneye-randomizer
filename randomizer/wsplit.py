"""WSplit alongside the game: open it, and run its timer while the game runs.

WSplit has no command line, but its window handles the WM_HOTKEY message even
with its global hotkeys turned off. It can't be asked what state the timer is
in, and pause/resume is a toggle, so the timer is only touched when this code
knows the state: WSplit was opened here (timer at zero), or paused from here.
A WSplit that was already open is left alone. Windows only.
"""

import ctypes
import json
import os
import subprocess
import threading
import time
from pathlib import Path

DEFAULT_PATH = Path.home() / "Downloads" / "WSplit_1.5.3" / "WSplit.exe"
SETTINGS_FILE = "timer.json"

WM_HOTKEY = 0x0312
HOTKEY_PAUSE_RESUME = 0x9D83     # starts an idle timer too, and never records a split
WSPLIT_WAIT = 15
GAME_WAIT = 180                  # the first launch builds the game files before its window opens


def supported():
    return os.name == "nt"


def load_settings(rando):
    s = {"path": str(DEFAULT_PATH), "open": True, "start": True}
    try:
        s.update(json.loads((Path(rando) / SETTINGS_FILE).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return s


def save_settings(rando, settings):
    Path(rando).mkdir(parents=True, exist_ok=True)
    (Path(rando) / SETTINGS_FILE).write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _user32():
    from ctypes import wintypes as w
    u = ctypes.WinDLL("user32")
    u.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM), w.LPARAM]
    u.IsWindowVisible.argtypes = [w.HWND]
    u.IsWindow.argtypes = [w.HWND]
    u.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    u.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    u.PostMessageW.restype = w.BOOL
    return u


def _windows():
    """(hwnd, pid, class name, title) of each visible top-level window."""
    from ctypes import wintypes as w
    u = _user32()
    found = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def visit(hwnd, _):
        if u.IsWindowVisible(hwnd):
            pid = w.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            cls, title = ctypes.create_unicode_buffer(128), ctypes.create_unicode_buffer(128)
            u.GetClassNameW(hwnd, cls, 128)
            u.GetWindowTextW(hwnd, title, 128)
            found.append((hwnd, pid.value, cls.value, title.value))
        return True

    u.EnumWindows(visit, 0)
    return found


def find_wsplit():
    for hwnd, _, cls, title in _windows():
        if title == "WSplit" and cls.startswith("WindowsForms10.Window"):
            return hwnd
    return None


def _has_game_window(pid):
    return any(p == pid and cls.startswith("SDL") for _, p, cls, _ in _windows())


def _toggle(hwnd):
    return bool(_user32().PostMessageW(hwnd, WM_HOTKEY, HOTKEY_PAUSE_RESUME, 0))


class Timer:
    """Call open() just before starting the game and run_with() just after."""

    def __init__(self):
        self.paused_hwnd = None      # the WSplit window this object last paused
        self.drive = False

    def open(self, rando):
        """Open WSplit if it isn't open. Returns an error message, or None."""
        self.drive = False
        s = load_settings(rando)
        if not (supported() and s["open"]):
            return None
        path = Path(s["path"])
        if not path.is_file():
            return None
        hwnd = find_wsplit()
        if hwnd:
            self.drive = s["start"] and hwnd == self.paused_hwnd
            return None
        try:
            subprocess.Popen([str(path)], cwd=str(path.parent))
        except OSError as e:
            return f"Could not open WSplit: {e}"
        self.drive = bool(s["start"])
        return None

    def run_with(self, game):
        if self.drive:
            threading.Thread(target=self._follow, args=(game,), daemon=True).start()

    def _wait_for(self, game, found, seconds):
        end = time.monotonic() + seconds
        while game.poll() is None and time.monotonic() < end:
            result = found()
            if result:
                return result
            time.sleep(0.1)
        return None

    def _follow(self, game):
        hwnd = self._wait_for(game, find_wsplit, WSPLIT_WAIT)
        if not hwnd or not self._wait_for(game, lambda: _has_game_window(game.pid), GAME_WAIT):
            return
        if _toggle(hwnd):
            self.paused_hwnd = None
            game.wait()
            if _toggle(hwnd):
                self.paused_hwnd = hwnd
