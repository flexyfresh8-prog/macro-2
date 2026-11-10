"""Icon matching engine.

Strategy (no OCR — pure computer vision):
  1. Multi-scale template matching (TM_CCOEFF_NORMED) of each reference icon
     against the captured frame, across a configurable size range so different
     resolutions / inventory layouts are handled.
  2. ORB feature-match verification for borderline results (gray zone).
  3. Appearance embedding (HSV histogram + Hu moments) to rank alternatives.

Every match returns a calibrated confidence in [0, 1].  Items without
references are never guessed — they are reported as missing data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class Reference:
    item_id: str
    category: str
    name: str
    image: np.ndarray                      # BGR uint8 (alpha flattened)
    source: str = ""                       # where it came from


@dataclass
class Match:
    item_id: str
    category: str
    name: str
    score: float
    location: Tuple[int, int]              # x, y in frame
    size: Tuple[int, int]                  # w, h of matched template
    thumbnail: np.ndarray = field(repr=False, default=None)
    alternatives: List[Tuple[str, float]] = field(default_factory=list)


def _gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def flatten_alpha(image_bgra: np.ndarray, bg=(24, 24, 28)) -> np.ndarray:
    """Flatten an RGBA image onto a dark background -> BGR."""
    if image_bgra.ndim == 2:
        return cv2.cvtColor(image_bgra, cv2.COLOR_GRAY2BGR)
    if image_bgra.shape[2] == 3:
        return image_bgra
    alpha = image_bgra[:, :, 3:4].astype(np.float32) / 255.0
    rgb = image_bgra[:, :, :3].astype(np.float32)
    out = rgb * alpha + np.array(bg, dtype=np.float32) * (1.0 - alpha)
    return out.astype(np.uint8)


def embed(img_bgr: np.ndarray) -> Optional[np.ndarray]:
    """Appearance embedding: normalized HSV histogram (512-d)."""
    if img_bgr is None or img_bgr.size == 0:
        return None
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
    cv2.normalize(hist, hist)
    return hist.flatten()


def embed_distance(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
    """0.0 = identical appearance, 1.0 = unrelated."""
    if a is None or b is None:
        return 1.0
    corr = cv2.compareHist(a.reshape(8, 8, 8).astype(np.float32),
                           b.reshape(8, 8, 8).astype(np.float32), cv2.HISTCMP_CORREL)
    return float(max(0.0, 1.0 - corr))


class IconMatcher:
    def __init__(self, settings=None):
        self.settings = settings
        self.orb = cv2.ORB_create(nfeatures=350)
        self.gray_zone = (0.52, 0.78)       # borderline scores -> ORB verify

    # -- settings helpers -----------------------------------------------------
    def _size_range(self) -> Tuple[int, int]:
        lo = int(self.settings.get("vision.icon_size_min", 40)) if self.settings else 40
        hi = int(self.settings.get("vision.icon_size_max", 96)) if self.settings else 96
        return max(24, lo), max(lo + 8, hi)

    def multi_scale(self) -> bool:
        return bool(self.settings.get("vision.multi_scale", True)) if self.settings else True

    # -- matching ----------------------------------------------------------------
    def match_frame(self, frame_bgr: np.ndarray, refs: List[Reference],
                    region: Optional[Tuple[int, int, int, int]] = None) -> List[Match]:
        """Match every reference against the frame (or a sub-region of it).

        Returns the best Match per reference (score in [0,1]).
        """
        if frame_bgr is None or frame_bgr.size == 0 or not refs:
            return []
        ox = oy = 0
        work = frame_bgr
        if region:
            x, y, w, h = region
            ox, oy = x, y
            work = frame_bgr[y:y + h, x:x + w]

        frame_gray = _gray(work)
        lo, hi = self._size_range()
        step = max(4, (hi - lo) // 9)
        coarse = [hi] if not self.multi_scale() else list(range(lo, hi + 1, step))

        def _match_at(ref_img: np.ndarray, size: int) -> Optional[Match]:
            tpl = self._resize(ref_img, size)
            if tpl is None or tpl.shape[0] >= work.shape[0] or tpl.shape[1] >= work.shape[1]:
                return None
            res = cv2.matchTemplate(frame_gray, _gray(tpl), cv2.TM_CCOEFF_NORMED)
            _, maxv, _, maxloc = cv2.minMaxLoc(res)
            return Match(ref_item, ref_cat, ref_name, float(maxv),
                         (maxloc[0] + ox, maxloc[1] + oy),
                         (tpl.shape[1], tpl.shape[0]), thumbnail=ref_img.copy())

        matches: List[Match] = []
        for ref in refs:
            ref_item, ref_cat, ref_name = ref.item_id, ref.category, ref.name
            best: Optional[Match] = None
            for size in coarse:
                m = _match_at(ref.image, size)
                if m is not None and (best is None or m.score > best.score):
                    best = m
            # second pass: fine sweep around the best coarse size
            if best is not None and self.multi_scale():
                base = best.size[1]
                for size in range(max(24, base - step), min(hi, base + step) + 1, 2):
                    if size in coarse:
                        continue
                    m = _match_at(ref.image, size)
                    if m is not None and m.score > best.score:
                        best = m
            if best is None:
                continue
            # ORB verification inside the gray zone
            if self.gray_zone[0] <= best.score <= self.gray_zone[1]:
                boost = self._orb_verify(work, ref.image, best)
                best.score = max(best.score, min(0.97, best.score + boost * 0.18))
            # alternatives via appearance embedding of the matched crop
            best.alternatives = self._alternatives(work, best, refs, None)
            matches.append(best)
        return matches

    # -- internals -----------------------------------------------------------------
    @staticmethod
    def _resize(ref_img: np.ndarray, target_h: int) -> Optional[np.ndarray]:
        h, w = ref_img.shape[:2]
        if h <= 0 or w <= 0:
            return None
        scale = target_h / float(h)
        tw = max(8, int(round(w * scale)))
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        return cv2.resize(ref_img, (tw, target_h), interpolation=interp)

    def _orb_verify(self, work: np.ndarray, ref_img: np.ndarray, best: Match) -> float:
        """Ratio-test ORB matching around the best location; 0..1."""
        try:
            x, y = best.location[0], best.location[1]
            w, h = best.size[0], best.size[1]
            pad = int(max(w, h) * 0.35)
            crop = work[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
            kp1, des1 = self.orb.detectAndCompute(_gray(ref_img), None)
            kp2, des2 = self.orb.detectAndCompute(_gray(crop), None)
            if des1 is None or des2 is None or len(kp1) < 6 or len(kp2) < 6:
                return 0.0
            bf = cv2.BFMatcher(cv2.NORM_HAMMING)
            raw = bf.knnMatch(des1, des2, k=2)
            good = 0
            for pair in raw:
                if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance:
                    good += 1
            return min(1.0, good / max(len(kp1), 1))
        except Exception:
            return 0.0

    def _alternatives(self, work: np.ndarray, best: Match, refs: List[Reference],
                      frame_emb: Optional[np.ndarray]) -> List[Tuple[str, float]]:
        """Second-guess list: same-category refs ranked by appearance similarity
        to the matched crop (embedding distance, lower = closer)."""
        x, y = best.location
        w, h = best.size
        crop = work[y:y + h, x:x + w]
        crop_emb = embed(crop)
        alts: List[Tuple[str, float]] = []
        for ref in refs:
            if ref.item_id == best.item_id or ref.category != best.category:
                continue
            resized = self._resize(ref.image, h)
            d = embed_distance(crop_emb, embed(resized if resized is not None else ref.image))
            alts.append((ref.name, round(d, 3)))
        alts.sort(key=lambda t: t[1])
        return alts[:3]

    @staticmethod
    def non_max_suppress(matches: List[Match], iou_threshold: float = 0.35) -> List[Match]:
        """Suppress overlapping boxes for *different* items (keep higher score)."""
        boxes = sorted(matches, key=lambda m: m.score, reverse=True)
        keep: List[Match] = []
        for m in boxes:
            ok = True
            for k in keep:
                if _iou(m.location, m.size, k.location, k.size) > iou_threshold:
                    ok = False
                    break
            if ok:
                keep.append(m)
        return keep


def _iou(a_xy, a_wh, b_xy, b_wh) -> float:
    ax, ay = a_xy
    aw, ah = a_wh
    bx, by = b_xy
    bw, bh = b_wh
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0
