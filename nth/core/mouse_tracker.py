"""Live mouse tracking: coordinates, speed, clicks, movement history."""

from __future__ import annotations

import sys
import threading
import time
from collections import deque
from typing import Callable, Deque, List, Optional, Tuple

Point = Tuple[int, int]


class MouseTracker:
    """Polls cursor position on a background thread.

    Works on Windows via GetCursorPos/GetAsyncKeyState.  On other platforms
    ``available`` is False and callers should show that honestly in the UI.
    """

    def __init__(self, settings, on_event: Optional[Callable[[str, dict], None]] = None):
        self.settings = settings
        self.on_event = on_event or (lambda tag, data: None)
        self.available = sys.platform == "win32"
        self.running = False
        self.position: Point = (0, 0)
        self.speed_pps: float = 0.0           # pixels per second
        self.click_count: int = 0
        self.trail: Deque[Point] = deque(maxlen=int(settings.get("mouse.trail_length", 400)))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pos_lock = threading.Lock()

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> bool:
        if self.running or not self.available:
            return self.available
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="NTH-MouseTracker", daemon=True)
        self.running = True
        self._thread.start()
        return True

    def stop(self) -> None:
        self.running = False
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    # -- internals -------------------------------------------------------------
    def _loop(self) -> None:
        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        poll = 1.0 / max(int(self.settings.get("mouse.poll_rate", 60)), 10)
        detect_clicks = bool(self.settings.get("mouse.click_detect", True))
        prev_pos: Optional[Point] = None
        prev_t = time.monotonic()
        prev_left = prev_right = False

        while not self._stop.is_set():
            now = time.monotonic()
            pt = _POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            pos = (pt.x, pt.y)
            with self._pos_lock:
                self.position = pos
                self.trail.append(pos)

            if prev_pos is not None:
                dt = max(now - prev_t, 1e-4)
                dist = ((pos[0] - prev_pos[0]) ** 2 + (pos[1] - prev_pos[1]) ** 2) ** 0.5
                inst = dist / dt
                with self._pos_lock:
                    self.speed_pps = self.speed_pps * 0.7 + inst * 0.3

            if detect_clicks:
                left = bool(user32.GetAsyncKeyState(0x01) & 0x8000)
                right = bool(user32.GetAsyncKeyState(0x02) & 0x8000)
                if left and not prev_left:
                    self.click_count += 1
                    self.on_event("click", {"button": "left", "pos": pos})
                if right and not prev_right:
                    self.click_count += 1
                    self.on_event("click", {"button": "right", "pos": pos})
                prev_left, prev_right = left, right

            prev_pos, prev_t = pos, now
            self._stop.wait(poll)

    # -- snapshot ---------------------------------------------------------------
    def snapshot(self) -> dict:
        with self._pos_lock:
            return {
                "available": self.available,
                "position": self.position,
                "speed": round(self.speed_pps, 1),
                "clicks": self.click_count,
                "trail": list(self.trail),
            }
