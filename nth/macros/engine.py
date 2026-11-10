"""Macro execution engine.

A dedicated worker thread drives the action timeline with
PLAY / PAUSE / RESUME / STOP / LOOP / STEP-BY-STEP support.  All game input
goes through the injected input backend (real SendInput on Windows, dry-run
elsewhere).  No Qt dependency — the UI subscribes via the ``on_state``
callback.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Callable, List, Optional

from nth.macros.actions import Action, Macro

IDLE, RUNNING, PAUSED, FINISHED = "idle", "running", "paused", "finished"


class MacroEngine:
    def __init__(self, input_backend, settings, activity=lambda tag, msg: None):
        self.input = input_backend
        self.settings = settings
        self.activity = activity
        self.on_state: Callable[[str, int], None] = lambda s, i: None
        self.on_action: Callable[[int, Action], None] = lambda i, a: None

        self.state = IDLE
        self.current_macro: Optional[Macro] = None
        self.current_index = -1
        self.actions_done = 0
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._pause_evt = threading.Event()      # set = running
        self._step_evt = threading.Event()       # set = waiting for step
        self._loop = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------ control API
    def start_macro(self, macro: Macro, loop: Optional[bool] = None,
                    step: Optional[bool] = None) -> bool:
        with self._lock:
            if self.state == RUNNING:
                return False
            if not macro.actions:
                self.activity("macro", "Macro is empty — nothing to run")
                return False
        self.stop(wait=True)
        self.current_macro = macro
        self._loop = self.settings.get("macro.loop", False) if loop is None else loop
        step_mode = self.settings.get("macro.step_mode", False) if step is None else step
        self._stop_evt.clear()
        self._pause_evt.set()
        self._step_evt.clear()
        self.actions_done = 0
        self._thread = threading.Thread(
            target=self._run, args=(macro, self._loop, step_mode),
            name="NTH-MacroEngine", daemon=True)
        self._set_state(RUNNING, -1)
        self.activity("macro", f"Running '{macro.name}' ({len(macro.actions)} actions)")
        self._thread.start()
        return True

    def pause(self) -> bool:
        if self.state != RUNNING:
            return False
        self._pause_evt.clear()
        self._set_state(PAUSED, self.current_index)
        self.activity("macro", "Paused")
        return True

    def resume(self) -> bool:
        if self.state != PAUSED:
            return False
        self._pause_evt.set()
        self._set_state(RUNNING, self.current_index)
        self.activity("macro", "Resumed")
        return True

    def toggle_pause(self) -> None:
        if self.state == RUNNING:
            self.pause()
        elif self.state == PAUSED:
            self.resume()

    def step(self) -> None:
        """Advance one action while paused/stepping."""
        self._step_evt.set()

    def stop(self, wait: bool = False) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_evt.set()
            self._pause_evt.set()      # unblock pause wait
            self._step_evt.set()       # unblock step wait
            if wait:
                self._thread.join(timeout=3.0)
        if self.state != IDLE:
            self._set_state(IDLE, -1)

    # ------------------------------------------------------------- worker loop
    def _run(self, macro: Macro, loop: bool, step_mode: bool) -> None:
        try:
            while True:
                ran_all = self._run_pass(macro, step_mode)
                self.actions_done += 1
                if self._stop_evt.is_set() or not loop or not ran_all:
                    break
                if not self._wait_pause():
                    break
                # small gap between loops
                if self._sleep(float(self.settings.get("macro.default_delay", 0.3))):
                    break
        finally:
            if not self._stop_evt.is_set():
                self.activity("macro", f"'{macro.name}' finished")
            self._set_state(IDLE, -1)

    def _run_pass(self, macro: Macro, step_mode: bool) -> bool:
        order: List[tuple] = []          # (index, action)
        for idx, action in enumerate(macro.actions):
            if action.enabled:
                order.append((idx, action))

        i = 0
        while i < len(order):
            if self._stop_evt.is_set():
                return False
            if not self._wait_pause():
                return False
            if step_mode:
                self._step_evt.clear()
                self._set_state(PAUSED, order[i][0])
                if not self._step_evt.wait(timeout=None) or self._stop_evt.is_set():
                    if self._stop_evt.is_set():
                        return False

            idx, action = order[i]

            # repeat_block: execute the next N actions `repeat` extra times
            if action.type == "repeat_block":
                block = order[i + 1:i + 1 + int(action.repeat)]
                for _ in range(max(0, int(action.repeat))):
                    for bidx, bact in block:
                        if self._stop_evt.is_set() or not self._exec(bidx, bact):
                            return False
                i += 1 + len(block)
                continue

            if not self._exec(idx, action):
                return False
            i += 1
        return True

    def _exec(self, idx: int, action: Action) -> bool:
        self.current_index = idx
        self.on_action(idx, action)
        self._set_state(RUNNING if self._pause_evt.is_set() else PAUSED, idx)
        self._sleep(action.delay_before)
        if self._stop_evt.is_set():
            return False

        ok = True
        for _ in range(max(1, int(action.repeat)) if action.type != "repeat_block" else 1):
            if self._stop_evt.is_set():
                return False
            ok = self._execute_one(action) and ok
        self._sleep(action.delay_after)
        return ok

    def _execute_one(self, action: Action) -> bool:
        hold_key = float(self.settings.get("input.key_hold", 0.045))
        humanize = bool(self.settings.get("macro.humanize", True))
        safety = float(self.settings.get("macro.safety_delay", 0.10))
        try:
            if action.type == "select_item":
                key = action.key or self._item_hotbar_key(action.item_id)
                if not key:
                    self.activity("macro", f"No hotbar key for '{action.item_name}' — skipped")
                    return False
                return self.input.tap_key(key, hold=hold_key)

            if action.type == "key":
                return self.input.tap_key(action.key, hold=max(action.hold, 0.01))

            if action.type == "click":
                if action.x is not None and action.y is not None:
                    self.input.move_to(int(action.x), int(action.y))
                    time.sleep(0.02)
                return self.input.click(action.button, hold=0.03)

            if action.type == "mouse_path":
                return self.input.smooth_path(action.path, action.path_speed)

            if action.type == "delay":
                return not self._sleep(max(0.0, action.duration))

            if action.type == "repeat_block":
                return True  # handled in _run_pass
        except Exception as exc:      # noqa: BLE001
            self.activity("macro", f"Action error: {exc}")
            return False
        finally:
            if humanize and action.type in ("select_item", "key", "click"):
                time.sleep(safety * random.uniform(0.6, 1.4))
        return True

    def _item_hotbar_key(self, item_id: str) -> str:
        try:
            from nth.settings.manager import data_dir
            from nth.items.catalog import Catalog
            item = Catalog(data_dir()).get(item_id)
            return item.hotbar_key if item else ""
        except Exception:
            return ""

    # ------------------------------------------------------------- primitives
    def _sleep(self, seconds: float) -> bool:
        """Interruptible sleep. Returns True if stopped during the sleep."""
        end = time.monotonic() + max(0.0, seconds)
        while time.monotonic() < end:
            if self._stop_evt.is_set():
                return True
            self._pause_evt.wait(timeout=0.02)
        return self._stop_evt.is_set()

    def _wait_pause(self) -> bool:
        """Block while paused; False if stopped."""
        while not self._pause_evt.wait(timeout=0.05):
            if self._stop_evt.is_set():
                return False
        return not self._stop_evt.is_set()

    def _set_state(self, state: str, index: int) -> None:
        self.state = state
        self.current_index = index
        try:
            self.on_state(state, index)
        except Exception:
            pass
