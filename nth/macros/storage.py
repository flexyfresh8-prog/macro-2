"""Macro + recording storage: data/macros/*.json, import/export helpers."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import List, Optional

from nth.macros.actions import Macro
from nth.settings.manager import data_dir


class MacroStorage:
    def __init__(self, folder: Optional[Path] = None):
        self.folder = folder or (data_dir() / "macros")
        self.folder.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- file paths
    def _path_for(self, name: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
        return self.folder / f"{safe or 'macro'}.json"

    # ------------------------------------------------------------------- CRUD
    def list_macros(self) -> List[dict]:
        out = []
        for f in sorted(self.folder.glob("*.json")):
            try:
                m = Macro.from_dict(json.loads(f.read_text(encoding="utf-8")))
                out.append({"id": m.id or f.stem, "name": m.name, "file": f.name,
                            "actions": len(m.actions), "modified": m.modified,
                            "loop": m.loop})
            except Exception:
                continue
        return out

    def save(self, macro: Macro) -> Path:
        if not macro.id:
            macro.id = uuid.uuid4().hex[:12]
        macro.modified = time.time()
        path = self._path_for(macro.name)
        path.write_text(json.dumps(macro.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return path

    def load(self, name_or_file: str) -> Optional[Macro]:
        p = Path(name_or_file)
        if not p.exists():
            p = self._path_for(name_or_file)
        if not p.exists():
            return None
        try:
            return Macro.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            return None

    def delete(self, name_or_file: str) -> bool:
        p = Path(name_or_file)
        if not p.exists():
            p = self._path_for(name_or_file)
        if p.exists():
            p.unlink()
            return True
        return False

    # -------------------------------------------------------- import / export
    def export_to(self, macro: Macro, dest_path: Path) -> Path:
        dest_path = Path(dest_path)
        dest_path.write_text(json.dumps(macro.to_dict(), indent=2, ensure_ascii=False),
                             encoding="utf-8")
        return dest_path

    def import_from(self, src_path: Path) -> Optional[Macro]:
        try:
            macro = Macro.from_dict(json.loads(Path(src_path).read_text(encoding="utf-8")))
            self.save(macro)
            return macro
        except Exception:
            return None

    def recording_path(self, name: str) -> Path:
        rec = self.folder.parent / "recordings"
        rec.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
        return rec / f"{safe or 'recording'}.json"

    def save_recording(self, name: str, data: dict) -> Path:
        p = self.recording_path(name)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return p

    def load_recording(self, name: str) -> Optional[dict]:
        p = self.recording_path(name)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None


def new_macro(name: str = "New macro") -> Macro:
    return Macro(id=uuid.uuid4().hex[:12], name=name)
