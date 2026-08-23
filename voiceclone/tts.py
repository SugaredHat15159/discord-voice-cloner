"""Piper TTS synthesis (uses the installed piper CLI)."""
import os
import sys
import shutil
import subprocess

from .config import TTS_OUT_DIR


def generate(model_path, text):
    """Synthesize text to a wav with Piper. Returns output path or raises."""
    if not model_path or not os.path.exists(model_path):
        raise FileNotFoundError("Pick a valid Piper .onnx model first.")
    if not text.strip():
        raise ValueError("No text to speak.")
    os.makedirs(TTS_OUT_DIR, exist_ok=True)
    out = os.path.join(TTS_OUT_DIR, "tts_last.wav")
    exe = shutil.which("piper")
    cmd = ([exe, "-m", model_path, "-f", out] if exe
           else [sys.executable, "-m", "piper", "-m", model_path, "-f", out])
    subprocess.run(cmd, input=text, text=True, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return out
