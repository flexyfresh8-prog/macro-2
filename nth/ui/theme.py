"""NTH visual theme — monochromatic dark design system.

Shared tokens + QSS builder used by every page so the desktop UI and the
HTML preview stay visually identical.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------- tokens
BG_BASE = "#0A0A0C"
BG_PANEL = "#101014"
BG_ELEVATED = "#16161B"
BG_HOVER = "#1C1C22"
BG_ACTIVE = "#202027"
BORDER = "#24242B"
BORDER_BRIGHT = "#3A3A44"
TEXT = "#ECECEF"
TEXT_2 = "#9A9AA5"
TEXT_DIM = "#5A5A64"
ACCENT = "#F5F5F7"
GLOW = "rgba(245,245,247,0.12)"
GLOW_STRONG = "rgba(245,245,247,0.22)"
OK = "#3DD68C"
WARN = "#F5A623"
ERR = "#FF4D4D"
FONT_FAMILY = '"Segoe UI", "Inter", "DejaVu Sans", sans-serif'
MONO_FAMILY = '"Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono", monospace'


def build_qss(glow_intensity: int = 60) -> str:
    g = max(0, min(100, glow_intensity)) / 100.0
    shadow = f"rgba(245,245,247,{0.10 * g:.3f})"
    return f"""
* {{
    font-family: {FONT_FAMILY};
    font-size: 12px;
    color: {TEXT};
    selection-background-color: {BG_ACTIVE};
    selection-color: {ACCENT};
}}
QMainWindow, QWidget#Root {{ background-color: {BG_BASE}; }}
QWidget#PageHost, QWidget#Page {{ background-color: {BG_BASE}; }}

/* ---------- panels / cards ---------- */
QFrame#Card, QFrame#Panel {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#Card[hover="true"] {{ border: 1px solid {BORDER_BRIGHT}; }}
QLabel#CardTitle {{
    color: {TEXT_2}; font-size: 10px; font-weight: 600;
}}
QLabel#BigValue {{ color: {TEXT}; font-size: 20px; font-weight: 600; }}
QLabel#Micro {{ color: {TEXT_DIM}; font-size: 10px; }}
QLabel#SectionTitle {{
    color: {TEXT}; font-size: 13px; font-weight: 600;
}}
QLabel#Hint {{ color: {TEXT_DIM}; font-size: 11px; }}
QLabel#Mono {{ font-family: {MONO_FAMILY}; }}

/* ---------- buttons ---------- */
QPushButton {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 14px;
    color: {TEXT};
}}
QPushButton:hover {{ background-color: {BG_HOVER}; border-color: {BORDER_BRIGHT}; }}
QPushButton:pressed {{ background-color: {BG_ACTIVE}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; border-color: {BORDER}; background: {BG_PANEL}; }}
QPushButton#Primary {{
    background-color: {ACCENT}; color: {BG_BASE};
    border: 1px solid {ACCENT}; font-weight: 600;
}}
QPushButton#Primary:hover {{
    background-color: #FFFFFF;
}}
QPushButton#Ghost {{ background: transparent; }}
QPushButton#Danger:hover {{ border-color: {ERR}; color: {ERR}; }}
QPushButton#Nav {{
    background: transparent; border: none; border-radius: 8px;
    padding: 9px 12px; text-align: left; color: {TEXT_2};
}}
QPushButton#Nav:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
QPushButton#Nav:checked {{ background: {BG_ELEVATED}; color: {ACCENT}; }}

/* ---------- inputs ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 9px;
    color: {TEXT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {BORDER_BRIGHT};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {BG_ELEVATED}; border: 1px solid {BORDER_BRIGHT};
    border-radius: 8px; padding: 4px; color: {TEXT};
    outline: none;
}}
QComboBox QAbstractItemView::item {{ padding: 6px 8px; border-radius: 5px; }}
QComboBox QAbstractItemView::item:selected {{ background: {BG_ACTIVE}; }}

/* ---------- sliders ---------- */
QSlider::groove:horizontal {{
    height: 4px; background: {BG_ELEVATED}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {TEXT_2}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -6px 0;
    background: {ACCENT}; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: #FFFFFF; }}

/* ---------- scrollbars ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_BRIGHT}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {BORDER_BRIGHT}; border-radius: 4px; min-width: 30px;
}}

/* ---------- tables / lists ---------- */
QTableWidget, QTableView {{
    background: {BG_PANEL}; border: 1px solid {BORDER};
    border-radius: 10px; gridline-color: {BORDER};
    alternate-background-color: {BG_ELEVATED};
}}
QHeaderView::section {{
    background: {BG_ELEVATED}; color: {TEXT_2};
    border: none; border-bottom: 1px solid {BORDER};
    padding: 7px 8px; font-size: 10px;
}}
QListWidget {{
    background: {BG_PANEL}; border: 1px solid {BORDER};
    border-radius: 10px; padding: 4px; outline: none;
}}
QListWidget::item {{ padding: 6px 8px; border-radius: 6px; margin: 1px 2px; }}
QListWidget::item:hover {{ background: {BG_HOVER}; }}
QListWidget::item:selected {{ background: {BG_ACTIVE}; color: {TEXT}; }}

/* ---------- misc ---------- */
QToolTip {{
    background: {BG_ELEVATED}; color: {TEXT};
    border: 1px solid {BORDER_BRIGHT}; border-radius: 6px; padding: 6px;
}}
QStatusBar {{ background: {BG_PANEL}; color: {TEXT_2}; border-top: 1px solid {BORDER}; }}
QSplitter::handle {{ background: {BORDER}; width: 1px; }}
"""


def apply_theme(app: QApplication, glow_intensity: int = 60) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss(glow_intensity))
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG_BASE))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(BG_PANEL))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(BG_ELEVATED))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(BG_ACTIVE))
    palette.setColor(QPalette.HighlightedText, QColor(ACCENT))
    app.setPalette(palette)
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)
