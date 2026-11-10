# NTH — Blox Fruits Automation Suite

An advanced Blox Fruits-focused **macro automation and visual recognition
platform** for Windows. NTH combines a premium monochrome desktop UI
(PySide6), a real computer-vision engine (OpenCV template/feature matching),
a full macro studio (timeline editor, play/pause/stop/loop/step), mouse
recording & replay, screen color-change triggers, and optional GitHub
integration — with clean modular architecture for future updates.

> **UI preview without installing anything:** open
> [`preview/index.html`](preview/index.html) in any browser. It is a
> standalone, fully interactive preview of the desktop interface.

---

## ⚠ Disclaimer

NTH uses **standard Windows input automation only** (synthetic keyboard and
mouse events via `SendInput`). It does **not** use DLL injection, exploit
executors, memory manipulation, or any anti-cheat bypass. nevertheless,
game automation may violate Roblox's Terms of Service and can lead to
account penalties. Use at your own risk and responsibly.

---

## Features

| Module | Highlights |
| --- | --- |
| **Dashboard** | Live status for system / Roblox / build / macro / mouse / vision, activity feed, performance meters |
| **Find Build** | One-click: locate Roblox window → focus → capture → CV analysis → detected Fruit / Sword / Fighting Style with confidence rings, alternatives, screenshot preview, build history |
| **Macro Studio** | Drag-and-drop timeline of *Select Item / Key / Click / Mouse Path / Delay / Repeat* actions; per-action delays, hold, repeat, enable; PLAY · PAUSE · STOP · LOOP · STEP; save / load / export / import JSON |
| **Move Library** | Saved moves & combos with search, category filters, favorites; insert into any macro |
| **Vision Engine** | Reference-icon database management (capture from screen or import file), recognition console, screenshot history; database updates **without rebuilding** |
| **Settings** | Window detection, recognition sensitivity, macro timing, mouse/color detection, theme glow, GitHub integration, database management |

### Recognition engine (no OCR)

1. Multi-scale **template matching** (`TM_CCOEFF_NORMED`, 40–96 px ladder +
   fine refinement pass) across the configured scan region.
2. **ORB feature verification** for borderline scores.
3. Appearance **embeddings** (HSV histogram) to rank alternatives.
4. Per-item **confidence scoring**, non-max suppression, unresolved-item
   reporting. Low confidence ⇒ NTH asks for another screenshot instead of
   pretending certainty.

The engine ships with **zero placeholder icons** — it only recognizes items
that have a real reference image, added via the Vision Engine or dropped
into `assets/icons/<category>/<item_id>.png`.

---

## Installation

```bash
# Windows (Python 3.10+, 3.11 recommended)
git clone https://github.com/<you>/macro-2.git
cd macro-2
python -m pip install -r requirements.txt
python main.py
```

Linux/macOS run in **dry-run input mode** (engine fully testable, no real
input events) — Windows is the supported target for game automation.

## Building `NTH.exe`

**Local (Windows):**

```bat
build\build.bat
:: → dist\NTH.exe
```

**CI (any OS):** push a tag `v1.0.x` — the included GitHub Action
(`.github/workflows/build-windows.yml`) builds the one-file exe on
`windows-latest` and attaches it to the release. You can also trigger it
manually from the *Actions* tab (**Run workflow**), then download
`NTH-windows-exe` from the run's artifacts.

---

## Item database (93 items, expandable)

* 42 fruits · 38 swords · 13 fighting styles — shipped in
  `data/catalog.json` (editable: names, tiers, aliases, ability keys,
  hotbar slots). Add new items or tune abilities **without touching code**.
* Reference icons: `assets/icons/{fruits,swords,styles}/<item_id>.png`
  (see [`assets/icons/README.md`](assets/icons/README.md)).

## Macro format

Macros are portable JSON (`format: "nth-macro"`). Example:

```json
{
  "format": "nth-macro",
  "version": 1,
  "name": "Combo Demo",
  "loop": false,
  "actions": [
    {"type": "select_item", "item_id": "dough", "item_name": "Dough", "key": "2"},
    {"type": "key", "key": "Z", "delay_after": 0.5},
    {"type": "select_item", "item_id": "cursed-dual-katana", "item_name": "CDK", "key": "3"},
    {"type": "key", "key": "X", "delay_after": 0.3},
    {"type": "select_item", "item_id": "godhuman", "item_name": "Godhuman", "key": "4"},
    {"type": "key", "key": "Z", "delay_after": 1.0}
  ]
}
```

`Select Item` fires the item's **hotbar slot key** (set per item in
`catalog.json`, e.g. `"hotbar_key": "3"`) — NTH never assumes an item is
already equipped.

## Color-change triggers

IF a monitored screen region changes from color A to color B beyond the
configured tolerance (held N consecutive samples) THEN run a macro or tap a
key. Region, tolerance, interval, cooldown and trigger are stored in
`data/settings.json` (`color.region`).

## Architecture

```
main.py                     # entry point (DPI-aware bootstrap)
nth/
├── ui/                     # PySide6 interface (frameless shell + 6 pages)
│   ├── theme.py            #   design tokens + QSS (matches preview/index.html)
│   ├── widgets.py          #   custom cards, glow buttons, status dots, meters
│   ├── main_window.py      #   sidebar navigation + animated transitions
│   └── pages/              #   dashboard, find_build, macro_studio,
│                           #   move_library, vision_engine, settings
├── core/                   # window manager, capture, input backend (SendInput
│                           #   / dry-run), mouse tracker, color monitor, app context
├── vision/                 # matcher (template+ORB+embeddings), icon DB, pipeline
├── recognition/            # build inference (cross-referencing)
├── macros/                 # action model, execution engine, mouse recorder, storage
├── database/               # SQLite (builds, moves, activity)
├── items/                  # catalog (93 items) → data/catalog.json
├── settings/               # JSON settings manager
└── integrations/           # GitHub (keyring token store, REST, git push)
assets/icons/               # reference icon database (user-provided)
data/                       # runtime: catalog.json, settings.json, nth.db, macros/
build/                      # NTH.spec (PyInstaller), build.bat
preview/index.html          # standalone browser preview of the UI
tests/                      # CV, core, and UI smoke tests
```

**Design principle:** the visual layer (`ui/`) is fully decoupled from
automation/recognition logic (`core/`, `vision/`, `macros/`) — the engine
threads never import Qt, which keeps the whole platform testable headlessly.

## Tests

```bash
python tests/test_core.py     # catalog integrity, macro model, engine dry-run
python tests/test_vision.py   # synthetic-frame end-to-end CV detection
python tests/test_ui_smoke.py # full app boot + all pages (offscreen)
```

## GitHub integration & token security

Settings → GitHub Integration → **SAVE TOKEN** stores your PAT in the
**OS credential vault** (Windows Credential Manager via `keyring`). The
token is never written to project files, settings, the HTML preview, or the
git history, and pushes use a temporary askpass helper so it never lands in
remote URLs or `.git/config`.

## Data locations

| Path | Contents |
| --- | --- |
| `data/catalog.json` | item database (tracked) |
| `data/settings.json` | your settings (gitignored) |
| `data/nth.db` | builds / moves / activity (gitignored) |
| `data/macros/*.json` | saved macros (`example_combo.json` tracked) |
| `data/builds/*.png` | saved build screenshots (gitignored) |
