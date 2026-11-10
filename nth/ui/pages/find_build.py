"""Find Build — one-click computer-vision build detection."""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QImage, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from nth.core.app_context import AppContext
from nth.ui import theme
from nth.ui.widgets import Card, ConfidenceRing, GlowButton, Meter, StatusDot, spaced_label


def frame_to_pixmap(frame_bgr) -> QPixmap:
    if frame_bgr is None:
        return QPixmap()
    h, w = frame_bgr.shape[:2]
    img = QImage(frame_bgr.data, w, h, 3 * w, QImage.Format_BGR888)
    return QPixmap.fromImage(img.copy())


class DetectWorker(QThread):
    """Runs locate -> focus -> capture -> analyze off the UI thread."""

    step = Signal(str)
    done = Signal(object)     # result dict
    failed = Signal(str)

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx

    def run(self):
        try:
            self.step.emit("locating")
            win = self.ctx.windows.refresh()
            if win is None:
                self.failed.emit("Roblox window not found. Launch Roblox Player first.")
                return
            self.step.emit("focusing")
            self.ctx.windows.focus(win)
            self.step.emit("capturing")
            from nth.core.capture import retry_capture
            scale = float(self.ctx.settings.get("vision.capture_scale", 1.0))
            frame = retry_capture(lambda: self.ctx.capture.grab_window(win, scale))
            self.step.emit("analyzing")
            payload = self.ctx.pipeline.detect(frame)
            result = self.ctx.build_engine.infer(payload)
            result["frame"] = frame
            result["window"] = win.title
            self.done.emit(result)
        except Exception as exc:      # noqa: BLE001
            self.failed.emit(str(exc))


class BuildResultCard(Card):
    def __init__(self, label: str, parent=None):
        super().__init__("", parent)
        self.setFixedHeight(150)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.ring = ConfidenceRing(0.0, 62)
        row.addWidget(self.ring, 0, Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.kind = spaced_label(label)
        col.addWidget(self.kind)
        self.name = QLabel("—")
        self.name.setObjectName("BigValue")
        col.addWidget(self.name)
        self.tier = QLabel("")
        self.tier.setObjectName("Micro")
        col.addWidget(self.tier)
        col.addStretch(1)
        row.addLayout(col, 1)
        self._layout.addLayout(row)
        self.ring.setFixedSize(62, 62)

    def set_result(self, entry: Optional[dict], tier: str = "") -> None:
        if entry:
            self.ring.set_value(entry["confidence"])
            self.name.setText(entry["name"])
            self.tier.setText(f"TIER {tier.upper()} · CONF {entry['confidence'] * 100:.1f}%")
        else:
            self.ring.set_value(0.0)
            self.name.setText("Unresolved")
            self.tier.setText("No qualifying match")


class FindBuildPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("Page")
        self._worker: Optional[DetectWorker] = None
        self._last_result = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("Find Build")
        title.setObjectName("SectionTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.ts_label = QLabel("")
        self.ts_label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px;")
        head.addWidget(self.ts_label)
        outer.addLayout(head)

        # pipeline status strip
        steps_row = QHBoxLayout()
        steps_row.setSpacing(8)
        self.steps = {}
        for key, label in (("locating", "LOCATE WINDOW"), ("focusing", "FOCUS"),
                           ("capturing", "CAPTURE"), ("analyzing", "ANALYZE")):
            chip = QLabel(label)
            chip.setStyleSheet(f"""
                QLabel {{ background: {theme.BG_ELEVATED}; color: {theme.TEXT_DIM};
                          border: 1px solid {theme.BORDER}; border-radius: 7px;
                          padding: 5px 12px; font-size: 10px; }}
            """)
            self.steps[key] = chip
            steps_row.addWidget(chip)
        steps_row.addStretch(1)
        outer.addLayout(steps_row)

        # main row: find button + results
        main = QHBoxLayout()
        main.setSpacing(12)

        left = Card()
        l = left.body()
        l.addStretch(1)
        self.find_btn = GlowButton("FIND BUILD", "primary")
        self.find_btn.setMinimumSize(240, 54)
        f = QFont()
        f.setWeight(QFont.DemiBold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 3.0)
        self.find_btn.setFont(f)
        self.find_btn.clicked.connect(self.run_detection)
        l.addWidget(self.find_btn, 0, Qt.AlignHCenter)
        self.status = QLabel("Locate the Roblox window, open your inventory or hotbar,"
                             " then run detection.")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignCenter)
        l.addWidget(self.status)
        l.addSpacing(6)
        self.ref_hint = QLabel("")
        self.ref_hint.setObjectName("Micro")
        self.ref_hint.setWordWrap(True)
        self.ref_hint.setAlignment(Qt.AlignCenter)
        l.addWidget(self.ref_hint)
        l.addStretch(1)
        main.addWidget(left, 2)

        results_col = QVBoxLayout()
        results_col.setSpacing(12)
        self.card_fruit = BuildResultCard("Fruit")
        self.card_sword = BuildResultCard("Sword")
        self.card_style = BuildResultCard("Fighting Style")
        results_col.addWidget(self.card_fruit)
        results_col.addWidget(self.card_sword)
        results_col.addWidget(self.card_style)
        results_wrap = QWidget()
        results_wrap.setLayout(results_col)
        main.addWidget(results_wrap, 3)
        outer.addLayout(main, 1)

        # screenshot + alternatives row
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        shot = Card("Screenshot Preview")
        self.shot_label = QLabel("No capture yet")
        self.shot_label.setAlignment(Qt.AlignCenter)
        self.shot_label.setMinimumSize(320, 200)
        self.shot_label.setStyleSheet(f"""
            background: {theme.BG_ELEVATED}; border: 1px solid {theme.BORDER};
            border-radius: 8px; color: {theme.TEXT_DIM};
        """)
        self.shot_label.setScaledContents(True)
        shot.add(self.shot_label)
        bottom.addWidget(shot, 5)

        alts = Card("Alternatives & Unknowns")
        self.alts_list = QListWidget()
        alts.add(self.alts_list)
        bottom.addWidget(alts, 3)

        actions_col = QVBoxLayout()
        save_btn = GlowButton("SAVE BUILD", "primary")
        save_btn.clicked.connect(self.save_build)
        self.save_hint = QLabel("")
        self.save_hint.setObjectName("Micro")
        self.save_hint.setWordWrap(True)
        actions_col.addWidget(save_btn)
        actions_col.addWidget(self.save_hint)
        actions_col.addStretch(1)
        rescan_btn = GlowButton("RESCAN", "ghost")
        rescan_btn.clicked.connect(self.run_detection)
        actions_col.addWidget(rescan_btn)
        history_btn = GlowButton("BUILD HISTORY", "ghost")
        history_btn.clicked.connect(self.show_history)
        actions_col.addWidget(history_btn)
        bottom.addLayout(actions_col, 1)
        outer.addLayout(bottom, 1)

        self._update_ref_hint()

    # ------------------------------------------------------------------ flow
    def _update_ref_hint(self) -> None:
        refs = len(self.ctx.icon_db.all_references())
        total = self.ctx.catalog.counts()["total"]
        if refs == 0:
            self.ref_hint.setText("⚠ Reference icon database is empty — add item references"
                                  " in the Vision Engine before detecting.")
            self.ref_hint.setStyleSheet(f"color: {theme.WARN};")
        else:
            self.ref_hint.setText(f"{refs}/{total} items have reference icons.")
            self.ref_hint.setStyleSheet(f"color: {theme.TEXT_DIM};")

    def run_detection(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self.find_btn.setEnabled(False)
        self.find_btn.setText("SCANNING…")
        self._set_step("locating")
        self._worker = DetectWorker(self.ctx)
        self._worker.step.connect(self._set_step)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _set_step(self, key: str) -> None:
        for k, chip in self.steps.items():
            active = k == key
            chip.setStyleSheet(f"""
                QLabel {{ background: {'%s' % theme.BG_ACTIVE};
                          color: {'%s' % theme.ACCENT};
                          border: 1px solid {'%s' % theme.BORDER_BRIGHT};
                          border-radius: 7px; padding: 5px 12px; font-size: 10px; }}
            """ if active else f"""
                QLabel {{ background: {theme.BG_ELEVATED}; color: {theme.TEXT_DIM};
                          border: 1px solid {theme.BORDER}; border-radius: 7px;
                          padding: 5px 12px; font-size: 10px; }}
            """)

    def _clear_steps(self) -> None:
        self._set_step("")

    def _on_fail(self, msg: str) -> None:
        self.find_btn.setEnabled(True)
        self.find_btn.setText("FIND BUILD")
        self._clear_steps()
        self.status.setText(f"✕ {msg}")
        self.status.setStyleSheet(f"color: {theme.ERR};")
        self.ctx.bus.activity.emit("vision", f"Detection failed: {msg}")

    def _on_done(self, result: dict) -> None:
        self.find_btn.setEnabled(True)
        self.find_btn.setText("FIND BUILD")
        self._clear_steps()
        self._last_result = result
        self._update_ref_hint()

        build = result.get("build", {})
        tiers = {}
        for cat, item in (("fruit", "fruit"), ("sword", "sword"), ("style", "style")):
            entry = build.get(cat)
            item_obj = self.ctx.catalog.get(entry["id"]) if entry else None
            tiers[cat] = item_obj.tier if item_obj else ""
        self.card_fruit.set_result(build.get("fruit"), tiers["fruit"])
        self.card_sword.set_result(build.get("sword"), tiers["sword"])
        self.card_style.set_result(build.get("style"), tiers["style"])

        unresolved = result.get("unresolved", [])
        needs = result.get("needs_rescan", False)
        conf = result.get("overall_confidence", 0.0)
        if result.get("status") == "no_references":
            self.status.setText("Reference database is empty — add references in the"
                                " Vision Engine, then scan again.")
            self.status.setStyleSheet(f"color: {theme.WARN};")
        elif needs:
            self.status.setText(f"Low confidence ({conf * 100:.0f}%). Re-open your inventory"
                                " clearly and scan again — unresolved: "
                                + (", ".join(unresolved) if unresolved else "—"))
            self.status.setStyleSheet(f"color: {theme.WARN};")
        else:
            self.status.setText(f"Detected build — overall confidence {conf * 100:.0f}%.")
            self.status.setStyleSheet(f"color: {theme.OK};")
        self.ts_label.setText(time.strftime("SCAN %Y-%m-%d %H:%M:%S", time.localtime(result["ts"])))

        frame = result.get("frame")
        if frame is not None:
            payload = {"detections": result.get("detections", []),
                       "threshold": result.get("threshold", 0.7)}
            annotated = self.ctx.pipeline.draw_detections(frame, payload)
            pm = frame_to_pixmap(annotated)
            self.shot_label.setPixmap(pm)

        self.alts_list.clear()
        for cat, alts in result.get("alternatives", {}).items():
            for a in alts:
                QListWidgetItem(f"{cat.title()}: {a['name']}  ({a['confidence'] * 100:.0f}%)"
                                if "confidence" in a else f"{cat.title()}: {a['name']}",
                                self.alts_list)
        for cat in unresolved:
            QListWidgetItem(f"{cat.title()}: unresolved — no match above threshold",
                            self.alts_list)
        if not result.get("alternatives") and not unresolved:
            QListWidgetItem("No competing matches — detection unambiguous.", self.alts_list)

        self.ctx.set_last_build({"ts": result["ts"], "summary": result.get("summary", ""),
                                 "overall_confidence": conf,
                                 "build": result.get("build", {})})
        self.ctx.bus.activity.emit("vision", f"Scan complete: {result.get('summary')}")

    def save_build(self) -> None:
        if not self._last_result:
            self.save_hint.setText("Run FIND BUILD first.")
            return
        shot_path = ""
        frame = self._last_result.get("frame")
        if frame is not None:
            from pathlib import Path
            from nth.settings.manager import data_dir
            d = data_dir() / "builds"
            d.mkdir(parents=True, exist_ok=True)
            shot_path = str(d / f"build_{int(self._last_result['ts'])}.png")
            import cv2
            cv2.imwrite(shot_path, frame)
        build_id = self.ctx.build_engine.save(self._last_result, shot_path,
                                              {k: v for k, v in self._last_result.items()
                                               if k != "frame"})
        self.save_hint.setText(f"Saved build #{build_id} to history.")
        self.ctx.bus.activity.emit("db", f"Build #{build_id} saved")

    def show_history(self) -> None:
        rows = self.ctx.build_engine.history(20)
        self.alts_list.clear()
        if not rows:
            QListWidgetItem("No saved builds yet.", self.alts_list)
            return
        for r in rows:
            ts = time.strftime("%m-%d %H:%M", time.localtime(r["ts"]))
            QListWidgetItem(f"[{ts}]  {r['fruit'] or '?'} / {r['sword'] or '?'} / "
                            f"{r['style'] or '?'}", self.alts_list)

    def showEvent(self, e) -> None:
        self._update_ref_hint()
        super().showEvent(e)
