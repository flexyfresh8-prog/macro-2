"""Windows input automation via SendInput (scan-code based).

This is *standard* Windows input automation — the same mechanism used by
accessibility tools and AutoHotkey.  NTH deliberately does NOT use DLL
injection, memory manipulation, or any anti-cheat bypass: it only sends
synthetic keyboard/mouse events to the foreground window.

A cross-platform "dry run" backend mirrors the same API for testing and
safe-mode so every call site stays identical.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import platform
import sys
import time
from typing import Dict, List, Optional, Tuple

IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------------------------
# Key tables
# ---------------------------------------------------------------------------
_VK_SPECIAL: Dict[str, int] = {
    "SPACE": 0x20, "ENTER": 0x0D, "RETURN": 0x0D, "ESC": 0x1B, "ESCAPE": 0x1B,
    "TAB": 0x09, "SHIFT": 0x10, "CTRL": 0x11, "CONTROL": 0x11, "ALT": 0x12,
    "BACKSPACE": 0x08, "DELETE": 0x2E, "DEL": 0x2E, "INSERT": 0x2D, "INS": 0x2D,
    "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
}
for _i in range(1, 13):
    _VK_SPECIAL[f"F{_i}"] = 0x6F + _i          # F1 = 0x70

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001


def normalize_key(key: str) -> str:
    k = (key or "").strip().upper()
    if not k:
        return ""
    if k in _VK_SPECIAL:
        return k
    return k[:1]


def key_supported(key: str) -> bool:
    return bool(vk_for_key(key))


def vk_for_key(key: str) -> Optional[int]:
    k = normalize_key(key)
    if not k:
        return None
    if k in _VK_SPECIAL:
        return _VK_SPECIAL[k]
    if len(k) == 1:
        if k.isdigit():
            return ord(k)
        if "A" <= k <= "Z":
            return ord(k)
        # numpad digits
    return None


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------
class DryRunInputBackend:
    """Logs every action instead of sending input (tests / safe mode)."""

    def __init__(self):
        self.journal: List[Tuple[float, str]] = []
        self._pos = (0, 0)

    def _log(self, msg: str) -> None:
        self.journal.append((time.monotonic(), msg))
        if len(self.journal) > 2000:
            del self.journal[:1000]

    def key_down(self, key: str) -> bool: self._log(f"key_down {normalize_key(key)}"); return True
    def key_up(self, key: str) -> bool: self._log(f"key_up {normalize_key(key)}"); return True

    def tap_key(self, key: str, hold: float = 0.045) -> bool:
        self._log(f"tap {normalize_key(key)} hold={hold:.3f}")
        if hold > 0:
            time.sleep(min(hold, 0.25))
        return True

    def move_to(self, x: int, y: int) -> bool:
        self._pos = (x, y)
        self._log(f"move {x},{y}")
        return True

    def current_pos(self) -> Tuple[int, int]:
        return self._pos

    def click(self, button: str = "left", hold: float = 0.03) -> bool:
        self._log(f"click {button} hold={hold:.3f}")
        return True

    def smooth_path(self, points: List[Tuple[int, int, float]], speed: float = 1.0,
                    progress=None) -> bool:
        self._log(f"path {len(points)} pts speed={speed:.2f}")
        return True

    @property
    def is_real(self) -> bool:
        return False


class Win32InputBackend:
    """SendInput-based keyboard + mouse automation (Windows only)."""

    def __init__(self):
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class _MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                        ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                        ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]

        class _KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                        ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]

        class _INPUTUNION(ctypes.Union):
            _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]

        class _INPUT(ctypes.Structure):
            _fields_ = [("type", wt.DWORD), ("union", _INPUTUNION)]

        self._INPUT = _INPUT
        self._KEYBDINPUT = _KEYBDINPUT
        self._MOUSEINPUT = _MOUSEINPUT

    # -- keyboard ------------------------------------------------------------
    def _scancode(self, vk: int) -> int:
        MAPVK_VK_TO_VSC = 0
        return self._user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC) & 0xFF

    def _send_key(self, key: str, up: bool) -> bool:
        vk = vk_for_key(key)
        if vk is None:
            return False
        scan = self._scancode(vk)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
        ki = self._KEYBDINPUT(0, scan, flags, 0, None)
        inp = self._INPUT(INPUT_KEYBOARD)
        inp.union.ki = ki
        return bool(self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) == 1)

    def key_down(self, key: str) -> bool:
        return self._send_key(key, False)

    def key_up(self, key: str) -> bool:
        return self._send_key(key, True)

    def tap_key(self, key: str, hold: float = 0.045) -> bool:
        if not self.key_down(key):
            return False
        time.sleep(max(0.01, min(hold, 0.5)))
        self.key_up(key)
        return True

    # -- mouse -----------------------------------------------------------------
    def move_to(self, x: int, y: int) -> bool:
        return bool(self._user32.SetCursorPos(int(x), int(y)))

    def current_pos(self) -> Tuple[int, int]:
        pt = wt.POINT()
        self._user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def _send_mouse(self, flags: int) -> bool:
        mi = self._MOUSEINPUT(0, 0, 0, flags, 0, None)
        inp = self._INPUT(INPUT_MOUSE)
        inp.union.mi = mi
        return bool(self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) == 1)

    def click(self, button: str = "left", hold: float = 0.03) -> bool:
        btn = (button or "left").lower()
        down, up = {
            "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
            "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
            "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
        }.get(btn, (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP))
        ok = self._send_mouse(down)
        time.sleep(max(0.005, min(hold, 0.3)))
        self._send_mouse(up)
        return ok

    def smooth_path(self, points: List[Tuple[int, int, float]], speed: float = 1.0,
                    progress=None) -> bool:
        """Replay [(x, y, t)] points; t = seconds offset from path start."""
        if not points:
            return True
        t0 = time.monotonic()
        for x, y, t in points:
            target_wait = (t / max(speed, 0.05)) - (time.monotonic() - t0)
            if target_wait > 0:
                time.sleep(min(target_wait, 1.0))
            self.move_to(int(x), int(y))
            if progress:
                progress(x, y)
        return True

    @property
    def is_real(self) -> bool:
        return True


def make_backend(settings) -> DryRunInputBackend | Win32InputBackend:
    """Factory honouring the input.backend setting and the platform."""
    mode = str(settings.get("input.backend", "auto")).lower()
    if mode == "dryrun":
        return DryRunInputBackend()
    if mode == "win32" or (mode == "auto" and IS_WINDOWS):
        if IS_WINDOWS:
            return Win32InputBackend()
        return DryRunInputBackend()
    return DryRunInputBackend()


PLATFORM_NOTE = (
    f"Real input backend available on Windows only (detected: {platform.system()}). "
    "Use Windows to drive the game; other platforms run in dry-run mode."
)
