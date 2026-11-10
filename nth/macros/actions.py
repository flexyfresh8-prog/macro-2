"""Macro action model.

Action types:
  select_item  — press the configured hotbar key to equip an item
  key          — press an ability key (Z/X/C/V/F/custom)
  click        — mouse click at current position or explicit screen coords
  mouse_path   — replay a recorded movement path
  delay        — wait
  repeat_block — repeat the N following actions (see Macro.repeat_at)

Every action supports: delay_before, delay_after, repeat count, hold
duration, enable/disable.  The model is plain dataclasses + to/from dict so
macros are portable JSON.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

ACTION_TYPES = ("select_item", "key", "click", "mouse_path", "delay", "repeat_block")


@dataclass
class Action:
    type: str
    # select_item / key
    item_id: str = ""            # for select_item
    item_name: str = ""
    key: str = ""                # ability key or hotbar slot key
    # key / click
    hold: float = 0.05           # seconds key/click held
    # click
    x: Optional[int] = None
    y: Optional[int] = None
    button: str = "left"
    # mouse_path
    path: List = field(default_factory=list)      # [(x, y, t)]
    path_speed: float = 1.0
    # delay
    duration: float = 0.5
    # generic
    delay_before: float = 0.0
    delay_after: float = 0.0
    repeat: int = 1
    enabled: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["path"] = [list(p) for p in self.path]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Action":
        known = Action("key").__dict__.keys()
        a = Action("key")
        for k, v in (d or {}).items():
            if k in known:
                if k == "path":
                    a.path = [tuple(p) for p in (v or [])]
                elif k in ("x", "y"):
                    a.__dict__[k] = int(v) if v is not None else None
                else:
                    a.__dict__[k] = v
        if a.type not in ACTION_TYPES:
            a.type = "key"
        return a

    def describe(self) -> str:
        if self.type == "select_item":
            return f"Select {self.item_name or self.item_id or 'item'} [{self.key or '?'}]"
        if self.type == "key":
            return f"Press {self.key or '?'}"
        if self.type == "click":
            pos = f" @ {self.x},{self.y}" if self.x is not None else ""
            return f"{self.button.capitalize()} click{pos}"
        if self.type == "mouse_path":
            return f"Mouse path ({len(self.path)} pts ×{self.path_speed:g})"
        if self.type == "delay":
            return f"Delay {self.duration:g}s"
        if self.type == "repeat_block":
            return f"Repeat block ×{self.repeat}"
        return self.type


@dataclass
class Macro:
    id: str = ""
    name: str = "Untitled macro"
    description: str = ""
    actions: List[Action] = field(default_factory=list)
    loop: bool = False
    created: float = field(default_factory=time.time)
    modified: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "format": "nth-macro",
            "version": 1,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "loop": self.loop,
            "created": self.created,
            "modified": self.modified,
            "actions": [a.to_dict() for a in self.actions],
        }

    @staticmethod
    def from_dict(d: dict) -> "Macro":
        if not isinstance(d, dict) or d.get("format") not in ("nth-macro", None):
            raise ValueError("Not an NTH macro file")
        return Macro(
            id=str(d.get("id", "")),
            name=str(d.get("name", "Imported macro")),
            description=str(d.get("description", "")),
            loop=bool(d.get("loop", False)),
            created=float(d.get("created", time.time())),
            modified=float(d.get("modified", time.time())),
            actions=[Action.from_dict(x) for x in d.get("actions", [])],
        )

    def enabled_actions(self) -> List[Action]:
        return [a for a in self.actions if a.enabled]

    def est_duration(self) -> float:
        t = 0.0
        for a in self.enabled_actions():
            t += a.delay_before
            if a.type == "delay":
                t += a.duration
            else:
                t += a.hold + a.delay_after
        return round(t, 2)
