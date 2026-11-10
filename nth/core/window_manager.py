"""Roblox window detection, focusing and geometry.

Windows: uses the Win32 API through ctypes (no pywin32 dependency).
Other platforms: a documented *simulation* backend so the whole pipeline
(window -> capture -> analysis) stays testable in CI / non-Windows dev boxes.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

IS_WINDOWS = sys.platform == "win32"


@dataclass
class GameWindow:
    handle: int          # hwnd on Windows, 0 for simulated
    title: str
    x: int
    y: int
    w: int
    h: int
    simulated: bool = False

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h


if IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    _SW_RESTORE = 9
    _GA_ROOT = 2

    def _enum_windows() -> List[Tuple[int, str]]:
        results: List[Tuple[int, str]] = []
        proto = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

        def cb(hwnd, lparam):
            if _user32.IsWindowVisible(hwnd):
                length = _user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    _user32.GetWindowTextW(hwnd, buf, length + 1)
                    results.append((hwnd, buf.value))
            return True

        _user32.EnumWindows(proto(cb), 0)
        return results

    def _client_rect_screen(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        rect = wt.RECT()
        if not _user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        pt = wt.POINT(0, 0)
        _user32.ClientToScreen(hwnd, ctypes.byref(pt))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None
        return pt.x, pt.y, w, h


class WindowManager:
    """Finds and focuses the Roblox Player window."""

    def __init__(self, settings):
        self.settings = settings
        self._lock = threading.Lock()
        self.current: Optional[GameWindow] = None
        # Simulated geometry used on non-Windows platforms (and unit tests).
        self.simulated_rect = (100, 100, 1280, 720)

    # -- discovery ----------------------------------------------------------
    def list_windows(self) -> List[GameWindow]:
        title_contains = str(self.settings.get("window.title_contains", "Roblox")).lower()
        found: List[GameWindow] = []
        if IS_WINDOWS:
            for hwnd, title in _enum_windows():
                if title_contains in title.lower():
                    rect = _client_rect_screen(hwnd)
                    if rect:
                        x, y, w, h = rect
                        found.append(GameWindow(hwnd, title, x, y, w, h))
        else:
            x, y, w, h = self.simulated_rect
            found.append(GameWindow(0, f"{title_contains or 'Roblox'} (simulated)", x, y, w, h,
                                    simulated=True))
        with self._lock:
            self.current = found[0] if found else None
        return found

    def detect(self) -> Optional[GameWindow]:
        wins = self.list_windows()
        return wins[0] if wins else None

    # -- focus --------------------------------------------------------------
    def focus(self, window: Optional[GameWindow] = None) -> bool:
        win = window or self.current or self.detect()
        if win is None:
            return False
        if IS_WINDOWS and not win.simulated:
            try:
                hwnd = win.handle
                if _user32.IsIconic(hwnd):
                    _user32.ShowWindow(hwnd, _SW_RESTORE)
                    import time as _t
                    _t.sleep(0.12)
                # Bring to foreground robustly.
                fg = _user32.GetForegroundWindow()
                if fg != hwnd:
                    cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
                    fg_tid = _user32.GetWindowThreadProcessId(fg, None)
                    target_tid = _user32.GetWindowThreadProcessId(hwnd, None)
                    if fg_tid != cur_tid:
                        _user32.AttachThreadInput(cur_tid, fg_tid, True)
                        _user32.AttachThreadInput(cur_tid, target_tid, True)
                    _user32.SetForegroundWindow(hwnd)
                    if fg_tid != cur_tid:
                        _user32.AttachThreadInput(cur_tid, fg_tid, False)
                        _user32.AttachThreadInput(cur_tid, target_tid, False)
                return _user32.GetForegroundWindow() == hwnd
            except Exception:
                return False
        return True  # simulated / already focused

    # -- geometry -------------------------------------------------------------
    def refresh(self) -> Optional[GameWindow]:
        win = self.detect()
        if win:
            self.current = win
        return win
