#!/usr/bin/env python3
"""NTH — Blox Fruits Automation Suite.

Entry point: DPI-aware Qt bootstrap, theme application, main window.
Run:  python main.py          (repo)
      NTH.exe                 (frozen build)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Keep the app directory on sys.path when launched from anywhere.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    if sys.platform == "win32":
        import ctypes
        try:                                   # crisp text on HiDPI displays
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    from nth import WINDOW_TITLE, __version__
    from nth.core.app_context import AppContext
    from nth.settings.manager import assets_dir
    from nth.ui import theme
    from nth.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("NTH")
    app.setApplicationDisplayName(WINDOW_TITLE)
    app.setApplicationVersion(__version__)
    theme.apply_theme(app, glow_intensity=60)

    icon_path = assets_dir() / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    ctx = AppContext()
    window = MainWindow(ctx)
    if ctx.settings.get("ui.start_minimized", False):
        window.showMinimized()
    else:
        window.show()

    code = app.exec()
    sys.exit(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
