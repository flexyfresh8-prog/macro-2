"""Mouse movement recording and replay.

Recording polls the cursor (Windows) at a fixed rate, capturing position and
click edges.  Recordings are compressed (near-duplicate / collinear points
removed) and stored as JSON so users can edit points, insert pauses and
clicks, adjust replay speed, and build custom movement paths.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Callable, List, Optional, Tuple

Point = Tuple[int, int, float]      # x, y, t_offset_seconds
Click = Tuple[float, str]           # t_offset, button


class MouseRecorder:
    """Records and replays mouse paths (Windows; dry-run logging elsewhere)."""

    def __init__(self, input_backend=None, settings=None):
        self.input = input_backend
        self.settings = settings
        self.available = sys.platform == "win32"
        self.recording = False
        self.replaying = False
        self.points: List[Point] = []
        self.clicks: List[Click] = []
        self.duration: float = 0.0
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._cancel = threading.Event()

    # ------------------------------------------------------------------ record
    def start_recording(self) -> bool:
        if self.recording or not self.available:
            return self.available
        self.points, self.clicks, self.duration = [], [], 0.0
        self._stop.clear()
        rate = max(int(self.settings.get("mouse.poll_rate", 60)) if self.settings else 60, 15)
        self._thread = threading.Thread(target=self._record_loop, args=(rate,),
                                        name="NTH-MouseRecorder", daemon=True)
        self.recording = True
        self._thread.start()
        return True

    def stop_recording(self) -> dict:
        self.recording = False
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self.points = self.compress(self.points)
        return {"points": list(self.points), "clicks": list(self.clicks),
                "duration": round(self.duration, 3)}

    def _record_loop(self, rate: int) -> None:
        import ctypes

        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        t0 = time.monotonic()
        prev_left = prev_right = False
        interval = 1.0 / rate
        while not self._stop.is_set():
            pt = _POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            t = time.monotonic() - t0
            self.points.append((pt.x, pt.y, t))
            left = bool(user32.GetAsyncKeyState(0x01) & 0x8000)
            right = bool(user32.GetAsyncKeyState(0x02) & 0x8000)
            if left and not prev_left:
                self.clicks.append((t, "left"))
            if right and not prev_right:
                self.clicks.append((t, "right"))
            prev_left, prev_right = left, right
            self.duration = t
            self._stop.wait(interval)

    # ------------------------------------------------------------------ replay
    def replay(self, points: List[Point], clicks: Optional[List[Click]] = None,
               speed: float = 1.0, on_progress: Optional[Callable[[int, int], None]] = None,
               on_click: Optional[Callable[[str], None]] = None) -> bool:
        """Replay a path with speed multiplier and click events."""
        if not points or self.input is None:
            return False
        self.replaying = True
        self._cancel.clear()
        try:
            clicks = sorted(clicks or [], key=lambda c: c[0])
            t0 = time.monotonic()
            ci = 0
            for i, (x, y, t) in enumerate(points):
                if self._cancel.is_set():
                    return False
                target = (t / max(speed, 0.05))
                wait = target - (time.monotonic() - t0)
                if wait > 0:
                    time.sleep(min(wait, 2.0))
                self.input.move_to(int(x), int(y))
                while ci < len(clicks) and clicks[ci][0] <= t:
                    self.input.click(clicks[ci][1])
                    if on_click:
                        on_click(clicks[ci][1])
                    ci += 1
                if on_progress and i % 5 == 0:
                    on_progress(int(x), int(y))
            # clicks trailing the last point
            while ci < len(clicks):
                self.input.click(clicks[ci][1])
                if on_click:
                    on_click(clicks[ci][1])
                ci += 1
            return True
        finally:
            self.replaying = False

    def cancel_replay(self) -> None:
        self._cancel.set()

    # ------------------------------------------------------------------ editing
    @staticmethod
    def compress(points: List[Point], min_dist: float = 1.5,
                 collinear_eps: float = 1.2) -> List[Point]:
        """Drop near-duplicate and collinear points while preserving shape."""
        if len(points) < 3:
            return list(points)
        out: List[Point] = [points[0]]
        for p in points[1:]:
            lx, ly, _ = out[-1]
            if (p[0] - lx) ** 2 + (p[1] - ly) ** 2 < min_dist ** 2:
                out[-1] = (p[0], p[1], p[2])
                continue
            if len(out) >= 2:
                px_, py_, _ = out[-2]
                # distance of new point from line (prev -> last)
                ax, ay = lx - px_, ly - py_
                bx, by = p[0] - px_, p[1] - py_
                denom = (ax * ax + ay * ay) ** 0.5
                if denom > 1e-6:
                    dist = abs(ax * by - ay * bx) / denom
                    if dist < collinear_eps:
                        out[-1] = (p[0], p[1], p[2])
                        continue
            out.append((p[0], p[1], p[2]))
        return out

    @staticmethod
    def insert_pause(points: List[Point], index: int, seconds: float) -> List[Point]:
        """Insert a pause at index by shifting subsequent timestamps."""
        if not points or index < 0 or index >= len(points):
            return list(points)
        out = [tuple(p) for p in points]
        base_t = out[index][2]
        out.insert(index + 1, (out[index][0], out[index][1], base_t + seconds))
        for i in range(index + 2, len(out)):
            x, y, t = out[i]
            out[i] = (x, y, t + seconds)
        return out

    @staticmethod
    def scale_speed(points: List[Point], factor: float) -> List[Point]:
        f = max(0.05, factor)
        return [(x, y, t / f) for x, y, t in points]
