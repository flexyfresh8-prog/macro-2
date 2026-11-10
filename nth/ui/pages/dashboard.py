"""Dashboard — live system overview with animated indicators."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QScrollArea, QVBoxLayout, QWidget)

from nth.ui import theme
from nth.ui.widgets import Card, Meter, StatusDot, spaced_label


class Sparkline(QWidget):
    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        self.data = list(data or [])
        self.setMinimumSize(120, 40)

    def push(self, v: float):
        self.data.append(v)
        if len(self.data) > 48:
            self.data.pop(0)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor_(theme.BORDER), 1))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
        if len(self.data) >= 2:
            path = QPainterPath()
            maxv = max(self.data) or 1.0
            step = (self.width() - 8) / (len(self.data) - 1)
            for i, v in enumerate(self.data):
                x = 4 + i * step
                y = self.height() - 4 - (v / maxv) * (self.height() - 10)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setPen(QPen(QColor_(theme.ACCENT), 1.4))
            p.drawPath(path)
        p.end()


def QColor_(s):
    from PySide6.QtGui import QColor
    return QColor(s)


class StatusCard(Card):
    def __init__(self, title: str, parent=None):
        super().__init__("", parent)
        self.setFixedHeight(118)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.dot = StatusDot("off")
        self.dot.setFixedSize(13, 13)
        row.addWidget(self.dot, 0, Qt.AlignVCenter)
        row.addWidget(spaced_label(title))
        row.addStretch(1)
        self._layout.addLayout(row)
        self.value = QLabel("—")
        self.value.setObjectName("BigValue")
        self._layout.addWidget(self.value)
        self.sub = QLabel("")
        self.sub.setObjectName("Micro")
        self.sub.setWordWrap(True)
        self._layout.addWidget(self.sub)
        self._layout.addStretch(1)

    def set(self, state: str, value: str, sub: str = "") -> None:
        self.dot.set_state(state)
        self.value.setText(value)
        self.sub.setText(sub)


class DashboardPage(QWidget):
    def __init__(self, ctx: AppContext):
        from nth.core.app_context import AppContext  # noqa: F401 (typing only)
        super().__init__()
        self.ctx = ctx
        self.setObjectName("Page")
        self.scan_history = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("SectionTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.uptime_lbl = QLabel("UPTIME 00:00:00")
        self.uptime_lbl.setStyleSheet(f"color: {theme.TEXT_2}; font-size: 10px;")
        head.addWidget(self.uptime_lbl)
        outer.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.card_system = StatusCard("System")
        self.card_roblox = StatusCard("Roblox Player")
        self.card_build = StatusCard("Detected Build")
        self.card_macro = StatusCard("Active Macro")
        self.card_mouse = StatusCard("Mouse Tracking")
        self.card_vision = StatusCard("Vision Engine")
        for i, card in enumerate((self.card_system, self.card_roblox, self.card_build,
                                  self.card_macro, self.card_mouse, self.card_vision)):
            grid.addWidget(card, i // 3, i % 3)
        outer.addLayout(grid)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        activity = Card("Recent Activity")
        self.activity_list = QListWidget()
        self.activity_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        activity.add(self.activity_list)
        bottom.addWidget(activity, 3)

        perf = Card("Performance")
        p_lay = perf.body()
        self.meter_vision = self._perf_row(p_lay, "VISION SCAN")
        self.meter_macro = self._perf_row(p_lay, "MACRO ACTIONS/MIN")
        self.meter_input = self._perf_row(p_lay, "INPUT EVENTS/MIN")
        self.spark = Sparkline()
        p_lay.addWidget(self.spark)
        self.spark_lbl = QLabel("Scan confidence trend")
        self.spark_lbl.setObjectName("Micro")
        p_lay.addWidget(self.spark_lbl)
        bottom.addWidget(perf, 2)
        outer.addLayout(bottom, 1)

        # timers + subscriptions
        self._tick = QTimer(self)
        self._tick.timeout.connect(self.refresh)
        self._tick.start(1000)
        ctx.bus.activity.connect(self._on_activity)
        ctx.bus.roblox_changed.connect(self._on_roblox)
        ctx.bus.build_detected.connect(self._on_build)
        ctx.bus.macro_state.connect(self._on_macro)
        for entry in reversed(ctx.db.recent_activity(20)):
            self._push_activity(time.strftime("%H:%M:%S", time.localtime(entry["ts"])),
                                entry["msg"])
        self.refresh()

    # ------------------------------------------------------------- ui helpers
    def _perf_row(self, lay: QVBoxLayout, label: str) -> Meter:
        row = QHBoxLayout()
        lbl = spaced_label(label)
        row.addWidget(lbl)
        row.addStretch(1)
        val = QLabel("—")
        val.setObjectName("Mono")
        val.setStyleSheet(f"color: {theme.TEXT_2};")
        row.addWidget(val)
        lay.addLayout(row)
        meter = Meter(0.0)
        lay.addWidget(meter)
        meter._val_lbl = val
        return meter

    # ----------------------------------------------------------------- events
    def _on_activity(self, tag: str, msg: str) -> None:
        self._push_activity(time.strftime("%H:%M:%S"), msg)

    def _push_activity(self, ts: str, msg: str) -> None:
        item = QListWidgetItem(f"{ts}   {msg}")
        self.activity_list.insertItem(0, item)
        while self.activity_list.count() > 60:
            self.activity_list.takeItem(self.activity_list.count() - 1)

    def _on_roblox(self, detected: bool, title: str) -> None:
        if detected:
            self.card_roblox.set("on", "DETECTED", title)
        else:
            self.card_roblox.set("warn", "NOT FOUND", "Launch Roblox Player")

    def _on_build(self, payload: dict) -> None:
        self.card_build.set("on", payload.get("summary", "—"),
                            time.strftime("%H:%M:%S", time.localtime(payload.get("ts", time.time()))))
        conf = payload.get("overall_confidence", 0.0)
        self.scan_history.append(max(0.05, conf))
        self.spark.push(max(0.05, conf))

    def _on_macro(self, state: str, index: int) -> None:
        mapping = {"running": "run", "paused": "warn", "idle": "off", "finished": "on"}
        name = self.ctx.macro_engine.current_macro.name if self.ctx.macro_engine.current_macro else "—"
        self.card_macro.set(mapping.get(state, "off"), state.upper(),
                            name if state != "idle" else "No macro active")

    # ------------------------------------------------------------------ timer
    def refresh(self) -> None:
        up = int(self.ctx.uptime())
        self.uptime_lbl.setText(
            f"UPTIME {up // 3600:02d}:{(up % 3600) // 60:02d}:{up % 60:02d}")
        self.card_system.set("on", "OPERATIONAL",
                             f"Input: {'REAL (SendInput)' if self.ctx.input.is_real else 'DRY-RUN'}")

        snap = self.ctx.tracker.snapshot()
        if snap["available"]:
            x, y = snap["position"]
            self.card_mouse.set("run", f"{x} , {y}", f"Speed {snap['speed']:.0f} px/s · {snap['clicks']} clicks")
        else:
            self.card_mouse.set("warn", "N/A", "Mouse tracking requires Windows")

        scan_ms = self.ctx.pipeline.last_scan_ms
        self.meter_vision._val_lbl.setText(f"{scan_ms:.0f} ms")
        self.meter_vision.set_value(min(1.0, scan_ms / 1000.0) if scan_ms else 0.0)
        refs = len(self.ctx.icon_db.all_references())
        self.card_vision.set("on" if refs else "warn",
                             f"{refs} REFERENCES",
                             f"Threshold {self.ctx.settings.match_threshold():.2f}")

        import time as _t
        now = _t.monotonic()
        if not hasattr(self, "_last_counts"):
            self._last_counts = (now, self.ctx.macro_engine.actions_done)
        prev_t, prev_c = self._last_counts
        if now - prev_t >= 1.0:
            rate = (self.ctx.macro_engine.actions_done - prev_c) / (now - prev_t) * 60
            self.meter_macro._val_lbl.setText(f"{rate:.0f}")
            self.meter_macro.set_value(min(1.0, rate / 120.0))
            self._last_counts = (now, self.ctx.macro_engine.actions_done)
