"""Settings + clip-index persistence."""
import json
import os

from .config import SETTINGS_PATH, INDEX_PATH

_DEFAULT_SETTINGS = {
    "auto_update": True,
    "auto_transcribe": True,
    "enable_capture_hotkey": True,
    "enable_sound_hotkeys": True,
    "sounds": [],
    "mic_gain": 100,
    "sound_gain": 100,
    "keybinds": {"capture": "<ctrl>+<shift>+c", "stop_sounds": ""},
    "sound_binds": {},
    "pitch_semitones": 0,
    "pitch_enabled": False,
    "pitch_presets": {"Normal": 0, "Chipmunk": 7, "Deep": -7},
    "tts_model": "",
}


def _load(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_settings():
    s = dict(_DEFAULT_SETTINGS)
    s.update(_load(SETTINGS_PATH, {}))
    return s


def save_settings(s):
    _save(SETTINGS_PATH, s)


def load_index():
    return _load(INDEX_PATH, [])


def save_index(index):
    _save(INDEX_PATH, index)