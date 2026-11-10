"""Stage-3 verification: catalog integrity + macro model + engine dry-run."""

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nth.items.catalog import Catalog                      # noqa: E402
from nth.macros.actions import Action, Macro               # noqa: E402
from nth.macros.engine import MacroEngine, IDLE, RUNNING   # noqa: E402
from nth.macros.recorder import MouseRecorder               # noqa: E402
from nth.core.input_backend import DryRunInputBackend       # noqa: E402
from nth.settings.manager import Settings                   # noqa: E402


def test_catalog():
    tmp = Path(tempfile.mkdtemp(prefix="nth_cat_"))
    cat = Catalog(tmp)
    counts = cat.counts()
    assert counts == {"fruit": 42, "sword": 38, "style": 13, "total": 93}, counts
    ids = [i.id for i in cat.all()]
    assert len(ids) == len(set(ids)), "duplicate ids"
    # spot-check specific items from the spec
    for name in ("Kitsune", "Cursed Dual Katana", "T-Rex", "Pole (1st Form)",
                 "Sanguine Art", "Fishing Trophy", "Advanced Combat"):
        item = cat.find_by_name(name)
        assert item is not None, name
    assert cat.find_by_name("CDK").id == "cursed-dual-katana"
    # persistence round-trip
    item = cat.get("dough")
    item.hotbar_key = "3"
    cat.add_or_update(item)
    cat2 = Catalog(tmp)
    assert cat2.get("dough").hotbar_key == "3"
    print("catalog OK:", counts)


def test_macro_model():
    m = Macro(name="Combo Demo", actions=[
        Action("select_item", item_id="dough", item_name="Dough", key="2"),
        Action("key", key="Z", delay_after=0.5),
        Action("select_item", item_id="cursed-dual-katana", item_name="CDK", key="3"),
        Action("key", key="X", delay_after=0.3),
        Action("select_item", item_id="godhuman", item_name="Godhuman", key="4"),
        Action("key", key="Z", delay_after=1.0),
    ])
    d = m.to_dict()
    m2 = Macro.from_dict(d)
    assert len(m2.actions) == 6 and m2.actions[1].key == "Z"
    assert m2.actions[0].describe() == "Select Dough [2]"
    # unknown type guarded, bad path data tolerated
    m2.actions[0].type = "nonsense"
    a = Action.from_dict(m2.actions[0].to_dict())
    assert a.type == "key"
    print("macro model OK, est duration:", m.est_duration(), "s")


def test_engine_dryrun():
    settings = Settings(Path(tempfile.mkdtemp(prefix="nth_eng_")) / "s.json")
    settings.set("macro.humanize", False)
    backend = DryRunInputBackend()
    states = []
    eng = MacroEngine(backend, settings, activity=lambda t, m: None)
    eng.on_state = lambda s, i: states.append((s, i))
    macro = Macro(name="test", actions=[
        Action("select_item", item_name="Dough", key="2"),
        Action("key", key="Z", delay_after=0.05),
        Action("delay", duration=0.05),
        Action("click", x=640, y=360),
        Action("disabled", enabled=False, key="Q"),
    ])
    assert eng.start_macro(macro)
    deadline = time.monotonic() + 5
    while eng.state != IDLE and time.monotonic() < deadline:
        time.sleep(0.02)
    assert eng.state == IDLE, "engine did not finish"
    log = [msg for _, msg in backend.journal]
    assert "tap 2" in " | ".join(log), log
    assert "tap Z" in " | ".join(log)
    assert "click left" in " | ".join(log)
    assert not any("tap Q" in m for m in log), "disabled action ran!"
    assert states[0][0] == RUNNING and states[-1][0] == IDLE
    print("engine dry-run OK:", len(log), "events")


def test_recorder_math():
    pts = [(0, 0, 0.0), (5, 0, 0.1), (10, 0, 0.2), (10, 1, 0.3), (10, 2, 0.4)]
    compressed = MouseRecorder.compress(pts)
    assert len(compressed) <= 4, compressed
    paused = MouseRecorder.insert_pause(pts, 1, 2.0)
    assert abs(paused[3][2] - pts[2][2] - 2.0) < 1e-6      # points after pause shift
    assert paused[2][2] - paused[1][2] >= 2.0              # pause gap exists
    faster = MouseRecorder.scale_speed(pts, 2.0)
    assert abs(faster[-1][2] - pts[-1][2] / 2) < 1e-6
    print("recorder math OK")


if __name__ == "__main__":
    test_catalog()
    test_macro_model()
    test_engine_dryrun()
    test_recorder_math()
    print("CORE TESTS: PASS")
