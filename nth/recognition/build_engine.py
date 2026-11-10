"""Build inference: raw detections -> the most likely equipped build.

Rules (kept explicit and explainable):
  * One winner per category (fruit / sword / style) = highest-confidence
    detection at or above threshold; runner-ups become alternatives.
  * A category with no qualifying detection is reported as unresolved —
    never guessed.
  * If ANY category is unresolved or the winner is in the low-confidence
    band, the payload asks for another screenshot instead of pretending.
"""

from __future__ import annotations

import time
from typing import Dict, Optional

from nth.database.db import Database

CATEGORIES = ("fruit", "sword", "style")


class BuildEngine:
    def __init__(self, catalog, db: Database, settings):
        self.catalog = catalog
        self.db = db
        self.settings = settings

    def infer(self, payload: Dict) -> Dict:
        """payload = VisionPipeline.detect() output -> build conclusion."""
        threshold = float(payload.get("threshold", 0.7))
        by_cat = payload.get("by_category", {})
        build, alternatives, unresolved = {}, {}, []
        scores = {}

        for cat in CATEGORIES:
            cands = by_cat.get(cat, [])
            winner = cands[0] if cands else None
            if winner and winner["confidence"] >= threshold:
                build[cat] = {"id": winner["item_id"], "name": winner["name"],
                              "confidence": winner["confidence"]}
                scores[cat] = winner["confidence"]
                if len(cands) > 1:
                    alternatives[cat] = [
                        {"name": c["name"], "confidence": c["confidence"]}
                        for c in cands[1:3]
                    ]
            else:
                build[cat] = None
                unresolved.append(cat)
                if winner:
                    alternatives[cat] = [
                        {"name": c["name"], "confidence": c["confidence"]}
                        for c in cands[:3]
                    ]

        confs = [v["confidence"] for v in build.values() if v]
        overall = round(sum(confs) / len(confs), 4) if confs else 0.0
        low_band = threshold - 0.06
        borderline = [c for c, v in build.items()
                      if v and v["confidence"] < threshold + 0.08]
        needs_rescan = bool(unresolved) or (confs and min(confs) < low_band)
        if not confs:
            needs_rescan = True

        return {
            "ts": time.time(),
            "threshold": threshold,
            "build": build,
            "alternatives": alternatives,
            "unresolved": unresolved,
            "overall_confidence": overall,
            "needs_rescan": needs_rescan,
            "borderline": borderline,
            "status": payload.get("status"),
            "scan_ms": payload.get("scan_ms"),
            "detections": payload.get("detections", []),
            "summary": self._summary(build),
        }

    # ------------------------------------------------------------------ output
    @staticmethod
    def _summary(build: Dict) -> str:
        parts = []
        for cat, label in (("fruit", "Fruit"), ("sword", "Sword"), ("style", "Style")):
            v = build.get(cat)
            parts.append(v["name"] if v else "?")
        return " / ".join(parts)

    def save(self, result: Dict, screenshot_path: str = "", raw_payload: Optional[Dict] = None
             ) -> int:
        b = result.get("build", {})
        fruit = (b.get("fruit") or {}).get("name", "")
        fconf = (b.get("fruit") or {}).get("confidence", 0.0)
        sword = (b.get("sword") or {}).get("name", "")
        sconf = (b.get("sword") or {}).get("confidence", 0.0)
        style = (b.get("style") or {}).get("name", "")
        stconf = (b.get("style") or {}).get("confidence", 0.0)
        return self.db.save_build(fruit, fconf, sword, sconf, style, stconf,
                                  screenshot_path, raw_payload or {})

    def history(self, limit: int = 30):
        return self.db.recent_builds(limit)
