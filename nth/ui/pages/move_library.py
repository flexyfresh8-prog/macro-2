"""Move Library — saved moves/combos with search, filters and favorites."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from nth.core.app_context import AppContext
from nth.macros.actions import Action
from nth.ui import theme
from nth.ui.widgets import Card, GlowButton, spaced_label


class MoveCard(QFrame):
    insert_requested = Signal(object)

    def __init__(self, move: dict, ctx: AppContext):
        super().__init__()
        self.move = move
        self.ctx = ctx
        self.setObjectName("Card")
        self.setFixedWidth(240)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)

        head = QHBoxLayout()
        name = QLabel(move["name"])
        name.setStyleSheet("font-weight: 600; font-size: 12px;")
        head.addWidget(name)
        head.addStretch(1)
        star = QPushButton("★" if move.get("favorite") else "☆")
        star.setFixedSize(26, 26)
        star.setCursor(Qt.PointingHandCursor)
        star.setStyleSheet(f"border: none; color: {theme.ACCENT}; font-size: 14px;")
        star.clicked.connect(self._toggle_fav)
        head.addWidget(star)
        lay.addLayout(head)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        for text in (move.get("category", "").upper(), f"KEY {move.get('key') or '—'}",
                     f"{move.get('delay', 0):g}s"):
            chip = QLabel(text)
            chip.setStyleSheet(f"""
                background: {theme.BG_ELEVATED}; color: {theme.TEXT_2};
                border: 1px solid {theme.BORDER}; border-radius: 5px;
                padding: 2px 7px; font-size: 9px;
            """)
            chip_row.addWidget(chip)
        chip_row.addStretch(1)
        lay.addLayout(chip_row)

        desc = move.get("description") or "No description."
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px;")
        lay.addWidget(d)
        lay.addStretch(1)

        foot = QHBoxLayout()
        item_lbl = QLabel(str(move.get("item") or ""))
        item_lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px;")
        foot.addWidget(item_lbl)
        foot.addStretch(1)
        insert = GlowButton("INSERT INTO MACRO", "ghost")
        insert.clicked.connect(lambda: self.insert_requested.emit(self.move))
        foot.addWidget(insert)
        lay.addLayout(foot)

    def _toggle_fav(self):
        new = 0 if self.move.get("favorite") else 1
        self.move["favorite"] = new
        self.ctx.db.update_move(self.move["id"], favorite=new)
        self.findChild(QPushButton, None)  # noop
        # refresh star glyph
        for btn in self.findChildren(QPushButton):
            if btn.text() in ("★", "☆"):
                btn.setText("★" if new else "☆")
        self.ctx.bus.activity.emit("library", f"{'★' if new else '☆'} {self.move['name']}")


class MoveLibraryPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("Page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("Move Library")
        title.setObjectName("SectionTitle")
        head.addWidget(title)
        head.addStretch(1)
        outer.addLayout(head)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search moves…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        controls.addWidget(self.search, 1)
        self.filter = QComboBox()
        self.filter.addItems(["All", "Fruit", "Sword", "Style", "Favorites"])
        self.filter.currentTextChanged.connect(self.refresh)
        controls.addWidget(self.filter)
        new_btn = GlowButton("NEW MOVE")
        new_btn.clicked.connect(self._new_move_dialog)
        controls.addWidget(new_btn)
        outer.addLayout(controls)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(12)
        scroll.setWidget(self.grid_host)
        outer.addWidget(scroll, 1)

        if not self.ctx.db.list_moves():
            self._seed_samples()
        self.refresh()

    # ----------------------------------------------------------------- data
    def _seed_samples(self) -> None:
        samples = [
            ("Dough Launch", "fruit", "dough", "Dough", "Z", 0.4, "Dough Z to close the gap."),
            ("Dough Burst", "fruit", "dough", "Dough", "X", 0.3, "Point-blank burst damage."),
            ("CDK Drain", "sword", "cursed-dual-katana", "CDK", "X", 0.5, "CDK life drain."),
            ("CDK Rift", "sword", "cursed-dual-katana", "CDK", "Z", 0.4, "Rift cleanup."),
            ("Godhuman Combo", "style", "godhuman", "Godhuman", "Z", 0.2, "Godhuman opener."),
            ("Sanguine Slam", "style", "sanguine-art", "Sanguine Art", "C", 0.4, "Sanguine C slam."),
            ("Tushita Cleave", "sword", "tushita", "Tushita", "C", 0.3, "Cursed cleave."),
            ("Dragon Flight", "fruit", "dragon", "Dragon", "F", 0.2, "Transform / flight toggle."),
        ]
        for name, cat, item_id, item_name, key, delay, desc in samples:
            self.ctx.db.add_move(name, cat, item_name, key, key, delay, "", desc)

    def refresh(self) -> None:
        q = self.search.text().strip()
        cat = {"All": "", "Fruit": "fruit", "Sword": "sword", "Style": "style"}.get(
            self.filter.currentText(), "")
        favs = self.filter.currentText() == "Favorites"
        moves = self.ctx.db.list_moves(q, cat, favs)
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        cols = 3
        for i, mv in enumerate(moves):
            card = MoveCard(mv, self.ctx)
            card.insert_requested.connect(self._insert_into_macro)
            self.grid.addWidget(card, i // cols, i % cols)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        if not moves:
            empty = QLabel("No moves match your search.")
            empty.setStyleSheet(f"color: {theme.TEXT_DIM};")
            self.grid.addWidget(empty, 0, 0)

    # ------------------------------------------------------------- actions
    def _insert_into_macro(self, move: dict) -> None:
        """Combine a saved move into the active macro timeline."""
        studio = None
        main = self.window()
        if hasattr(main, "_pages"):
            studio = main._pages.get("macro_studio")
        if studio is None:
            return
        item = self.ctx.catalog.find_by_name(str(move.get("item") or ""))
        if move.get("category") == "style" or not item:
            studio.macro.actions.append(Action("key", key=str(move.get("key") or "Z"),
                                               delay_after=float(move.get("delay", 0.3))))
        else:
            studio.macro.actions.append(Action(
                "select_item", item_id=item.id, item_name=item.name,
                key=str(move.get("key") or "")))
            studio.macro.actions.append(Action("key", key=str(move.get("key") or "Z"),
                                               delay_after=float(move.get("delay", 0.3))))
        studio._reload_timeline()
        self.ctx.bus.activity.emit("library", f"Inserted '{move['name']}' into macro")
        main._switch_page("macro_studio")

    def _new_move_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("New Move")
        form = QFormLayout(dlg)
        name = QLineEdit()
        cat = QComboBox(); cat.addItems(["fruit", "sword", "style"])
        item = QComboBox(); item.setEditable(True)
        for it in self.ctx.catalog.all():
            item.addItem(it.name)
        key = QComboBox(); key.setEditable(True)
        from nth.ui.pages.macro_studio import KEYS
        key.addItems(KEYS)
        delay = QDoubleSpinBox(); delay.setRange(0, 30); delay.setSingleStep(0.1)
        delay.setValue(0.3)
        desc = QLineEdit()
        form.addRow("Name", name)
        form.addRow("Category", cat)
        form.addRow("Item", item)
        form.addRow("Key", key)
        form.addRow("Delay (s)", delay)
        form.addRow("Description", desc)
        btns = QHBoxLayout()
        ok = QPushButton("SAVE MOVE"); ok.setObjectName("Primary")
        cancel = QPushButton("CANCEL")
        ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
        btns.addWidget(ok); btns.addWidget(cancel)
        form.addRow(btns)
        if dlg.exec() and name.text().strip():
            self.ctx.db.add_move(name.text().strip(), cat.currentText(),
                                 item.currentText(), key.currentText().upper(),
                                 key.currentText().upper(), delay.value(), "", desc.text())
            self.ctx.bus.activity.emit("library", f"Created move '{name.text().strip()}'")
            self.refresh()
