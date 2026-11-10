"""Screen capture built on mss (fast, multi-monitor aware)."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional, Tuple

import numpy as np


class CaptureError(RuntimeError):
    pass


class ScreenCapture:
    """Captures screen regions as BGR numpy arrays."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sct = None

    def _grabber(self):
        with self._lock:
            if self._sct is None:
                import mss
                self._sct = mss.mss()
            return self._sct

    def close(self) -> None:
        with self._lock:
            if self._sct is not None:
                try:
                    self._sct.close()
                except Exception:
                    pass
                self._sct = None

    def grab(self, x: int, y: int, w: int, h: int, scale: float = 1.0) -> np.ndarray:
        """Capture a screen rect -> BGR uint8 ndarray."""
        if w <= 0 or h <= 0:
            raise CaptureError(f"invalid region {w}x{h}")
        sct = self._grabber()
        region = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
        with self._lock:
            raw = sct.grab(region)
        frame = np.asarray(raw)[:, :, :3]          # BGRA -> BGR
        if scale and abs(scale - 1.0) > 1e-3:
            import cv2
            frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        return np.ascontiguousarray(frame)

    def grab_window(self, win, scale: float = 1.0) -> np.ndarray:
        """Capture the client area of a GameWindow."""
        return self.grab(win.x, win.y, win.w, win.h, scale)


def average_color(frame_bgr: np.ndarray) -> Tuple[int, int, int]:
    """Average BGR color of a frame region."""
    if frame_bgr.size == 0:
        return (0, 0, 0)
    mean = frame_bgr.reshape(-1, 3).mean(axis=0)
    return int(mean[0]), int(mean[1]), int(mean[2])   # B, G, R


def retry_capture(grab_fn: Callable[[], np.ndarray], attempts: int = 3, delay: float = 0.15,
                  on_error: Optional[Callable[[Exception], None]] = None) -> np.ndarray:
    """Capture with retries (screen lock, transient mss errors)."""
    last: Optional[Exception] = None
    for _ in range(attempts):
        try:
            return grab_fn()
        except Exception as exc:      # noqa: BLE001
            last = exc
            if on_error:
                on_error(exc)
            time.sleep(delay)
    raise CaptureError(f"capture failed after {attempts} attempts: {last}")
