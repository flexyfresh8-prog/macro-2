"""Custom NTH widgets: cards, glowing buttons, status dots, toggles, meters."""

from __future__ import annotations

import time

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from nth.ui import theme


def spaced_label(text: str, object_name: str = "CardTitle") -> QLabel:
    """Micro-label with letterspacing (QSS lacks letter-spacing)."""
    lbl = QLabel(text.upper())
    lbl.setObjectName(object_name)
    font = QFont()
    font.setLetterSpacing(QFont.AbsoluteSpacing, 1.6)
    lbl.setFont(font)
    return lbl


class Card(QFrame):
    """Rounded panel with optional title row and subtle top highlight."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 14)
        self._layout.setSpacing(8)
        self.title_row = None
        if title:
            self.title_row = QHBoxLayout()
            self.title_row.addWidget(spaced_label(title))
            self.title_row.addStretch(1)
            self._layout.addLayout(self.title_row)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def enterEvent(self, e):
        self.setProperty("hover", "true")
        self.style().unpolish(self); self.style().polish(self)

    def leaveEvent(self, e):
        self.setProperty("hover", "false")
        self.style().unpolish(self); self.style().polish(self)


class GlowButton(QPushButton):
    """Button with an animated glow / border emphasis on hover."""

    def __init__(self, text: str, kind: str = "normal", parent=None):
        super().__init__(text, parent)
        kinds = {"primary": "Primary", "ghost": "Ghost", "danger": "Danger"}
        self.setObjectName(kinds.get(kind, "normal"))
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(30)
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(0)
        self._glow.setColor(QColor(245, 245, 247, 0))
        self._glow.setOffset(0, 0)
        self.setGraphicsEffect(self._glow)
        self._anim = QPropertyAnimation(self._glow, b"blurRadius", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def enterEvent(self, e):
        glow = 0
        try:
            glow = int(self.window().property("glow_intensity") or 60)
        except Exception:
            glow = 60
        self._anim.stop()
        self._anim.setStartValue(self._glow.blurRadius())
        self._anim.setEndValue(18 * glow / 100.0)
        self._glow.setColor(QColor(245, 245, 247, int(70 * glow / 100.0)))
        self._anim.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._glow.blurRadius())
        self._anim.setEndValue(0)
        self._anim.start()
        super().leaveEvent(e)


class StatusDot(QWidget):
    """Animated status indicator: steady / pulse / off / error."""

    SIZES = {"on": theme.OK, "off": theme.TEXT_DIM, "run": theme.ACCENT, "err": theme.ERR,
             "warn": theme.WARN}

    def __init__(self, state: str = "off", size: int = 9, parent=None):
        super().__init__(parent)
        self._state = state
        self._size = size
        self._phase = 0.0
        self.setFixedSize(size + 4, size + 4)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.set_state(state)

    def set_state(self, state: str) -> None:
        self._state = state
        if state == "run":
            self._timer.start(40)
        else:
            self._timer.stop()
            self.update()

    def _tick(self):
        self._phase = (self._phase + 0.05) % 1.0
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(self.SIZES.get(self._state, theme.TEXT_DIM))
        rect = QRectF(2, 2, self._size, self._size)
        if self._state == "run":
            halo = QColor(245, 245, 247, int(90 * (0.5 + 0.5 * abs(0.5 - self._phase) * 2)))
            p.setBrush(halo)
            p.setPen(Qt.NoPen)
            p.drawEllipse(rect.adjusted(-2.5, -2.5, 2.5, 2.5))
        elif self._state == "off":
            color = QColor(theme.BORDER_BRIGHT)
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(rect)
        p.end()


class Toggle(QCheckBox):
    """Animated monochrome switch."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._slide)
        self.setFixedSize(38, 20)

    def _slide(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def get_knob(self):
        return self._pos

    def set_knob(self, v):
        self._pos = v
        self.update()

    knob = Property(float, get_knob, set_knob)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(1, 3, self.width() - 2, self.height() - 6)
        p.setPen(QPen(QColor(theme.BORDER if not self.isChecked() else theme.BORDER_BRIGHT), 1))
        p.setBrush(QColor(theme.BG_ELEVATED if not self.isChecked() else theme.BG_ACTIVE))
        p.drawRoundedRect(track, 8, 8)
        r = 6.0
        x = 6 + self._pos * (self.width() - 12 - 2 * r) + r
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT if self.isChecked() else theme.TEXT_DIM))
        p.drawEllipse(QRectF(x - r, track.center().y() - r, r * 2, r * 2))
        p.end()


class Meter(QWidget):
    """Thin horizontal confidence/progress meter with animated fill."""

    def __init__(self, value: float = 0.0, height: int = 6, parent=None):
        super().__init__(parent)
        self._target = max(0.0, min(1.0, value))
        self._value = self._target
        self.setFixedHeight(height)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)

    def set_value(self, v: float) -> None:
        self._target = max(0.0, min(1.0, float(v)))
        if not self._timer.isActive():
            self._timer.start(16)

    def _step(self):
        self._value += (self._target - self._value) * 0.18
        if abs(self._target - self._value) < 0.004:
            self._value = self._target
            self._timer.stop()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.BG_ELEVATED))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 3, 3)
        w = self.width() * self._value
        if w > 1:
            p.setBrush(QColor(theme.TEXT_2 if self._value < 0.6 else theme.ACCENT))
            p.drawRoundedRect(QRectF(0, 0, w, self.height()), 3, 3)
        p.end()


class ConfidenceRing(QWidget):
    """Circular SVG-style confidence ring with animated sweep."""

    def __init__(self, value: float = 0.0, size: int = 64, parent=None):
        super().__init__(parent)
        self._value = max(0.0, min(1.0, value))
        self._shown = self._value
        self.setFixedSize(size, size)
        t = QTimer(self)
        t.timeout.connect(self._step)
        t.start(16)
        self._t = t

    def set_value(self, v: float):
        self._value = max(0.0, min(1.0, float(v)))

    def _step(self):
        self._shown += (self._value - self._shown) * 0.15
        if abs(self._value - self._shown) < 0.003:
            self._shown = self._value
        self.update()

    def paintEvent(self, e):
        s = min(self.width(), self.height())
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen_bg = QPen(QColor(theme.BORDER), 4)
        rect = QRectF(4, 4, s - 8, s - 8)
        p.setPen(pen_bg)
        p.drawArc(rect, 0, 360 * 16)
        pen = QPen(QColor(theme.ACCENT if self._value >= 0.6 else theme.TEXT_2), 4)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 90 * 16, -int(360 * 16 * self._shown))
        f = QFont()
        f.setPointSizeF(9.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.TEXT))
        p.drawText(rect, Qt.AlignCenter, f"{int(round(self._shown * 100))}%")
        p.end()


def make_icon_pixmap(kind: str, color: str = theme.TEXT_2, size: int = 22) -> QPixmap:
    """Draw simple monochrome line icons with QPainter (no external assets)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.5)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    r = QRectF(2, 2, size - 4, size - 4)
    k = kind
    if k == "dashboard":
        p.drawRect(r.adjusted(0, 0, -r.width() / 2 - 1, -r.height() / 2 - 1))
        p.drawRect(r.adjusted(r.width() / 2 + 1, 0, 0, -r.height() / 2 - 1))
        p.drawRect(r.adjusted(0, r.height() / 2 + 1, -r.width() / 2 - 1, 0))
        p.drawRect(r.adjusted(r.width() / 2 + 1, r.height() / 2 + 1, 0, 0))
    elif k == "crosshair":
        p.drawEllipse(r.adjusted(3, 3, -3, -3))
        p.drawLine(size // 2, 2, size // 2, 7)
        p.drawLine(size // 2, size - 7, size // 2, size - 2)
        p.drawLine(2, size // 2, 7, size // 2)
        p.drawLine(size - 7, size // 2, size - 2, size // 2)
        p.drawPoint(size / 2, size / 2)
    elif k == "macro":
        p.drawEllipse(r)
        path = QPainterPath()
        path.moveTo(size * 0.42, size * 0.32)
        path.lineTo(size * 0.68, size * 0.5)
        path.lineTo(size * 0.42, size * 0.68)
        path.closeSubpath()
        p.setBrush(c)
        p.drawPath(path)
    elif k == "library":
        for i, y in enumerate((4, 9, 14)):
            p.drawRect(QRectF(3, y, size - 6, 4))
    elif k == "eye":
        path = QPainterPath()
        path.moveTo(2, size / 2)
        path.quadTo(size / 2, size * 0.12, size - 2, size / 2)
        path.quadTo(size / 2, size * 0.88, 2, size / 2)
        p.drawPath(path)
        p.drawEllipse(r.adjusted(size * 0.28, size * 0.28, -size * 0.28, -size * 0.28))
    elif k == "settings":
        p.drawEllipse(r.adjusted(size * 0.3, size * 0.3, -size * 0.3, -size * 0.3))
        import math
        for a in range(0, 360, 45):
            rad = math.radians(a)
            x1 = size / 2 + math.cos(rad) * (size * 0.36)
            y1 = size / 2 + math.sin(rad) * (size * 0.36)
            x2 = size / 2 + math.cos(rad) * (size * 0.46)
            y2 = size / 2 + math.sin(rad) * (size * 0.46)
            p.drawLine(x1, y1, x2, y2)
    elif k == "play":
        path = QPainterPath()
        path.moveTo(size * 0.36, size * 0.24)
        path.lineTo(size * 0.74, size * 0.5)
        path.lineTo(size * 0.36, size * 0.76)
        path.closeSubpath()
        p.setBrush(c)
        p.drawPath(path)
    elif k == "pause":
        p.setBrush(c)
        p.drawRect(QRectF(size * 0.30, size * 0.24, 3.4, size * 0.52))
        p.drawRect(QRectF(size * 0.56, size * 0.24, 3.4, size * 0.52))
    elif k == "stop":
        p.setBrush(c)
        p.drawRect(QRectF(size * 0.28, size * 0.28, size * 0.44, size * 0.44))
    elif k == "loop":
        p.drawArc(r.adjusted(2, 2, -2, -2), 45 * 16, 270 * 16)
        path = QPainterPath()
        path.moveTo(size * 0.72, size * 0.20)
        path.lineTo(size * 0.72, size * 0.42)
        path.lineTo(size * 0.50, size * 0.30)
        path.closeSubpath()
        p.setBrush(c)
        p.drawPath(path)
    elif k == "step":
        p.setBrush(c)
        p.drawPolygon([QPointF_(size * 0.30, size * 0.26), QPointF_(size * 0.62, size * 0.5),
                       QPointF_(size * 0.30, size * 0.74)])
        p.drawRect(QRectF(size * 0.66, size * 0.26, 3.2, size * 0.48))
    p.end()
    return pm


def QPointF_(x, y):
    from PySide6.QtCore import QPointF
    return QPointF(x, y)
