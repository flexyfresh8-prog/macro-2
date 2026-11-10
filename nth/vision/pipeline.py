"""Vision pipeline: capture -> scan-region selection -> matching -> payload.

The pipeline is deliberately UI-free and screen-free: callers hand it a BGR
frame, it hands back a plain dict payload.  That keeps it unit-testable and
lets the desktop app and future tools share it.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from nth.vision.icon_db import IconDatabase
from nth.vision.matcher import IconMatcher, Match


class VisionPipeline:
    def __init__(self, settings, icon_db: IconDatabase):
        self.settings = settings
        self.icon_db = icon_db
        self.matcher = IconMatcher(settings)
        self.last_scan_ms = 0.0
        self.last_frame: Optional[np.ndarray] = None

    # ---------------------------------------------------------------- regions
    def scan_region(self, frame_shape: Tuple[int, int]) -> Optional[Tuple[int, int, int, int]]:
        """Region of the frame to scan, from settings. None = full frame."""
        mode = str(self.settings.get("vision.scan_mode", "hotbar"))
        h, w = frame_shape[:2]
        if mode == "full":
            return None
        if mode == "hotbar":
            # Bottom-center strip where the Roblox hotbar lives.
            strip_h = int(h * 0.22)
            strip_w = int(w * 0.72)
            return ((w - strip_w) // 2, h - strip_h, strip_w, strip_h)
        region = self.settings.get("vision.custom_region", None)
        if region and len(region) == 4:
            x, y, rw, rh = [int(v) for v in region]
            rw = max(16, min(rw, w - x))
            rh = max(16, min(rh, h - y))
            return (max(0, x), max(0, y), rw, rh)
        return None

    # ------------------------------------------------------------------ detect
    def detect(self, frame_bgr: np.ndarray, threshold: Optional[float] = None) -> Dict:
        """Run the full detection over a frame. Returns a payload dict."""
        t0 = time.perf_counter()
        threshold = threshold if threshold is not None else self.settings.match_threshold()
        refs = self.icon_db.all_references()
        self.last_frame = frame_bgr
        self.last_payload = None

        if not refs:
            return self._payload(
                status="no_references", matches=[], threshold=threshold,
                ms=(time.perf_counter() - t0) * 1000.0, region=None,
            )

        region = self.scan_region(frame_bgr.shape)
        matches = self.matcher.match_frame(frame_bgr, refs, region)
        matches = IconMatcher.non_max_suppress(matches)
        self.last_scan_ms = (time.perf_counter() - t0) * 1000.0

        payload = self._payload(status="ok", matches=matches, threshold=threshold,
                                ms=self.last_scan_ms, region=region)
        self.last_payload = payload
        return payload

    # ----------------------------------------------------------------- payload
    def _payload(self, status: str, matches: List[Match], threshold: float, ms: float,
                 region) -> Dict:
        by_cat: Dict[str, List[Match]] = {"fruit": [], "sword": [], "style": []}
        for m in matches:
            if m.category in by_cat:
                by_cat[m.category].append(m)
        for cat in by_cat:
            by_cat[cat].sort(key=lambda m: m.score, reverse=True)

        detections = []
        for m in matches:
            detections.append({
                "item_id": m.item_id, "category": m.category, "name": m.name,
                "confidence": round(m.score, 4),
                "location": list(m.location), "size": list(m.size),
                "alternatives": [{"name": n, "distance": d} for n, d in m.alternatives],
            })

        return {
            "status": status,
            "ts": time.time(),
            "scan_ms": round(ms, 1),
            "threshold": threshold,
            "region": list(region) if region else None,
            "detections": detections,
            "by_category": {cat: [
                {"item_id": m.item_id, "name": m.name, "confidence": round(m.score, 4),
                 "location": list(m.location), "size": list(m.size)}
                for m in lst[:4]                       # top candidates per category
            ] for cat, lst in by_cat.items()},
            "frame": self.last_frame,
        }

    # -------------------------------------------------------------- utilities
    def draw_detections(self, frame_bgr: np.ndarray, payload: Dict) -> np.ndarray:
        """Annotate a frame with detection boxes + labels (for previews)."""
        out = frame_bgr.copy()
        for d in payload.get("detections", []):
            x, y = d["location"]
            w, h = d["size"]
            conf = d["confidence"]
            color = (245, 245, 245) if conf >= payload["threshold"] else (90, 90, 95)
            cv2.rectangle(out, (x, y), (x + w, y + h), color, 1)
            label = f'{d["name"]} {conf * 100:.0f}%'
            ty = max(12, y - 6)
            cv2.putText(out, label, (x, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (10, 10, 12), 3)
            cv2.putText(out, label, (x, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)
        return out
