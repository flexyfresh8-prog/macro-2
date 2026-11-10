"""Region color monitoring with change detection and macro triggers.

IF the selected screen region changes from color A to color B (beyond
tolerance, held for N consecutive samples) THEN run a configured action
(e.g. start a macro, tap a key).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple

import numpy as np

RGB = Tuple[int, int, int]


@dataclass
class ColorRegion:
    x: int
    y: int
    w: int
    h: int
    reference: Optional[RGB] = None            # color to watch against
    tolerance: int = 24                        # per-channel tolerance
    interval_ms: int = 150
    consecutive: int = 3
    cooldown_s: float = 1.5
    trigger_kind: str = "none"                 # none | macro | key
    trigger_payload: str = ""                  # macro id or key name
    enabled: bool = True

    _FIELDS = ("x", "y", "w", "h", "reference", "tolerance", "interval_ms",
               "consecutive", "cooldown_s", "trigger_kind", "trigger_payload", "enabled")

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self._FIELDS}

    @classmethod
    def from_dict(cls, d: dict) -> "ColorRegion":
        base = cls(0, 0, 10, 10)
        for k in cls._FIELDS:
            if k in d:
                setattr(base, k, d[k])
        return base


class ColorMonitor:
    """Samples a screen region and emits change events.

    ``sampler(x, y, w, h) -> BGR ndarray`` is injected so the monitor is
    testable without a real screen.
    """

    def __init__(self, sampler: Callable[[int, int, int, int], np.ndarray],
                 on_change: Optional[Callable[[dict], None]] = None,
                 on_sample: Optional[Callable[[dict], None]] = None):
        self.sampler = sampler
        self.on_change = on_change or (lambda data: None)
        self.on_sample = on_sample or (lambda data: None)
        self.region: Optional[ColorRegion] = None
        self.running = False
        self.error: str = ""
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def set_region(self, region: Optional[ColorRegion]) -> None:
        with self._lock:
            self.region = region

    def get_region(self) -> Optional[ColorRegion]:
        with self._lock:
            return self.region

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="NTH-ColorMonitor", daemon=True)
        self.running = True
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

    # -- core -------------------------------------------------------------------
    @staticmethod
    def _avg_rgb(frame_bgr: np.ndarray) -> RGB:
        if frame_bgr is None or frame_bgr.size == 0:
            return (0, 0, 0)
        mean = frame_bgr.reshape(-1, 3).mean(axis=0)
        return int(mean[2]), int(mean[1]), int(mean[0])       # -> R,G,B

    @staticmethod
    def distance(a: RGB, b: RGB) -> float:
        return max(abs(a[i] - b[i]) for i in range(3))

    def _loop(self) -> None:
        breach = 0
        last_trigger = 0.0
        while not self._stop.is_set():
            reg = self.get_region()
            if reg is None or not reg.enabled:
                self._stop.wait(0.1)
                continue
            try:
                frame = self.sampler(reg.x, reg.y, reg.w, reg.h)
                rgb = self._avg_rgb(frame)
                self.error = ""
            except Exception as exc:      # noqa: BLE001
                self.error = str(exc)
                self._stop.wait(0.5)
                continue

            payload = {
                "rgb": rgb, "hex": "#{:02X}{:02X}{:02X}".format(*rgb),
                "reference": reg.reference, "ts": time.time(),
            }
            self.on_sample(payload)

            now = time.monotonic()
            if reg.reference is not None:
                diff = self.distance(reg.reference, rgb)
                if diff > reg.tolerance:
                    breach += 1
                else:
                    breach = 0
                if breach >= max(reg.consecutive, 1) and (now - last_trigger) >= reg.cooldown_s:
                    breach = 0
                    last_trigger = now
                    self.on_change({
                        **payload,
                        "from": reg.reference,
                        "to": rgb,
                        "trigger_kind": reg.trigger_kind,
                        "trigger_payload": reg.trigger_payload,
                    })
            self._stop.wait(max(reg.interval_ms, 20) / 1000.0)
