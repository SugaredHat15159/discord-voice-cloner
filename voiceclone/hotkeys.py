"""Robust global hotkey matching by virtual-key code.

Replaces pynput's GlobalHotKeys (which is chord-oriented and can't tell numpad
keys apart from the top row). Here every key is identified by its vk, so numpad
9 is distinct from row 9 and ANY key/combo can be bound.
"""
from pynput import keyboard

Key = keyboard.Key
MODS = {"ctrl", "alt", "shift"}


def normalize(key):
    """Turn a pynput key event into a stable token string."""
    if key in (Key.ctrl, Key.ctrl_l, Key.ctrl_r):
        return "ctrl"
    if key in (Key.alt, Key.alt_l, Key.alt_r, getattr(Key, "alt_gr", None)):
        return "alt"
    if key in (Key.shift, Key.shift_l, Key.shift_r):
        return "shift"
    if isinstance(key, keyboard.KeyCode):
        if key.vk is not None:
            return f"vk{key.vk}"
        if key.char:
            return f"ch{key.char.lower()}"
        return None
    if isinstance(key, keyboard.Key):
        return f"k{key.name}"
    return None


_VK_NAMES = {
    96: "Num0", 97: "Num1", 98: "Num2", 99: "Num3", 100: "Num4",
    101: "Num5", 102: "Num6", 103: "Num7", 104: "Num8", 105: "Num9",
    106: "Num*", 107: "Num+", 109: "Num-", 110: "Num.", 111: "Num/",
    32: "Space", 13: "Enter", 9: "Tab", 8: "Backspace",
    37: "Left", 38: "Up", 39: "Right", 40: "Down",
}


def _vk_name(vk):
    if vk in _VK_NAMES:
        return _VK_NAMES[vk]
    if 48 <= vk <= 57:
        return chr(vk)              # 0-9
    if 65 <= vk <= 90:
        return chr(vk)              # A-Z
    if 112 <= vk <= 123:
        return f"F{vk - 111}"       # F1-F12
    return f"VK{vk}"


def label_for(tokens):
    """Human-readable label like 'Ctrl+Alt+Num9' for a token list."""
    if not tokens:
        return "(none)"
    order = {"ctrl": 0, "alt": 1, "shift": 2}
    mods = sorted([t for t in tokens if t in MODS], key=lambda t: order[t])
    main = [t for t in tokens if t not in MODS]
    parts = [m.capitalize() for m in mods]
    for t in main:
        if t.startswith("vk"):
            parts.append(_vk_name(int(t[2:])))
        elif t.startswith("ch"):
            parts.append(t[2:].upper())
        elif t.startswith("k"):
            parts.append(t[1:].capitalize())
    return "+".join(parts) if parts else "(none)"


def tokens_from_pynput_string(sfmt):
    """Migrate an old pynput-style hotkey string ('<ctrl>+<alt>+c', '<98>') to tokens."""
    if not sfmt or not isinstance(sfmt, str):
        return []
    out = []
    for part in sfmt.split("+"):
        part = part.strip()
        if not part:
            continue
        if part.startswith("<") and part.endswith(">"):
            inner = part[1:-1]
            if inner in ("ctrl", "ctrl_l", "ctrl_r"):
                out.append("ctrl")
            elif inner in ("alt", "alt_l", "alt_r", "alt_gr"):
                out.append("alt")
            elif inner in ("shift", "shift_l", "shift_r"):
                out.append("shift")
            elif inner.isdigit():
                out.append(f"vk{inner}")
            else:
                out.append(f"k{inner}")
        else:
            c = part.lower()
            if len(c) == 1 and (c.isalpha() or c.isdigit()):
                out.append(f"vk{ord(c.upper())}")   # map letter/digit to Windows vk
            else:
                out.append(f"ch{c}")
    return out


class HotkeyManager:
    """Runs one global key listener and fires callbacks when a combo is held."""

    def __init__(self):
        self._listener = None
        self._binds = {}        # frozenset(tokens) -> callable
        self._pressed = set()
        self._fired = set()

    def set_binds(self, binds):
        """binds: iterable of (tokens_list, callable)."""
        self._binds = {}
        for tokens, fn in binds:
            if tokens:
                self._binds[frozenset(tokens)] = fn
        self._pressed = set()
        self._fired = set()

    def start(self):
        self.stop()
        if not self._binds:
            return
        self._listener = keyboard.Listener(on_press=self._on_press,
                                           on_release=self._on_release)
        self._listener.start()

    def stop(self):
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self._pressed = set()
        self._fired = set()

    def _on_press(self, key):
        t = normalize(key)
        if not t:
            return
        self._pressed.add(t)
        for combo, fn in self._binds.items():
            if combo <= self._pressed and combo not in self._fired:
                self._fired.add(combo)
                try:
                    fn()
                except Exception:
                    pass

    def _on_release(self, key):
        t = normalize(key)
        if not t:
            return
        self._pressed.discard(t)
        for combo in list(self._fired):
            if not (combo <= self._pressed):
                self._fired.discard(combo)
