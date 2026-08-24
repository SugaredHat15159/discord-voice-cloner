"""Shared constants and paths."""
import os
import pyaudio

# Audio
RATE = 48000
CHUNK = 2048
FORMAT = pyaudio.paInt16
SAMPWIDTH = 2
INT16_MAX = 32767

# Behaviour
DEFAULT_BUFFER_SECONDS = 15
WHISPER_MODEL_SIZE = "base"          # tiny / base / small
CAPTURE_HOTKEY = "<ctrl>+<shift>+c"

# Paths
CLIPS_DIR = "clips"
DATASET_DIR = "dataset"
TTS_OUT_DIR = "tts_out"
SOUNDS_DIR = "sounds"
INDEX_PATH = os.path.join(CLIPS_DIR, "index.json")
SETTINGS_PATH = "settings.json"


def ensure_dirs():
    for d in (CLIPS_DIR, DATASET_DIR, TTS_OUT_DIR, SOUNDS_DIR):
        os.makedirs(d, exist_ok=True)
