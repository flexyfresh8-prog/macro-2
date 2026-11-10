"""NTH main window — frameless dark shell with sidebar navigation.

Implements the premium chrome: custom title bar, edge resizing, animated
page transitions, sliding nav indicator and live engine status pill.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QMainWindow, QPushButton, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget)

from nth import APP_NAME, WINDOW_TITLE, __version__
from nth.core.app_context import AppContext
from nth.ui import theme
from nth.ui.widgets import GlowButton, StatusDot, make_icon_pixmap

PAGES = [
    ("dashboard", "Dashboard", "dashboard"),
    ("find_build", "Find Build", "crosshair"),
    ("macro_studio", "Macro Studio", "macro"),
    ("move_library", "Move Library", "library"),
    ("vision_engine", "Vision Engine", "eye"),
    ("settings", "Settings", "settings"),
]


class TitleBar(QFrame):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.win = window
        self.setFixedHeight(44)
        self.setObjectName("TitleBar")
        self.setStyleSheet(f"""
            QFrame#TitleBar {{ background: {theme.BG_PANEL};
                               border-bottom: 1px solid {theme.BORDER}; }}
            QLabel {{ background: transparent; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 8, 0)
        lay.setSpacing(10)

        logo = QLabel("N")
        logo.setFixedSize(26, 26)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(f"""
            background: {theme.BG_ELEVATED}; color: {theme.ACCENT};
            border: 1px solid {theme.BORDER_BRIGHT}; border-radius: 6px;
            font-weight: 700; font-size: 13px;
        """)
        lay.addWidget(logo)

        title = QLabel(APP_NAME)
        f = QFont()
        f.setWeight(QFont.DemiBold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 2.2)
        title.setFont(f)
        lay.addWidget(title)
        sub = QLabel("BLOX FRUITS AUTOMATION SUITE")
        sf = QFont()
        sf.setPointSizeF(7.2)
        sf.setLetterSpacing(QFont.AbsoluteSpacing, 1.4)
        sub.setFont(sf)
        sub.setStyleSheet(f"color: {theme.TEXT_DIM};")
        lay.addWidget(sub)
        lay.addStretch(1)

        self.status_dot = StatusDot("run")
        self.status_label = QLabel("ENGINE IDLE")
        self.status_label.setStyleSheet(f"color: {theme.TEXT_2}; font-size: 10px;")
        lay.addWidget(self.status_dot)
        lay.addWidget(self.status_label)
        lay.addSpacing(12)

        for glyph, cb in (("—", self.win.showMinimized), ("▢", self.win.toggle_max),
                          ("✕", self.win.close)):
            b = QPushButton(glyph)
            b.setFixedSize(34, 26)
            b.setCursor(Qt.PointingHandCursor)
            danger = glyph == "✕"
            b.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: 1px solid transparent;
                               border-radius: 6px; color: {theme.TEXT_2}; font-size: 11px; }}
                QPushButton:hover {{ background: {theme.BG_HOVER};
                                    color: {'#FF4D4D' if danger else theme.TEXT}; }}
            """)
            b.clicked.connect(cb)
            lay.addWidget(b)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.win.windowHandle().startSystemMove()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.win.toggle_max()


class Sidebar(QFrame):
    page_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setFixedWidth(216)
        self.setObjectName("Sidebar")
        self.setStyleSheet(f"""
            QFrame#Sidebar {{ background: {theme.BG_PANEL};
                              border-right: 1px solid {theme.BORDER}; }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 16, 12, 12)
        lay.setSpacing(4)

        cap = spaced_title("NAVIGATION")
        lay.addWidget(cap)
        lay.addSpacing(6)

        self._buttons = {}
        self._indicator = QFrame()
        self._indicator.setFixedSize(3, 26)
        self._indicator.setStyleSheet(f"background: {theme.ACCENT}; border-radius: 2px;")

        for key, label, icon in PAGES:
            btn = QPushButton(f"  {label}")
            btn.setObjectName("Nav")
            btn.setIcon(make_icon_pixmap(icon))
            btn.setIconSize(QSize_(20, 20))
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(36)
            btn.clicked.connect(lambda _=False, k=key: self.select(k))
            lay.addWidget(btn)
            self._buttons[key] = btn

        lay.addStretch(1)
        engine_box = QFrame()
        engine_box.setObjectName("Card")
        engine_box.setStyleSheet(f"""
            QFrame#Card {{ background: {theme.BG_ELEVATED};
                           border: 1px solid {theme.BORDER}; border-radius: 10px; }}
        """)
        e_lay = QVBoxLayout(engine_box)
        e_lay.setContentsMargins(12, 10, 12, 10)
        e_lay.setSpacing(6)
        row = QHBoxLayout()
        self.engine_dot = StatusDot("run", 8)
        self.engine_label = QLabel("ENGINE READY")
        self.engine_label.setStyleSheet(f"color: {theme.TEXT_2}; font-size: 10px;")
        row.addWidget(self.engine_dot)
        row.addWidget(self.engine_label)
        row.addStretch(1)
        e_lay.addLayout(row)
        ver = QLabel(f"v{__version__} · PySide6")
        ver.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 9px;")
        e_lay.addWidget(ver)
        lay.addWidget(engine_box)

    def select(self, key: str) -> None:
        for k, b in self._buttons.items():
            b.setChecked(k == key)
        self.page_selected.emit(key)

    def set_engine_state(self, state: str) -> None:
        self.engine_dot.set_state(state)
        self.engine_label.setText({"run": "ENGINE RUNNING", "on": "ENGINE READY",
                                   "err": "ENGINE ERROR", "off": "ENGINE IDLE",
                                   "warn": "ATTENTION"}.get(state, state.upper()))


def spaced_title(text: str) -> QLabel:
    lbl = QLabel(text)
    f = QFont()
    f.setPointSizeF(7.4)
    f.setLetterSpacing(QFont.AbsoluteSpacing, 1.8)
    f.setWeight(QFont.DemiBold)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {theme.TEXT_DIM};")
    return lbl


def QSize_(w, h):
    from PySide6.QtCore import QSize
    return QSize(w, h)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setMinimumSize(980, 640)
        size = ctx.settings.get("ui.window_size", [1180, 720])
        self.resize(int(size[0]), int(size[1]))
        self.setProperty("glow_intensity", ctx.settings.get("ui.glow_intensity", 60))

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.title_bar = TitleBar(self)
        v.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        v.addLayout(body, 1)

        self.sidebar = Sidebar()
        self.sidebar.page_selected.connect(self._switch_page)
        body.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("PageHost")
        body.addWidget(self.stack, 1)

        self._pages = {}
        self._build_pages()
        self.sidebar.select("dashboard")

        self.bus = ctx.bus
        self.bus.status.connect(self._on_status)
        self._edge_timer = QTimer(self)
        self._edge_timer.timeout.connect(self._poll_roblox)
        self._edge_timer.start(4000)
        QTimer.singleShot(400, self._poll_roblox)

    # ------------------------------------------------------------- pages
    def _build_pages(self):
        from nth.ui.pages.dashboard import DashboardPage
        from nth.ui.pages.find_build import FindBuildPage
        from nth.ui.pages.macro_studio import MacroStudioPage
        from nth.ui.pages.move_library import MoveLibraryPage
        from nth.ui.pages.settings_page import SettingsPage
        from nth.ui.pages.vision_engine import VisionEnginePage

        for key, cls in (("dashboard", DashboardPage), ("find_build", FindBuildPage),
                         ("macro_studio", MacroStudioPage), ("move_library", MoveLibraryPage),
                         ("vision_engine", VisionEnginePage), ("settings", SettingsPage)):
            page = cls(self.ctx)
            self.stack.addWidget(page)
            self._pages[key] = page

    def _switch_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        if self.ctx.settings.get("ui.animations", True):
            self._animate_to(page)
        else:
            self.stack.setCurrentWidget(page)

    def _animate_to(self, page: QWidget) -> None:
        self.stack.setCurrentWidget(page)
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _cleanup():
            if page.graphicsEffect() is effect:
                page.setGraphicsEffect(None)
        anim.finished.connect(_cleanup)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _on_status(self, key: str, value: str) -> None:
        if key == "roblox":
            self.sidebar.set_engine_state("on" if value == "detected" else "off")

    def _poll_roblox(self) -> None:
        if self.ctx.settings.get("window.auto_detect", True):
            self.ctx.poll_roblox()

    # ------------------------------------------------------------- window mgmt
    def toggle_max(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def resizeEvent(self, e):
        self._update_cursor_shape(e)
        super().resizeEvent(e)

    def _update_cursor_shape(self, e):
        pass

    def mouseMoveEvent(self, e):
        if not self.isMaximized():
            edges = self._edges_at(e.position().toPoint())
            if edges == Qt.LeftEdge | Qt.TopEdge or edges == Qt.RightEdge | Qt.BottomEdge:
                self.setCursor(Qt.SizeFDiagCursor)
            elif edges == Qt.RightEdge | Qt.TopEdge or edges == Qt.LeftEdge | Qt.BottomEdge:
                self.setCursor(Qt.SizeBDiagCursor)
            elif edges in (Qt.LeftEdge, Qt.RightEdge):
                self.setCursor(Qt.SizeHorCursor)
            elif edges in (Qt.TopEdge, Qt.BottomEdge):
                self.setCursor(Qt.SizeVerCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.isMaximized():
            edges = self._edges_at(e.position().toPoint())
            if edges:
                self.windowHandle().startSystemResize(edges)
                return
        super().mousePressEvent(e)

    def _edges_at(self, pos) -> Qt.Edges:
        m = 6
        edges = Qt.Edges()
        if pos.x() <= m:
            edges |= Qt.LeftEdge
        if pos.x() >= self.width() - m:
            edges |= Qt.RightEdge
        if pos.y() <= m:
            edges |= Qt.TopEdge
        if pos.y() >= self.height() - m:
            edges |= Qt.BottomEdge
        return edges

    def closeEvent(self, e):
        size = [self.width(), self.height()]
        self.ctx.settings.set("ui.window_size", size)
        self.ctx.shutdown()
        super().closeEvent(e)
