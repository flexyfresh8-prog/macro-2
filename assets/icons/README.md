# Reference Icon Database

This folder holds the **reference images** the Vision Engine matches against
real game captures. Structure:

```
assets/icons/fruits/<item_id>.png     # one PNG per fruit item id
assets/icons/swords/<item_id>.png     # one PNG per sword item id
assets/icons/styles/<item_id>.png     # one PNG per fighting style item id
```

## How NTH uses these

* **No placeholder images are shipped.** The matcher only recognizes items
  that actually have a reference here — it never guesses from generic art.
* Item ids come from `data/catalog.json` (e.g. `kitsune.png`,
  `cursed-dual-katana.png`, `godhuman.png`).
* Any resolution works: the matcher is multi-scale (default 40–96 px icon
  height). Clean square crops of the in-game icon work best.
* PNGs with alpha are flattened onto a dark background automatically.

## Adding / replacing references

1. **In the app (recommended):** Vision Engine → select an item row →
   *CAPTURE FROM SCREEN* (drag a box around the in-game icon) or
   *IMPORT FILE…*.
2. **Manually:** drop correctly-named PNGs into these folders, then press
   *RESCAN FOLDER* (or restart). New files are picked up **without rebuilding
   the application**.
