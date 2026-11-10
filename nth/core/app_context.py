"""Application context — the service hub shared by every UI page.

Holds settings, database, catalog, icon DB, window manager, capture,
input backend, macro engine, mouse tracker, color monitor and an
activity/event bus so pages stay decoupled from the engine internals.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from nth.core.capture import ScreenCapture
from nth.core.color_monitor import ColorMonitor
from nth.core.input_backend import DryRunInputBackend, make_backend
from nth.core.mouse_tracker import MouseTracker
from nth.core.window_manager import WindowManager
from nth.database.db import Database
from nth.items.catalog import Catalog
from nth.macros.engine import MacroEngine
from nth.recognition.build_engine import BuildEngine
from nth.settings.manager import Settings, data_dir
from nth.vision.icon_db import IconDatabase
from nth.vision.pipeline import VisionPipeline


class EventBus(QObject):
    activity = Signal(str, str)            # tag, message
    status = Signal(str, str)              # key, value
    roblox_changed = Signal(bool, str)     # detected, title
    build_detected = Signal(dict)          # build result payload
    macro_state = Signal(str, int)         # state, action index
    color_event = Signal(dict)             # sample / change payloads


class AppContext:
    """Created once in main(); passed into every page."""

    def __init__(self):
        self.settings = Settings()
        self.db = Database(data_dir() / "nth.db")
        self.catalog = Catalog(data_dir())
        self.icon_db = IconDatabase()
        self.bus = EventBus()
        self.windows = WindowManager(self.settings)
        self.capture = ScreenCapture()
        self.pipeline = VisionPipeline(self.settings, self.icon_db)
        self.build_engine = BuildEngine(self.catalog, self.db, self.settings)
        self.input = make_backend(self.settings)

        # Mouse tracker (event -> bus bridge keeps Qt out of the core layer)
        self.tracker = MouseTracker(self.settings, on_event=self._on_tracker_event)
        self.tracker.start()

        # Color monitor wired to real capture + macro triggers
        self.color_monitor = ColorMonitor(
            sampler=self._sample_region,
            on_change=self._on_color_change,
            on_sample=lambda payload: self.bus.color_event.emit({"kind": "sample", **payload}),
        )
        self.color_monitor.set_region(self._restore_color_region())

        self.macro_engine = MacroEngine(self.input, self.settings, self._activity)
        self.macro_engine.on_state = lambda s, i: self.bus.macro_state.emit(s, i)

        self.last_build: Optional[Dict] = None
        self.start_time = time.time()
        self._activity_ring: Deque[Dict] = deque(maxlen=120)
        self._lock = threading.Lock()

        self.bus.activity.connect(self._remember_activity)
        self._activity("system", "NTH core initialized")
        self.db.log("system", "NTH started")

    # ------------------------------------------------------------------ utils
    def _activity(self, tag: str, msg: str) -> None:
        self.bus.activity.emit(tag, msg)

    def _on_tracker_event(self, kind: str, data: dict) -> None:
        if kind == "click":
            self.bus.activity.emit(
                "mouse", f"{data['button']} click @ {data['pos'][0]},{data['pos'][1]}")

    def _remember_activity(self, tag: str, msg: str) -> None:
        with self._lock:
            self._activity_ring.append({"ts": time.time(), "tag": tag, "msg": msg})

    def activity_snapshot(self) -> List[Dict]:
        with self._lock:
            return list(self._activity_ring)

    def uptime(self) -> float:
        return time.time() - self.start_time

    # ----------------------------------------------------------- window detect
    def poll_roblox(self) -> None:
        win = self.windows.detect()
        detected = win is not None
        self.bus.status.emit("roblox", "detected" if detected else "not_found")
        self.bus.roblox_changed.emit(detected, win.title if win else "")

    def focus_roblox(self) -> bool:
        win = self.windows.refresh()
        if win is None:
            self._activity("window", "Roblox window not found")
            return False
        ok = self.windows.focus(win)
        self._activity("window", f"Focused '{win.title}'" if ok else "Focus failed")
        return ok

    # ----------------------------------------------------------- color region
    def _sample_region(self, x: int, y: int, w: int, h: int):
        from nth.core.capture import retry_capture
        return retry_capture(lambda: self.capture.grab(x, y, w, h), attempts=1)

    def _on_color_change(self, data: Dict) -> None:
        self.bus.color_event.emit({"kind": "change", **data})
        kind = data.get("trigger_kind")
        payload = data.get("trigger_payload") or ""
        if kind == "macro" and payload:
            macro = self.macro_engine.load_macro_by_name(payload)
            if macro is not None:
                self.macro_engine.start_macro(macro, loop=False)
                self._activity("color", f"Triggered macro '{payload}'")
        elif kind == "key" and payload:
            self.input.tap_key(payload, hold=float(self.settings.get("input.key_hold", 0.045)))
            self._activity("color", f"Triggered key {payload}")

    def _restore_color_region(self):
        raw = self.settings.get("color.region", None)
        if not raw:
            return None
        from nth.core.color_monitor import ColorRegion
        try:
            return ColorRegion.from_dict(raw)
        except Exception:
            return None

    def save_color_region(self, region) -> None:
        self.color_monitor.set_region(region)
        if region is not None:
            self.settings.set("color.region", region.to_dict())
        else:
            self.settings.set("color.region", None)

    # ------------------------------------------------------------- build flow
    def set_last_build(self, payload: Dict) -> None:
        self.last_build = payload
        self.bus.build_detected.emit(payload)
        self.bus.status.emit("build", payload.get("summary", ""))

    # ------------------------------------------------------------------ close
    def shutdown(self) -> None:
        try:
            self.macro_engine.stop()
            self.color_monitor.stop()
            self.tracker.stop()
            self.capture.close()
            self.db.log("system", "NTH shutdown")
            self.db.close()
        except Exception:
            pass
