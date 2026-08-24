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
WHISPER_MODEL_SIZE = "small"          # tiny / base / small
CAPTURE_HOTKEY = "<ctrl>+<shift>+c"

# Paths (anchored to the project folder so they resolve no matter where the
# app is launched from - fixes "clips disappeared" when the working dir changes)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPS_DIR = os.path.join(BASE_DIR, "clips")
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
TTS_OUT_DIR = os.path.join(BASE_DIR, "tts_out")
SOUNDS_DIR = os.path.join(BASE_DIR, "sounds")
INDEX_PATH = os.path.join(CLIPS_DIR, "index.json")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")


def ensure_dirs():
    for d in (CLIPS_DIR, DATASET_DIR, TTS_OUT_DIR, SOUNDS_DIR):
        os.makedirs(d, exist_ok=True)
