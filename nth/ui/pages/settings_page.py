"""Settings — window, vision, macro, mouse, color, theme, startup, GitHub, DB."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QScrollArea, QSlider,
                               QSpinBox, QVBoxLayout, QWidget)

from nth.core.app_context import AppContext
from nth.integrations.github import GitHubClient, TokenStore
from nth.ui import theme
from nth.ui.widgets import Card, GlowButton, Toggle, spaced_label

try:
    import platform
    IS_WIN = sys.platform == "win32"
except Exception:
    IS_WIN = False


def _slider(value: int, lo: int, hi: int) -> QSlider:
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setValue(int(value))
    return s


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("Page")
        self.token_store = TokenStore()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(12)
        scroll.setWidget(host)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        title = QLabel("Settings")
        title.setObjectName("SectionTitle")
        v.addWidget(title)

        # ---------------------------------------------------------- window
        w = Card("Roblox Window Detection")
        row = QHBoxLayout()
        row.addWidget(spaced_label("Title contains"))
        self.win_title = QLineEdit(str(ctx.settings.get("window.title_contains", "Roblox")))
        self.win_title.editingFinished.connect(
            lambda: ctx.settings.set("window.title_contains", self.win_title.text()))
        row.addWidget(self.win_title, 1)
        refresh = GlowButton("SCAN WINDOWS")
        refresh.clicked.connect(self._refresh_windows)
        row.addWidget(refresh)
        w.body().addLayout(row)
        self.window_combo = QComboBox()
        w.add(self.window_combo)
        self.auto = Toggle(bool(ctx.settings.get("window.auto_detect", True)))
        auto_row = QHBoxLayout()
        auto_row.addWidget(spaced_label("Auto-detect (4s)"))
        auto_row.addStretch(1)
        auto_row.addWidget(self.auto)
        self.auto.toggled.connect(
            lambda on: ctx.settings.set("window.auto_detect", on))
        w.body().addLayout(auto_row)
        v.addWidget(w)

        # ---------------------------------------------------------- vision
        vis = Card("Vision & Recognition")
        s1_row = QHBoxLayout()
        s1_row.addWidget(spaced_label("Recognition sensitivity"))
        s1_row.addStretch(1)
        self.sens_val = QLabel(str(ctx.settings.get("vision.sensitivity", 72)))
        self.sens_val.setObjectName("Mono")
        s1_row.addWidget(self.sens_val)
        vis.body().addLayout(s1_row)
        self.sens = _slider(ctx.settings.get("vision.sensitivity", 72), 0, 100)
        self.sens.valueChanged.connect(
            lambda val: (ctx.settings.set("vision.sensitivity", int(val)),
                         self.sens_val.setText(str(val)),
                         self._hint(f"Match threshold → {ctx.settings.match_threshold():.2f}")))
        vis.add(self.sens)
        mode_row = QHBoxLayout()
        mode_row.addWidget(spaced_label("Scan region"))
        self.scan_mode = QComboBox()
        self.scan_mode.addItems(["full", "hotbar", "custom"])
        self.scan_mode.setCurrentText(str(ctx.settings.get("vision.scan_mode", "hotbar")))
        self.scan_mode.currentTextChanged.connect(
            lambda m: ctx.settings.set("vision.scan_mode", m))
        mode_row.addWidget(self.scan_mode)
        mode_row.addStretch(1)
        mode_row.addWidget(spaced_label("Capture scale"))
        self.cap_scale = QDoubleSpinBox()
        self.cap_scale.setRange(0.5, 2.0); self.cap_scale.setSingleStep(0.25)
        self.cap_scale.setValue(float(ctx.settings.get("vision.capture_scale", 1.0)))
        self.cap_scale.valueChanged.connect(
            lambda val: ctx.settings.set("vision.capture_scale", float(val)))
        mode_row.addWidget(self.cap_scale)
        vis.body().addLayout(mode_row)
        self.vis_hint = QLabel("")
        self.vis_hint.setObjectName("Micro")
        vis.add(self.vis_hint)
        v.addWidget(vis)

        # ---------------------------------------------------------- macro
        mac = Card("Macro Execution")
        d_row = QHBoxLayout()
        d_row.addWidget(spaced_label("Default delay (s)"))
        self.def_delay = QDoubleSpinBox()
        self.def_delay.setRange(0.0, 5.0); self.def_delay.setSingleStep(0.05)
        self.def_delay.setValue(float(ctx.settings.get("macro.default_delay", 0.3)))
        self.def_delay.valueChanged.connect(
            lambda val: ctx.settings.set("macro.default_delay", float(val)))
        d_row.addWidget(self.def_delay)
        d_row.addStretch(1)
        d_row.addWidget(spaced_label("Safety delay (s)"))
        self.safety = QDoubleSpinBox()
        self.safety.setRange(0.0, 1.0); self.safety.setSingleStep(0.05)
        self.safety.setValue(float(ctx.settings.get("macro.safety_delay", 0.10)))
        self.safety.valueChanged.connect(
            lambda val: ctx.settings.set("macro.safety_delay", float(val)))
        d_row.addWidget(self.safety)
        mac.body().addLayout(d_row)
        hum_row = QHBoxLayout()
        hum_row.addWidget(spaced_label("Humanized timing (jitter)"))
        hum_row.addStretch(1)
        self.hum = Toggle(bool(ctx.settings.get("macro.humanize", True)))
        self.hum.toggled.connect(lambda on: ctx.settings.set("macro.humanize", on))
        hum_row.addWidget(self.hum)
        mac.body().addLayout(hum_row)
        v.addWidget(mac)

        # ---------------------------------------------------------- mouse/color
        mc = Card("Mouse Tracking & Color Detection")
        m1 = QHBoxLayout()
        m1.addWidget(spaced_label("Poll rate (Hz)"))
        self.poll = QSpinBox(); self.poll.setRange(15, 240)
        self.poll.setValue(int(ctx.settings.get("mouse.poll_rate", 60)))
        self.poll.valueChanged.connect(lambda val: ctx.settings.set("mouse.poll_rate", int(val)))
        m1.addWidget(self.poll)
        m1.addStretch(1)
        m1.addWidget(spaced_label("Trail length"))
        self.trail = QSpinBox(); self.trail.setRange(50, 2000)
        self.trail.setValue(int(ctx.settings.get("mouse.trail_length", 400)))
        self.trail.valueChanged.connect(lambda val: ctx.settings.set("mouse.trail_length", int(val)))
        m1.addWidget(self.trail)
        mc.body().addLayout(m1)
        m2 = QHBoxLayout()
        m2.addWidget(spaced_label("Color tolerance (RGB)"))
        self.tol = QSpinBox(); self.tol.setRange(2, 120)
        self.tol.setValue(int(ctx.settings.get("color.tolerance", 24)))
        self.tol.valueChanged.connect(self._save_color)
        m2.addWidget(self.tol)
        m2.addStretch(1)
        m2.addWidget(spaced_label("Sample interval (ms)"))
        self.interval = QSpinBox(); self.interval.setRange(30, 2000)
        self.interval.setValue(int(ctx.settings.get("color.interval", 150)))
        self.interval.valueChanged.connect(self._save_color)
        m2.addWidget(self.interval)
        mc.body().addLayout(m2)
        self.color_state = QLabel("Color monitor: no region selected")
        self.color_state.setObjectName("Micro")
        mc.add(self.color_state)
        v.addWidget(mc)

        # ---------------------------------------------------------- theme
        themec = Card("Theme & Interface")
        g_row = QHBoxLayout()
        g_row.addWidget(spaced_label("Glow intensity"))
        g_row.addStretch(1)
        self.glow_val = QLabel(str(ctx.settings.get("ui.glow_intensity", 60)))
        self.glow_val.setObjectName("Mono")
        g_row.addWidget(self.glow_val)
        themec.body().addLayout(g_row)
        self.glow = _slider(ctx.settings.get("ui.glow_intensity", 60), 0, 100)
        self.glow.valueChanged.connect(
            lambda val: (ctx.settings.set("ui.glow_intensity", int(val)),
                         self.glow_val.setText(str(val)),
                         self.window().setProperty("glow_intensity", int(val))))
        themec.add(self.glow)
        t_row = QHBoxLayout()
        t_row.addWidget(spaced_label("Animations"))
        t_row.addStretch(1)
        self.anim = Toggle(bool(ctx.settings.get("ui.animations", True)))
        self.anim.toggled.connect(lambda on: ctx.settings.set("ui.animations", on))
        t_row.addWidget(self.anim)
        t_row.addSpacing(18)
        t_row.addWidget(spaced_label("Start minimized"))
        t_row.addStretch(1)
        self.mini = Toggle(bool(ctx.settings.get("ui.start_minimized", False)))
        self.mini.toggled.connect(lambda on: ctx.settings.set("ui.start_minimized", on))
        t_row.addWidget(self.mini)
        themec.body().addLayout(t_row)
        v.addWidget(themec)

        # ---------------------------------------------------------- github
        gh = Card("GitHub Integration")
        gh_row = QHBoxLayout()
        gh_row.addWidget(spaced_label("Repository name"))
        self.repo_edit = QLineEdit(str(ctx.settings.get("github.repo_name", "macro-2")))
        self.repo_edit.editingFinished.connect(
            lambda: ctx.settings.set("github.repo_name", self.repo_edit.text().strip()))
        gh_row.addWidget(self.repo_edit, 1)
        gh.body().addLayout(gh_row)
        self.gh_status = QLabel("Token not stored in this session.")
        self.gh_status.setObjectName("Micro")
        self.gh_status.setWordWrap(True)
        gh.add(self.gh_status)
        gh_btns = QHBoxLayout()
        save_tok = GlowButton("SAVE TOKEN (keyring)")
        save_tok.clicked.connect(self._save_token)
        clear_tok = GlowButton("CLEAR TOKEN", "danger")
        clear_tok.clicked.connect(self._clear_token)
        connect = GlowButton("CONNECT")
        connect.clicked.connect(self._connect)
        push = GlowButton("CREATE & PUSH REPO", "primary")
        push.clicked.connect(self._push_repo)
        for b in (save_tok, clear_tok, connect, push):
            gh_btns.addWidget(b)
        gh_btns.addStretch(1)
        gh.body().addLayout(gh_btns)
        v.addWidget(gh)

        # ---------------------------------------------------------- database
        db = Card("Database Management")
        self.db_info = QLabel("")
        self.db_info.setObjectName("Micro")
        db.add(self.db_info)
        db_btns = QHBoxLayout()
        open_folder = GlowButton("OPEN DATA FOLDER")
        backup = GlowButton("BACKUP")
        clear_hist = GlowButton("CLEAR BUILD HISTORY", "danger")
        open_folder.clicked.connect(self._open_folder)
        backup.clicked.connect(self._backup)
        clear_hist.clicked.connect(self._clear_history)
        for b in (open_folder, backup, clear_hist):
            db_btns.addWidget(b)
        db_btns.addStretch(1)
        db.body().addLayout(db_btns)
        v.addWidget(db)

        self._refresh_windows()
        self._update_db_info()
        self._update_gh_status()

    # ------------------------------------------------------------------ slots
    def _hint(self, text: str) -> None:
        self.vis_hint.setText(text)

    def _save_color(self, *_):
        self.ctx.settings.set("color.tolerance", self.tol.value())
        self.ctx.settings.set("color.interval", self.interval.value())
        reg = self.ctx.color_monitor.get_region()
        if reg:
            reg.tolerance = self.tol.value()
            reg.interval_ms = self.interval.value()
        self._update_color_state()

    def _update_color_state(self) -> None:
        reg = self.ctx.color_monitor.get_region()
        if reg is None:
            self.color_state.setText(
                "Color monitor: no region selected — pick one in the Macro Studio console"
                " or via settings file.")
        else:
            self.color_state.setText(
                f"Monitoring ({reg.x},{reg.y} {reg.w}×{reg.h}) · tolerance {reg.tolerance}"
                f" · trigger: {reg.trigger_kind} {reg.trigger_payload}".rstrip())

    def _refresh_windows(self) -> None:
        wins = self.ctx.windows.list_windows()
        self.window_combo.clear()
        for wdw in wins:
            self.window_combo.addItem(f"{wdw.title}  ({wdw.w}×{wdw.h})", wdw.handle)
        if not wins:
            self.window_combo.addItem("No matching windows found", 0)

    def _update_db_info(self) -> None:
        st = self.ctx.db.stats()
        self.db_info.setText(f"{st['builds']} saved builds · {st['moves']} moves ·"
                             f" {st['size'] / 1024:.0f} KB · {st['path']}")

    def _open_folder(self) -> None:
        from nth.settings.manager import data_dir
        path = str(data_dir())
        if sys.platform == "win32":
            subprocess.Popen(["explorer", path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _backup(self) -> None:
        src = self.ctx.db.path
        dst, _ = QFileDialog.getSaveFileName(self, "Backup database", "nth_backup.db",
                                             "SQLite (*.db)")
        if dst:
            import shutil
            shutil.copy2(src, dst)
            self.ctx.bus.activity.emit("db", f"Backup → {dst}")

    def _clear_history(self) -> None:
        if QMessageBox.question(self, "Confirm", "Delete ALL saved builds?") == QMessageBox.Yes:
            self.ctx.db.clear_builds()
            self._update_db_info()
            self.ctx.bus.activity.emit("db", "Build history cleared")

    # ------------------------------------------------------------------ github
    def _update_gh_status(self) -> None:
        token = self.token_store.load()
        backend = self.token_store.backend
        if token:
            self.gh_status.setText(f"✓ Token stored in OS keyring ({backend}) —"
                                   " never saved to files or the repository.")
            self.gh_status.setStyleSheet(f"color: {theme.OK};")
        elif backend != "keyring":
            self.gh_status.setText("⚠ No OS keyring backend available on this platform."
                                   " On Windows the Credential Manager is used.")
            self.gh_status.setStyleSheet(f"color: {theme.WARN};")
        else:
            self.gh_status.setText("Token not stored. Enter it below — it will be kept in"
                                   " the OS credential vault only.")
            self.gh_status.setStyleSheet(f"color: {theme.TEXT_DIM};")

    def _save_token(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        token, ok = QInputDialog.getText(
            self, "GitHub token", "Paste your Personal Access Token (fine-grained, repo scope):",
            QLineEdit.Password)
        if ok and token.strip():
            if self.token_store.save(token.strip()):
                self._update_gh_status()
                self.ctx.bus.activity.emit("github", "Token stored in OS keyring")
            else:
                QMessageBox.warning(self, "Failed", "No secure keyring backend available.")

    def _clear_token(self) -> None:
        self.token_store.clear()
        self._update_gh_status()
        self.ctx.bus.activity.emit("github", "Token cleared")

    def _client(self) -> GitHubClient:
        token = self.token_store.load() or ""
        return GitHubClient(token)

    def _connect(self) -> None:
        ok, msg = self._client().whoami()
        if ok:
            self.gh_status.setText(f"✓ Connected as @{msg} · repo '{self.repo_edit.text()}'"
                                   " target ready.")
            self.gh_status.setStyleSheet(f"color: {theme.OK};")
            self.ctx.bus.activity.emit("github", f"Connected as @{msg}")
        else:
            self.gh_status.setText(f"✕ Connection failed: {msg}")
            self.gh_status.setStyleSheet(f"color: {theme.ERR};")

    def _push_repo(self) -> None:
        client = self._client()
        ok, msg = client.whoami()
        if not ok:
            QMessageBox.warning(self, "GitHub", f"Not authenticated: {msg}\n"
                                "Store a token first (SAVE TOKEN).")
            return
        repo_name = self.repo_edit.text().strip() or "macro-2"
        repo_dir = Path(__file__).resolve().parents[3]
        self.gh_status.setText("Pushing…")
        ok, msg = client.push_repo(repo_dir, repo_name,
                                   "Update from NTH app (GitHub integration)")
        self.gh_status.setText(("✓ " if ok else "✕ ") + msg)
        self.gh_status.setStyleSheet(f"color: {theme.OK if ok else theme.ERR};")
        self.ctx.bus.activity.emit("github", msg)
