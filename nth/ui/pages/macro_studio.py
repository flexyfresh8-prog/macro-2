"""Macro Studio — drag-and-drop action timeline + live transport controls."""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFrame, QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from nth.core.app_context import AppContext
from nth.macros.actions import ACTION_TYPES, Action, Macro
from nth.macros.storage import MacroStorage, new_macro
from nth.ui import theme
from nth.ui.widgets import GlowButton, make_icon_pixmap, spaced_label

TYPE_LABELS = {
    "select_item": "Select Item", "key": "Key Press", "click": "Mouse Click",
    "mouse_path": "Mouse Path", "delay": "Delay", "repeat_block": "Repeat Block",
}
KEYS = ["", "Z", "X", "C", "V", "F", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
        "SPACE", "ENTER", "SHIFT", "CTRL"]


class Timeline(QListWidget):
    """Drag-reorderable action list synced to a Macro model."""

    order_changed = Signal()

    def __init__(self, page: "MacroStudioPage"):
        super().__init__()
        self.page = page
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(False)
        self.model().rowsMoved.connect(self._sync_order)

    def _sync_order(self, *args) -> None:
        macro = self.page.macro
        if macro is None:
            return
        new_order = []
        for i in range(self.count()):
            idx = self.item(i).data(Qt.UserRole)
            new_order.append(macro.actions[idx])
        macro.actions = new_order
        self.reindex()
        self.order_changed.emit()

    def reindex(self) -> None:
        for i in range(self.count()):
            item = self.item(i)
            item.setText(self.page.row_text(int(item.data(Qt.UserRole))))

    def dropEvent(self, e):
        super().dropEvent(e)
        self.order_changed.emit()


class MacroStudioPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.storage = MacroStorage()
        self.macro: Macro = new_macro("Combo Demo")
        self._build_sample()
        self.setObjectName("Page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("Macro Studio")
        title.setObjectName("SectionTitle")
        head.addWidget(title)
        head.addStretch(1)
        outer.addLayout(head)

        # transport bar
        transport = QFrame()
        transport.setObjectName("Panel")
        transport.setStyleSheet(f"""
            QFrame#Panel {{ background: {theme.BG_PANEL}; border: 1px solid {theme.BORDER};
                            border-radius: 10px; }}
        """)
        t_lay = QHBoxLayout(transport)
        t_lay.setContentsMargins(12, 8, 12, 8)
        t_lay.setSpacing(8)

        self.name_edit = self._name_edit()
        t_lay.addWidget(self.name_edit)
        t_lay.addSpacing(8)

        self.btn_play = self._transport_btn("PLAY", "play")
        self.btn_pause = self._transport_btn("PAUSE", "pause")
        self.btn_stop = self._transport_btn("STOP", "stop")
        self.btn_step = self._transport_btn("STEP", "step")
        self.btn_loop = self._transport_btn("LOOP", "loop", checkable=True)
        self.btn_loop.setChecked(bool(self.macro.loop))
        for b in (self.btn_play, self.btn_pause, self.btn_stop, self.btn_step, self.btn_loop):
            t_lay.addWidget(b)
        t_lay.addStretch(1)
        self.state_label = QLabel("IDLE")
        self.state_label.setStyleSheet(f"color: {theme.TEXT_2}; font-weight: 600;")
        t_lay.addWidget(self.state_label)
        self.est_label = QLabel("")
        self.est_label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px;")
        t_lay.addWidget(self.est_label)
        outer.addWidget(transport)

        # body: palette | timeline | config
        body = QHBoxLayout()
        body.setSpacing(12)
        outer.addLayout(body, 1)

        # --- palette ---
        palette = self._card("Actions")
        for atype in ACTION_TYPES:
            b = GlowButton(TYPE_LABELS[atype])
            b.clicked.connect(lambda _=False, t=atype: self.add_action(t))
            palette.add(b)
        palette.body().addSpacing(10)
        for label, cb in (("SAVE", self.save_macro), ("LOAD…", self.load_macro),
                          ("EXPORT…", self.export_macro), ("IMPORT…", self.import_macro)):
            b = GlowButton(label, "ghost")
            b.clicked.connect(cb)
            palette.add(b)
        body.addWidget(palette, 0)

        # --- timeline ---
        mid = QVBoxLayout()
        mid.setSpacing(8)
        tl_head = QHBoxLayout()
        tl_head.addWidget(spaced_label("Timeline"))
        tl_head.addStretch(1)
        self.dup_btn = GlowButton("DUPLICATE", "ghost")
        self.dup_btn.clicked.connect(self.duplicate_selected)
        self.del_btn = GlowButton("DELETE", "danger")
        self.del_btn.clicked.connect(self.delete_selected)
        tl_head.addWidget(self.dup_btn)
        tl_head.addWidget(self.del_btn)
        mid.addLayout(tl_head)
        self.timeline = Timeline(self)
        self.timeline.itemSelectionChanged.connect(self._on_select)
        mid.addWidget(self.timeline, 1)
        timeline_wrap = QWidget()
        timeline_wrap.setLayout(mid)
        body.addWidget(timeline_wrap, 3)

        # --- config panel ---
        cfg = self._card("Action Settings")
        self.cfg_stack = QVBoxLayout()
        cfg.body().addLayout(self.cfg_stack)
        self._build_config_panel()
        body.addWidget(cfg, 2)

        # engine wiring
        self.ctx.macro_engine.on_state = self._on_engine_state
        self.ctx.macro_engine.on_action = self._on_engine_action
        self._reload_timeline()
        self._refresh_est()

    # ------------------------------------------------------------ ui builders
    def _card(self, title: str) -> QWidget:
        from nth.ui.widgets import Card
        return Card(title)

    def _transport_btn(self, label: str, icon: str, checkable: bool = False) -> QPushButton:
        b = QPushButton(label)
        b.setIcon(make_icon_pixmap(icon))
        b.setCheckable(checkable)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(32)
        handler = {
            "PLAY": self.play, "PAUSE": self.ctx.macro_engine.toggle_pause,
            "STOP": self.stop, "STEP": self.step_once, "LOOP": None,
        }.get(label)
        if handler:
            b.clicked.connect(handler)
        return b

    def _name_edit(self) -> QWidget:
        from PySide6.QtWidgets import QLineEdit
        edit = QLineEdit(self.macro.name)
        edit.setMinimumWidth(200)
        edit.textChanged.connect(self._rename)
        return edit

    # ------------------------------------------------------------- sample data
    def _build_sample(self) -> None:
        fruit = self.ctx.catalog.find_by_name("Dough")
        sword = self.ctx.catalog.find_by_name("CDK")
        style = self.ctx.catalog.find_by_name("Godhuman")
        self.macro.actions = [
            Action("select_item", item_id=fruit.id, item_name=fruit.name, key="2"),
            Action("key", key="Z", delay_after=0.5),
            Action("select_item", item_id=sword.id, item_name=sword.name, key="3"),
            Action("key", key="X", delay_after=0.3),
            Action("select_item", item_id=style.id, item_name=style.name, key="4"),
            Action("key", key="Z", delay_after=1.0),
        ]

    # --------------------------------------------------------------- timeline
    def row_text(self, action_index: int) -> str:
        a = self.macro.actions[action_index]
        return f"{action_index + 1:02d}  ·  {a.describe()}"

    def _reload_timeline(self) -> None:
        self.timeline.blockSignals(True)
        self.timeline.clear()
        for i, a in enumerate(self.macro.actions):
            item = QListWidgetItem(self.row_text(i))
            item.setData(Qt.UserRole, i)
            self.timeline.addItem(item)
        self.timeline.blockSignals(False)
        self._refresh_est()

    def _refresh_est(self) -> None:
        self.est_label.setText(f"{len(self.macro.actions)} actions · ~{self.macro.est_duration()}s")

    def _rename(self, text: str) -> None:
        self.macro.name = text or "Untitled macro"

    # ------------------------------------------------------------ mutations
    def add_action(self, atype: str) -> None:
        a = Action(atype)
        if atype == "delay":
            a.duration = float(self.ctx.settings.get("macro.default_delay", 0.3))
        if atype == "key":
            a.key = "Z"
        if atype == "repeat_block":
            a.repeat = 2
        self.macro.actions.append(a)
        self._reload_timeline()
        self.timeline.setCurrentRow(len(self.macro.actions) - 1)

    def duplicate_selected(self) -> None:
        row = self.timeline.currentRow()
        if row < 0:
            return
        import copy
        dup = copy.deepcopy(self.macro.actions[row])
        self.macro.actions.insert(row + 1, dup)
        self._reload_timeline()
        self.timeline.setCurrentRow(row + 1)

    def delete_selected(self) -> None:
        row = self.timeline.currentRow()
        if row < 0:
            return
        del self.macro.actions[row]
        self._reload_timeline()
        self._refresh_est()

    # ------------------------------------------------------------ config panel
    def _build_config_panel(self) -> None:
        w = QWidget()
        form = QVBoxLayout(w)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        self.cfg_info = QLabel("Select a timeline action to configure it.")
        self.cfg_info.setObjectName("Hint")
        self.cfg_info.setWordWrap(True)
        form.addWidget(self.cfg_info)

        def row(label: str) -> QHBoxLayout:
            r = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {theme.TEXT_2}; min-width: 92px;")
            r.addWidget(lbl)
            return r

        self.cfg_type = QLabel("—")
        form.addLayout(row("Type")); form.addWidget(self.cfg_type)

        self.cfg_item = QComboBox()
        for it in self.ctx.catalog.all():
            self.cfg_item.addItem(f"{it.name} ({it.category})", it.id)
        form.addLayout(row("Item")); form.addWidget(self.cfg_item)

        self.cfg_key = QComboBox()
        self.cfg_key.setEditable(True)
        self.cfg_key.addItems(KEYS)
        form.addLayout(row("Key / Slot")); form.addWidget(self.cfg_key)

        self.cfg_delay_before = QDoubleSpinBox(); self.cfg_delay_before.setRange(0, 30)
        self.cfg_delay_before.setSingleStep(0.05); self.cfg_delay_before.setDecimals(2)
        self.cfg_delay_after = QDoubleSpinBox(); self.cfg_delay_after.setRange(0, 30)
        self.cfg_delay_after.setSingleStep(0.05); self.cfg_delay_after.setDecimals(2)
        form.addLayout(row("Delay before")); form.addWidget(self.cfg_delay_before)
        form.addLayout(row("Delay after")); form.addWidget(self.cfg_delay_after)

        self.cfg_hold = QDoubleSpinBox(); self.cfg_hold.setRange(0.01, 2.0)
        self.cfg_hold.setSingleStep(0.01); self.cfg_hold.setDecimals(3)
        form.addLayout(row("Hold (s)")); form.addWidget(self.cfg_hold)

        self.cfg_duration = QDoubleSpinBox(); self.cfg_duration.setRange(0, 60)
        self.cfg_duration.setSingleStep(0.1); self.cfg_duration.setDecimals(2)
        form.addLayout(row("Duration (s)")); form.addWidget(self.cfg_duration)

        self.cfg_repeat = QSpinBox(); self.cfg_repeat.setRange(1, 20)
        form.addLayout(row("Repeat")); form.addWidget(self.cfg_repeat)

        self.cfg_enabled = self._toggle()
        self.cfg_enabled.toggled.connect(self._config_changed)
        form.addLayout(row("Enabled")); form.addWidget(self.cfg_enabled)

        for widget, sig in ((self.cfg_item, self.cfg_item.currentIndexChanged),
                            (self.cfg_key, self.cfg_key.currentTextChanged),
                            (self.cfg_delay_before, self.cfg_delay_before.valueChanged),
                            (self.cfg_delay_after, self.cfg_delay_after.valueChanged),
                            (self.cfg_hold, self.cfg_hold.valueChanged),
                            (self.cfg_duration, self.cfg_duration.valueChanged),
                            (self.cfg_repeat, self.cfg_repeat.valueChanged)):
            sig.connect(self._config_changed)

        form.addStretch(1)
        self.cfg_stack.addWidget(w)

    def _toggle(self):
        from nth.ui.widgets import Toggle
        return Toggle(True)

    def _on_select(self) -> None:
        row = self.timeline.currentRow()
        if row < 0 or row >= len(self.macro.actions):
            return
        a = self.macro.actions[row]
        self.cfg_type.setText(TYPE_LABELS.get(a.type, a.type))
        self.cfg_info.setText(a.describe())
        idx = self.cfg_item.findData(a.item_id)
        self.cfg_item.blockSignals(True)
        self.cfg_item.setCurrentIndex(max(0, idx))
        self.cfg_item.blockSignals(False)
        self.cfg_key.blockSignals(True)
        self.cfg_key.setCurrentText(a.key)
        self.cfg_key.blockSignals(False)
        for w, val in ((self.cfg_delay_before, a.delay_before),
                       (self.cfg_delay_after, a.delay_after),
                       (self.cfg_hold, a.hold or 0.05),
                       (self.cfg_duration, a.duration),
                       (self.cfg_repeat, a.repeat)):
            w.blockSignals(True)
            w.setValue(val)
            w.blockSignals(False)
        self.cfg_enabled.blockSignals(True)
        self.cfg_enabled.setChecked(a.enabled)
        self.cfg_enabled.blockSignals(False)
        self._selected_row = row

    def _config_changed(self, *args) -> None:
        row = self.timeline.currentRow()
        if row < 0 or row >= len(self.macro.actions):
            return
        a = self.macro.actions[row]
        a.item_id = self.cfg_item.currentData() or ""
        item = self.ctx.catalog.get(a.item_id)
        a.item_name = item.name if item else ""
        a.key = self.cfg_key.currentText().strip().upper()
        a.delay_before = self.cfg_delay_before.value()
        a.delay_after = self.cfg_delay_after.value()
        a.hold = self.cfg_hold.value()
        a.duration = self.cfg_duration.value()
        a.repeat = self.cfg_repeat.value()
        a.enabled = self.cfg_enabled.isChecked()
        self.timeline.blockSignals(True)
        self.timeline.item(row).setText(self.row_text(row))
        self.timeline.item(row).setForeground(
            Qt.gray if not a.enabled else self.palette().text())
        self.timeline.blockSignals(False)
        self._refresh_est()

    # ------------------------------------------------------------- transport
    def play(self) -> None:
        self.btn_loop.setChecked(self.btn_loop.isChecked())
        self.macro.loop = self.btn_loop.isChecked()
        ok = self.ctx.macro_engine.start_macro(self.macro, loop=self.macro.loop)
        if not ok:
            self.state_label.setText("ALREADY RUNNING")

    def stop(self) -> None:
        self.ctx.macro_engine.stop()

    def step_once(self) -> None:
        eng = self.ctx.macro_engine
        if eng.state == "idle":
            eng.start_macro(self.macro, loop=False, step=True)
        else:
            eng.step()

    def _on_engine_state(self, state: str, index: int) -> None:
        self.state_label.setText(state.upper())
        color = {"running": theme.OK, "paused": theme.WARN,
                 "idle": theme.TEXT_2, "finished": theme.TEXT_2}.get(state, theme.TEXT_2)
        self.state_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        for i in range(self.timeline.count()):
            item = self.timeline.item(i)
            item.setSelected(i == index and state in ("running", "paused"))
            if i == index and state in ("running", "paused"):
                self.timeline.scrollToItem(item)

    def _on_engine_action(self, index: int, action: Action) -> None:
        self.ctx.bus.activity.emit("macro", f"Action {index + 1}: {action.describe()}")

    # -------------------------------------------------------------- persistence
    def save_macro(self) -> None:
        path = self.storage.save(self.macro)
        self.ctx.bus.activity.emit("macro", f"Saved '{self.macro.name}' → {path.name}")
        QMessageBox.information(self, "Macro saved", f"Saved to:\n{path}")

    def load_macro(self) -> None:
        macros = self.storage.list_macros()
        if not macros:
            QMessageBox.information(self, "No macros", "No saved macros found in"
                                    f" {self.storage.folder}")
            return
        names = [m["name"] for m in macros]
        name, ok = QInputDialog.getItem(self, "Load macro", "Macro:", names, 0, False)
        if not ok:
            return
        m = self.storage.load(name)
        if m:
            self.macro = m
            self.name_edit.blockSignals(True)
            self.name_edit.setText(m.name)
            self.name_edit.blockSignals(False)
            self.btn_loop.setChecked(m.loop)
            self._reload_timeline()

    def export_macro(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export macro", f"{self.macro.name}.json",
                                              "NTH Macro (*.json)")
        if path:
            self.storage.export_to(self.macro, path)
            self.ctx.bus.activity.emit("macro", f"Exported '{self.macro.name}'")

    def import_macro(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import macro", "",
                                              "NTH Macro (*.json)")
        if path:
            m = self.storage.import_from(path)
            if m:
                self.macro = m
                self.name_edit.blockSignals(True)
                self.name_edit.setText(m.name)
                self.name_edit.blockSignals(False)
                self._reload_timeline()
                self.ctx.bus.activity.emit("macro", f"Imported '{m.name}'")
            else:
                QMessageBox.warning(self, "Import failed", "That file is not a valid NTH macro.")
