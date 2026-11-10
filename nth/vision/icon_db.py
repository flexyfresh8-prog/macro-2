"""Reference icon database.

Reference images live in ``assets/icons/<category>/<item_id>.png`` so they can
be added or replaced at any time — including while the app is running — without
touching application code.  The Vision Engine can also capture references
straight from a live screenshot.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

from nth.vision.matcher import Reference, flatten_alpha

CATEGORY_DIRS = {"fruit": "fruits", "sword": "swords", "style": "styles"}


class IconDatabase:
    def __init__(self, assets_dir: Optional[Path] = None):
        from nth.settings.manager import assets_dir as default_assets
        self.root = Path(assets_dir) if assets_dir else default_assets() / "icons"
        self._lock = threading.RLock()
        self._cache: Dict[str, Reference] = {}
        self._mtimes: Dict[Path, float] = {}
        self.reload()

    # -- paths ---------------------------------------------------------------
    def category_dir(self, category: str) -> Path:
        d = self.root / CATEGORY_DIRS.get(category, category)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def reference_path(self, item_id: str, category: str) -> Path:
        return self.category_dir(category) / f"{item_id}.png"

    # -- loading ---------------------------------------------------------------
    def reload(self, catalog=None) -> Dict[str, int]:
        """Scan the icons folders; hot-reload files changed on disk."""
        with self._lock:
            counts = {"fruit": 0, "sword": 0, "style": 0}
            by_id = {}
            if catalog is not None:
                by_id = {i.id: i for i in catalog.all()}
            for category, dirname in CATEGORY_DIRS.items():
                d = self.root / dirname
                if not d.exists():
                    counts[category] = 0
                    continue
                n = 0
                for f in sorted(d.glob("*.png")) + sorted(d.glob("*.jpg")):
                    mtime = f.stat().st_mtime
                    if self._mtimes.get(f) == mtime and f.stem in self._cache:
                        n += 1
                        continue
                    img = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
                    if img is None:
                        continue
                    meta = by_id.get(f.stem)
                    self._cache[f.stem] = Reference(
                        item_id=f.stem,
                        category=category,
                        name=meta.name if meta else f.stem.replace("-", " ").title(),
                        image=flatten_alpha(img),
                        source=str(f),
                    )
                    self._mtimes[f] = mtime
                    n += 1
                counts[category] = n
            return counts

    # -- queries ------------------------------------------------------------------
    def has_reference(self, item_id: str) -> bool:
        with self._lock:
            return item_id in self._cache

    def get(self, item_id: str) -> Optional[Reference]:
        with self._lock:
            return self._cache.get(item_id)

    def all_references(self, categories: Optional[List[str]] = None) -> List[Reference]:
        with self._lock:
            return [r for r in self._cache.values()
                    if categories is None or r.category in categories]

    def status(self, catalog) -> Dict[str, Dict[str, object]]:
        """Per-item reference status for the Vision Engine page."""
        out: Dict[str, Dict[str, object]] = {}
        with self._lock:
            for item in catalog.all():
                ref = self._cache.get(item.id)
                out[item.id] = {
                    "item": item,
                    "ready": ref is not None,
                    "source": ref.source if ref else "",
                }
        return out

    # -- mutation ---------------------------------------------------------------
    def set_reference(self, item_id: str, category: str, name: str,
                      image_bgr: np.ndarray, source: str = "captured") -> bool:
        """Add or replace a reference icon (persists to disk + cache)."""
        if image_bgr is None or image_bgr.size == 0:
            return False
        path = self.reference_path(item_id, category)
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), image_bgr)
        with self._lock:
            self._cache[item_id] = Reference(item_id, category, name,
                                             flatten_alpha(image_bgr), source=str(path))
            self._mtimes[path] = time.time()
        return True

    def remove_reference(self, item_id: str, category: str) -> bool:
        path = self.reference_path(item_id, category)
        removed = False
        if path.exists():
            path.unlink()
            removed = True
        with self._lock:
            self._cache.pop(item_id, None)
            self._mtimes.pop(path, None)
        return removed

    def crop_from_frame(self, frame_bgr: np.ndarray,
                        rect: tuple) -> Optional[np.ndarray]:
        """Crop a reference from a captured frame. rect = (x, y, w, h)."""
        x, y, w, h = rect
        h_f, w_f = frame_bgr.shape[:2]
        x, y = max(0, x), max(0, y)
        w, h = min(w, w_f - x), min(h, h_f - y)
        if w <= 4 or h <= 4:
            return None
        return frame_bgr[y:y + h, x:x + w].copy()
