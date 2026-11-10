"""NTH application settings — persisted as JSON next to the executable."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict


def base_dir() -> Path:
    """Install/base directory: next to the frozen exe, else repo root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    d = base_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def assets_dir() -> Path:
    return base_dir() / "assets"


DEFAULTS: Dict[str, Any] = {
    # Window detection
    "window.title_contains": "Roblox",
    "window.auto_detect": True,
    "window.focus_before_capture": True,
    # Vision
    "vision.sensitivity": 72,            # 0-100 -> match threshold 0.90..0.55
    "vision.scan_mode": "hotbar",        # full | hotbar | custom
    "vision.custom_region": None,        # [x, y, w, h] relative to window client area
    "vision.multi_scale": True,
    "vision.icon_size_min": 40,
    "vision.icon_size_max": 96,
    "vision.capture_scale": 1.0,         # downscale captures for speed
    # Macro engine
    "macro.default_delay": 0.30,
    "macro.safety_delay": 0.10,          # humanized extra jitter
    "macro.humanize": True,
    "macro.loop": False,
    "macro.step_mode": False,
    # Mouse tracking
    "mouse.poll_rate": 60,               # Hz
    "mouse.trail_length": 400,
    "mouse.click_detect": True,
    # Color detection
    "color.tolerance": 24,               # per-channel RGB tolerance
    "color.interval": 150,               # ms between samples
    "color.consecutive": 3,              # consecutive diffs before trigger
    "color.cooldown": 1.5,               # seconds between triggers
    # Input
    "input.backend": "auto",             # auto | win32 | dryrun
    "input.key_hold": 0.045,
    # UI
    "ui.glow_intensity": 60,             # 0-100
    "ui.animations": True,
    "ui.cursor_glow": True,
    "ui.compact": False,
    "ui.start_minimized": False,
    "ui.window_size": [1180, 720],
    # GitHub
    "github.repo_name": "macro-2",
    "github.repo_private": True,
    "github.auto_push": False,
    # Database
    "db.keep_history": 500,
}


class Settings:
    """Thread-safe JSON-backed settings store with dotted keys."""

    def __init__(self, path: Path | None = None):
        self._lock = threading.RLock()
        self.path = path or (data_dir() / "settings.json")
        self._values: Dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    stored = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(stored, dict):
                        self._values.update(stored)
                except Exception:
                    pass  # keep defaults on corruption

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._values, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._values.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any, save: bool = True) -> None:
        with self._lock:
            self._values[key] = value
            if save:
                self.save()

    def as_dict(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._values)

    def reset_section(self, prefix: str) -> None:
        with self._lock:
            for k in list(self._values.keys()):
                if k.startswith(prefix + "."):
                    self._values[k] = DEFAULTS.get(k)
            self.save()

    # -- derived ------------------------------------------------------------
    def match_threshold(self) -> float:
        """Sensitivity slider (0-100) -> template-match threshold."""
        s = float(self.get("vision.sensitivity", 72))
        return round(0.90 - (s / 100.0) * 0.35, 3)  # 0.90 .. 0.55
