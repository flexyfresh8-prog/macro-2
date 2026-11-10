"""Vision Engine — reference database management + detection console."""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                               QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from nth.core.app_context import AppContext
from nth.ui import theme
from nth.ui.pages.find_build import frame_to_pixmap
from nth.ui.widgets import Card, GlowButton, StatusDot, spaced_label


class RegionPickerDialog(QDialog):
    """Capture the Roblox window and drag a rectangle to crop a reference icon."""

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Capture reference icon")
        self.setMinimumSize(860, 560)
        self.frame = None
        self.rect_start = None
        self.rect_now = None
        lay = QVBoxLayout(self)
        hint = QLabel("Drag a rectangle around an item icon, then press SAVE CROP.")
        hint.setObjectName("Hint")
        lay.addWidget(hint)

        self.view = QLabel()
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setMinimumSize(820, 420)
        self.view.setStyleSheet(f"background: {theme.BG_ELEVATED};"
                                f" border: 1px solid {theme.BORDER}; border-radius: 8px;")
        self.view.setScaledContents(True)
        self.view.mousePressEvent = self._press
        self.view.mouseMoveEvent = self._move
        self.view.mouseReleaseEvent = self._release
        lay.addWidget(self.view, 1)

        btns = QHBoxLayout()
        cap_btn = GlowButton("CAPTURE SCREEN")
        cap_btn.clicked.connect(self._capture)
        self.save_btn = GlowButton("SAVE CROP", "primary")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.accept)
        cancel = GlowButton("CANCEL", "ghost")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cap_btn)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(self.save_btn)
        lay.addLayout(btns)
        self._capture()

    def _capture(self) -> None:
        try:
            win = self.ctx.windows.refresh()
            if win is None:
                QMessageBox.warning(self, "No window", "Roblox window not found.")
                return
            self.ctx.windows.focus(win)
            from nth.core.capture import retry_capture
            self.frame = retry_capture(lambda: self.ctx.capture.grab_window(win))
            pm = frame_to_pixmap(self.frame)
            self.view.setPixmap(pm)
        except Exception as exc:      # noqa: BLE001
            QMessageBox.warning(self, "Capture failed", str(exc))

    # rect picking ------------------------------------------------------------
    def _to_frame_coords(self, pos) -> tuple:
        pm = self.view.pixmap()
        if pm is None or self.frame is None:
            return None
        vw, vh = self.view.width(), self.view.height()
        fw, fh = self.frame.shape[1], self.frame.shape[0]
        x = int(pos.x() / vw * fw)
        y = int(pos.y() / vh * fh)
        return x, y

    def _press(self, e) -> None:
        self.rect_start = self._to_frame_coords(e.position())
        self.rect_now = self.rect_start

    def _move(self, e) -> None:
        if self.rect_start:
            self.rect_now = self._to_frame_coords(e.position())

    def _release(self, e) -> None:
        self.rect_now = self._to_frame_coords(e.position())
        if self.rect_start and self.rect_now:
            self.save_btn.setEnabled(True)

    def crop_rect(self):
        if not self.rect_start or not self.rect_now:
            return None
        x1, y1 = self.rect_start
        x2, y2 = self.rect_now
        x, y = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1), abs(y2 - y1)
        if w < 8 or h < 8:
            return None
        return (x, y, w, h)

    def cropped_image(self):
        r = self.crop_rect()
        if r is None or self.frame is None:
            return None
        return self.ctx.icon_db.crop_from_frame(self.frame, r)


class VisionEnginePage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("Page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("Vision Engine")
        title.setObjectName("SectionTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.status_dot = StatusDot("on")
        head.addWidget(self.status_dot)
        self.status_lbl = QLabel("READY")
        self.status_lbl.setStyleSheet(f"color: {theme.TEXT_2}; font-size: 10px;")
        head.addWidget(self.status_lbl)
        outer.addLayout(head)

        cols = QHBoxLayout()
        cols.setSpacing(12)
        outer.addLayout(cols, 1)

        # --- reference database table ---
        ref_card = Card("Reference Icon Database")
        tools = QHBoxLayout()
        add_cap = GlowButton("CAPTURE FROM SCREEN")
        add_cap.clicked.connect(self._capture_reference)
        add_file = GlowButton("IMPORT FILE…")
        add_file.clicked.connect(self._import_reference)
        remove = GlowButton("REMOVE", "danger")
        remove.clicked.connect(self._remove_reference)
        scan = GlowButton("RESCAN FOLDER")
        scan.clicked.connect(self._rescan)
        for b in (add_cap, add_file, remove, scan):
            tools.addWidget(b)
        tools.addStretch(1)
        ref_card.body().addLayout(tools)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Item", "Category", "Tier", "Reference"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 110)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        ref_card.add(self.table)
        cols.addWidget(ref_card, 5)

        # --- console column ---
        right = QVBoxLayout()
        right.setSpacing(12)
        console = Card("Detection Console")
        self.log = QListWidget()
        self.log.setMinimumHeight(180)
        console.add(self.log)
        right.addWidget(console, 2)

        hist = Card("Screenshot History")
        strip = QHBoxLayout()
        self.frames = []
        for _ in range(3):
            lbl = QLabel("—")
            lbl.setFixedSize(120, 76)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"""
                background: {theme.BG_ELEVATED}; color: {theme.TEXT_DIM};
                border: 1px solid {theme.BORDER}; border-radius: 6px; font-size: 9px;
            """)
            strip.addWidget(lbl)
            self.frames.append(lbl)
        strip.addStretch(1)
        hist.body().addLayout(strip)
        right.addWidget(hist, 1)
        right_wrap = QWidget()
        right_wrap.setLayout(right)
        cols.addWidget(right_wrap, 3)

        ctx.bus.activity.connect(self._on_activity)
        ctx.bus.build_detected.connect(self._on_build)
        self._fill_table()

    # ------------------------------------------------------------------ table
    def _fill_table(self) -> None:
        status = self.ctx.icon_db.status(self.ctx.catalog)
        rows = list(status.values())
        self.table.setRowCount(len(rows))
        ready = 0
        for i, entry in enumerate(rows):
            item = entry["item"]
            self.table.setItem(i, 0, QTableWidgetItem(item.name))
            self.table.setItem(i, 1, QTableWidgetItem(item.category))
            self.table.setItem(i, 2, QTableWidgetItem(item.tier))
            if entry["ready"]:
                ready += 1
                cell = QTableWidgetItem("● READY")
                cell.setForeground(Qt.green)
            else:
                cell = QTableWidgetItem("○ no reference")
                cell.setForeground(Qt.gray)
            self.table.setItem(i, 3, cell)
        self.status_lbl.setText(f"READY · {ready}/{len(rows)} references")

    def _rescan(self) -> None:
        counts = self.ctx.icon_db.reload(self.ctx.catalog)
        self._fill_table()
        self.ctx.bus.activity.emit("vision", f"Icon folder rescan: {sum(counts.values())} refs")

    def _selected_item(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No selection", "Select an item row first.")
            return None
        return list(self.ctx.icon_db.status(self.ctx.catalog).values())[row]["item"]

    def _save_reference(self, item, image) -> None:
        if image is None:
            QMessageBox.warning(self, "Empty crop", "Crop an icon first.")
            return
        ok = self.ctx.icon_db.set_reference(item.id, item.category, item.name, image,
                                            source="captured")
        if ok:
            self._fill_table()
            self.ctx.bus.activity.emit("vision", f"Reference saved: {item.name}")

    def _capture_reference(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        dlg = RegionPickerDialog(self.ctx, self)
        if dlg.exec():
            self._save_reference(item, dlg.cropped_image())

    def _import_reference(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, f"Reference icon for {item.name}", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        import cv2
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            QMessageBox.warning(self, "Invalid image", "Could not read that image.")
            return
        self._save_reference(item, img)

    def _remove_reference(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        if self.ctx.icon_db.remove_reference(item.id, item.category):
            self._fill_table()
            self.ctx.bus.activity.emit("vision", f"Reference removed: {item.name}")

    # ------------------------------------------------------------------ console
    def _on_activity(self, tag: str, msg: str) -> None:
        if tag in ("vision", "db", "system"):
            self.log.insertItem(0, QListWidgetItem(
                f"[{time.strftime('%H:%M:%S')}] {tag}: {msg}"))
            while self.log.count() > 80:
                self.log.takeItem(self.log.count() - 1)

    def _on_build(self, payload: dict) -> None:
        frame = self.ctx.pipeline.last_frame
        if frame is not None:
            payload_cv = self.ctx.pipeline.last_payload or {"detections": [], "threshold": 0.7}
            annotated = self.ctx.pipeline.draw_detections(frame, payload_cv)
            pm = frame_to_pixmap(annotated)
            # slide history frames
            for i in range(len(self.frames) - 1, 0, -1):
                self.frames[i].setPixmap(self.frames[i - 1].pixmap() or QPixmap())
            self.frames[0].setPixmap(pm.scaled(self.frames[0].size(), Qt.KeepAspectRatio,
                                               Qt.SmoothTransformation))
            self.frames[0].setText("")
