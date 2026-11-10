"""Stage-4/5 verification: vision pipeline on synthetic game frames.

Builds a synthetic 'Roblox screenshot' with icon-like sprites, creates
reference icons from those sprites at a different scale, and verifies the
matcher finds the right items with sane confidence — proving the real CV
pipeline (multi-scale template match + NMS + build inference) works.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nth.items.catalog import Catalog          # noqa: E402
from nth.recognition.build_engine import BuildEngine  # noqa: E402
from nth.settings.manager import Settings      # noqa: E402
from nth.vision.icon_db import IconDatabase    # noqa: E402
from nth.vision.pipeline import VisionPipeline  # noqa: E402


def sprite_fruit(size=64):
    """Sphere-ish fruit glyph."""
    img = np.zeros((size, size, 3), np.uint8)
    cv2.circle(img, (size // 2, size // 2), size // 2 - 2, (60, 130, 220), -1)
    cv2.circle(img, (size // 2 - 6, size // 2 - 8), size // 6, (150, 200, 250), -1)
    cv2.circle(img, (size // 2, size // 2), size // 2 - 2, (250, 250, 250), 1)
    return img


def sprite_sword(size=64):
    img = np.zeros((size, size, 3), np.uint8)
    cv2.line(img, (size // 2, 4), (size // 2, size - 14), (230, 230, 235), 4)
    cv2.line(img, (size // 2 - 12, size - 10), (size // 2 + 12, size - 10), (200, 170, 90), 5)
    cv2.line(img, (size // 2, size - 10), (size // 2, size - 2), (200, 170, 90), 3)
    return img


def sprite_style(size=64):
    img = np.zeros((size, size, 3), np.uint8)
    cv2.rectangle(img, (14, 20), (50, 50), (90, 90, 235), -1)
    cv2.rectangle(img, (10, 26), (16, 44), (90, 90, 235), -1)
    cv2.rectangle(img, (14, 20), (50, 50), (250, 250, 250), 1)
    return img


def make_scene():
    """1280x720 dark scene with a hotbar strip holding 3 icons at odd scale."""
    scene = np.full((720, 1280, 3), (18, 16, 14), np.uint8)
    for i in range(0, 1280, 40):
        cv2.line(scene, (i, 0), (i, 720), (24, 22, 20), 1)
    strip_y = 640
    for idx, spr in enumerate([sprite_fruit(56), sprite_sword(56), sprite_style(56)]):
        x = 500 + idx * 100
        region = scene[strip_y:strip_y + 56, x:x + 56]
        scene[strip_y:strip_y + 56, x:x + 56] = cv2.addWeighted(region, 0.0, spr, 1.0, 0)
    return scene


def main() -> int:
    # Isolated fixture: settings/icons in a temp dir.
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="nth_vision_test_"))
    settings = Settings(tmp / "settings.json")
    settings.set("vision.scan_mode", "full")

    catalog = Catalog(tmp)                      # materializes catalog.json
    icon_db = IconDatabase(assets_dir=tmp / "assets")

    fruit, sword, style = catalog.by_category("fruit")[0], catalog.by_category("sword")[0], \
        catalog.by_category("style")[0]
    assert icon_db.set_reference(fruit.id, "fruit", fruit.name, sprite_fruit(64), "test")
    assert icon_db.set_reference(sword.id, "sword", sword.name, sprite_sword(64), "test")
    assert icon_db.set_reference(style.id, "style", style.name, sprite_style(64), "test")

    # A decoy reference that must NOT match the scene.
    decoy = catalog.by_category("fruit")[5]
    assert icon_db.set_reference(decoy.id, "fruit", decoy.name, sprite_style(64), "test")

    scene = make_scene()
    pipeline = VisionPipeline(settings, icon_db)
    payload = pipeline.detect(scene)
    result = BuildEngine(catalog, None, settings).infer(payload)

    print("status:", payload["status"], "| scan_ms:", payload["scan_ms"])
    for d in payload["detections"]:
        print(f"  {d['category']:5s} {d['name']:24s} conf={d['confidence']:.3f} "
              f"at {d['location']}")

    ok = True
    by_id = {d["item_id"]: d for d in payload["detections"]}
    for item, expect_sprite in ((fruit, sprite_fruit), (sword, sprite_sword),
                                (style, sprite_style)):
        det = by_id.get(item.id)
        if det is None or det["confidence"] < 0.85:
            print(f"FAIL: {item.name} detection weak/missing: {det}")
            ok = False
    decoy_det = by_id.get(decoy.id)
    if decoy_det and decoy_det["confidence"] > 0.6:
        print(f"FAIL: decoy matched too strongly ({decoy_det['confidence']:.2f})")
        ok = False

    b = result["build"]
    resolved = {k: v["name"] if v else None for k, v in b.items()}
    print("build:", resolved, "| overall:", result["overall_confidence"],
          "| rescan:", result["needs_rescan"])
    if not all([b["fruit"], b["sword"], b["style"]]):
        print("FAIL: build inference did not resolve all 3 categories")
        ok = False
    if result["needs_rescan"]:
        print("FAIL: needs_rescan should be False for a clean scene")
        ok = False

    # Unknown-icon honesty: empty reference DB must report no_references.
    empty_db = IconDatabase(assets_dir=tmp / "none")
    p2 = VisionPipeline(settings, empty_db).detect(scene)
    if p2["status"] != "no_references":
        print("FAIL: empty DB should return status no_references")
        ok = False

    print("VISION TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
