"""Headless UI smoke test: boots the full app offscreen, visits every page,
simulates interactions, and renders page screenshots for visual QA."""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/nth_ui")
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    from nth.ui import theme
    theme.apply_theme(app)

    from nth.core.app_context import AppContext
    from nth.ui.main_window import MainWindow

    ctx = AppContext()
    ctx.settings.set("ui.animations", False)   # offscreen test has no event loop
    win = MainWindow(ctx)
    win.resize(1180, 720)
    win.show()
    app.processEvents()

    # Give page constructors a beat, then capture each page.
    order = ["dashboard", "find_build", "macro_studio", "move_library",
             "vision_engine", "settings"]
    failures = []
    for key in order:
        win.sidebar.select(key)
        for _ in range(6):
            app.processEvents()
        png = out_dir / f"page_{key}.png"
        ok = win.grab().save(str(png))
        print(f"page {key}: rendered={ok} size={png.stat().st_size}")
        if not ok:
            failures.append(key)

    # exercise a few interactions
    app.processEvents()
    studio = win._pages["macro_studio"]
    n0 = len(studio.macro.actions)
    studio.add_action("delay")
    assert len(studio.macro.actions) == n0 + 1, "add_action failed"
    studio.timeline.setCurrentRow(0)
    studio.duplicate_selected()
    assert len(studio.macro.actions) == n0 + 2, "duplicate failed"
    studio.timeline.setCurrentRow(1)
    studio.delete_selected()
    print("macro studio interactions OK")

    lib = win._pages["move_library"]
    assert lib.grid.count() >= 8, "move library seeding failed"
    lib.search.setText("dough")
    app.processEvents()
    print("move library search OK, matches:", lib.grid.count())

    vis = win._pages["vision_engine"]
    vis._fill_table()
    print("vision table rows:", vis.table.rowCount())

    fb = win._pages["find_build"]
    fb._update_ref_hint()
    hist = fb.ctx.build_engine.history(5)
    print("build history entries:", len(hist))

    ctx.shutdown()
    print("UI SMOKE:", "PASS" if not failures else f"FAIL {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
