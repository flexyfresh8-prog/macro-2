"""NTH item catalog — complete, expandable item database.

The catalog ships as Python defaults and is materialised to ``data/catalog.json``
on first run.  Users can edit the JSON (add items, rename, tune ability keys,
add aliases) without touching application code.  Reference *icons* live in
``assets/icons/<category>/<item_id>.png`` and are managed via the Vision Engine.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

CATALOG_VERSION = 1

# ---------------------------------------------------------------------------
# Default ability keys per category (users can override per item in the JSON).
# NOTE: not every item has every key in game — that is exactly why these are
# editable per item rather than hard-coded assumptions.
# ---------------------------------------------------------------------------
DEFAULT_KEYS = {
    "fruit": ["Z", "X", "C", "V", "F"],
    "sword": ["Z", "X", "C"],
    "style": ["Z", "X", "C", "V"],
}

# (name, tier, aliases)  per category, in the exact order supplied by the spec.
_FRUITS = {
    "mythical": [
        ("Kitsune", []), ("Dragon", []), ("Tiger", []), ("Gas", []),
        ("Yeti", []), ("Dough", ["Dough King"]), ("T-Rex", ["Trex", "T Rex"]),
        ("Spirit", []), ("Venom", []), ("Control", []), ("Shadow", []),
        ("Mammoth", []), ("Gravity", []),
    ],
    "legendary": [
        ("Buddha", ["Buddha Fruit"]), ("Portal", ["Door"]), ("Lightning", []),
        ("Pain", []), ("Blizzard", []), ("Phoenix", ["Phoenix Fruit"]),
        ("Sound", []), ("Spider", ["String"]), ("Love", []), ("Quake", []),
    ],
    "rare": [
        ("Rumble", []), ("Ghost", ["Revive"]), ("Magma", []), ("Barrier", []),
        ("Rubber", []), ("Light", []), ("Diamond", []), ("Dark", []),
        ("Sand", []), ("Ice", []),
    ],
    "common": [
        ("Falcon", []), ("Flame", []), ("Spike", []), ("Smoke", []),
        ("Bomb", []), ("Spring", []), ("Chop", []), ("Spin", []),
        ("Rocket", ["Kilo"]),
    ],
}

_SWORDS = {
    "endgame": [
        ("Cursed Dual Katana", ["CDK"]),
        ("True Triple Katana", ["TTK"]),
        ("Dark Blade", ["Yoru"]),
        ("Tushita", []), ("Yama", []), ("Shark Anchor", []),
        ("Spikey Trident", []), ("Fox Lamp", []), ("Buddy Sword", []),
    ],
    "epic": [
        ("Canvander", []), ("Dragon Trident", []), ("Dark Dagger", []),
        ("Koko", ["Saddi"]), ("Soul Cane", []), ("Dragonheart", []),
        ("Triple Dark Blade", []),
    ],
    "rare": [
        ("Bisento", []), ("Pole (1st Form", []), ("Pole (2nd Form", []),
        ("Saber", []), ("Shizu", []), ("Saishi", []), ("Trident", []),
        ("Twin Hooks", []), ("Shark Saw", []), ("Cutlass", []),
        ("Gravity Cane", []),
    ],
    "common": [
        ("Katana", []), ("Dual Katana", []), ("Triple Katana", []),
        ("Dog Blade", []), ("Iron Mace", []), ("Long Sword", []),
        ("Warden Sword", []), ("Dual-Headed Blade", []), ("Flail", []),
        ("Pipe", []), ("Fishing Trophy", []),
    ],
}

_STYLES = {
    "first_sea": [
        ("Combat", ["Basic Combat"]), ("Dark Step", []), ("Water Kung Fu", []),
        ("Electric", ["Electro"]), ("Dragon Breath", []),
    ],
    "second_sea": [
        ("Superhuman", []), ("Death Step", []), ("Sharkman Karate", []),
        ("Electric Claw", []), ("Dragon Talon", []),
    ],
    "master": [
        ("Godhuman", []), ("Sanguine Art", []), ("Advanced Combat", []),
    ],
}


@dataclass
class Item:
    id: str
    name: str
    category: str            # fruit | sword | style
    tier: str                # mythical | legendary | rare | common | endgame | epic | first_sea | second_sea | master
    aliases: List[str] = field(default_factory=list)
    keys: List[str] = field(default_factory=list)
    hotbar_key: str = ""     # hotbar slot key used by "Select Item" actions
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Item":
        return Item(
            id=d["id"], name=d["name"], category=d["category"], tier=d.get("tier", ""),
            aliases=list(d.get("aliases", [])), keys=list(d.get("keys", [])),
            hotbar_key=d.get("hotbar_key", ""), notes=d.get("notes", ""),
        )


def _slug(name: str) -> str:
    s = name.lower().strip()
    s = s.replace("&", "and")
    out = []
    for ch in s:
        out.append(ch if (ch.isalnum() or ch in "-_ ") else "")
    s = "".join(out).replace(" ", "-")
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def _build_defaults() -> List[Item]:
    items: List[Item] = []

    def add(group: dict, category: str, key_label: str = ""):
        for tier, entries in group.items():
            for name, aliases in entries:
                # Pole entries carry "(1st Form" style suffix — rebuild display names
                full_name = name
                if name.startswith("Pole ("):
                    full_name = name + ")"
                items.append(Item(
                    id=_slug(full_name), name=full_name, category=category, tier=tier,
                    aliases=list(aliases), keys=list(DEFAULT_KEYS[category]),
                ))

    add(_FRUITS, "fruit")
    add(_SWORDS, "sword")
    add(_STYLES, "style")
    return items


class Catalog:
    """Thread-safe catalog backed by ``data/catalog.json``."""

    def __init__(self, data_dir: Path):
        self._lock = threading.RLock()
        self.path = data_dir / "catalog.json"
        self._items: List[Item] = []
        self.reload()

    # -- persistence --------------------------------------------------------
    def reload(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    self._items = [Item.from_dict(d) for d in raw.get("items", [])]
                    return
                except Exception:
                    pass  # corrupt file -> fall back to defaults
            self._items = _build_defaults()
            self.save()

    def save(self) -> None:
        with self._lock:
            payload = {"version": CATALOG_VERSION, "items": [i.to_dict() for i in self._items]}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # -- queries ------------------------------------------------------------
    def all(self) -> List[Item]:
        with self._lock:
            return list(self._items)

    def by_category(self, category: str) -> List[Item]:
        with self._lock:
            return [i for i in self._items if i.category == category]

    def get(self, item_id: str) -> Optional[Item]:
        with self._lock:
            for i in self._items:
                if i.id == item_id:
                    return i
            return None

    def find_by_name(self, name: str) -> Optional[Item]:
        q = name.strip().lower()
        with self._lock:
            for i in self._items:
                if i.name.lower() == q or i.id == q or q in (a.lower() for a in i.aliases):
                    return i
            # substring fallback
            for i in self._items:
                if q and (q in i.name.lower() or any(q in a.lower() for a in i.aliases)):
                    return i
        return None

    def search(self, query: str, category: str = "", tier: str = "") -> List[Item]:
        q = query.strip().lower()
        with self._lock:
            res = []
            for i in self._items:
                if category and i.category != category:
                    continue
                if tier and i.tier != tier:
                    continue
                if q:
                    hay = " ".join([i.name, i.id] + i.aliases).lower()
                    if q not in hay:
                        continue
                res.append(i)
            return res

    def add_or_update(self, item: Item) -> None:
        with self._lock:
            for idx, existing in enumerate(self._items):
                if existing.id == item.id:
                    self._items[idx] = item
                    self.save()
                    return
            self._items.append(item)
            self.save()

    def remove(self, item_id: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [i for i in self._items if i.id != item_id]
            changed = len(self._items) != before
            if changed:
                self.save()
            return changed

    # -- stats --------------------------------------------------------------
    def counts(self) -> Dict[str, int]:
        out = {"fruit": 0, "sword": 0, "style": 0}
        for i in self._items:
            if i.category in out:
                out[i.category] += 1
        out["total"] = len(self._items)
        return out
