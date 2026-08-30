"""Piper TTS synthesis (uses the installed piper CLI)."""
import os
import sys
import shutil
import subprocess
import time
import wave

from .config import TTS_OUT_DIR


def generate(model_path, text, length_scale=1.0):
    """Synthesize text to a wav with Piper. Returns output path or raises."""
    if not model_path or not os.path.exists(model_path):
        raise FileNotFoundError("Pick a valid Piper .onnx model first.")
    if not text.strip():
        raise ValueError("No text to speak.")
    os.makedirs(TTS_OUT_DIR, exist_ok=True)
    out = os.path.join(TTS_OUT_DIR, f"tts_{int(time.time()*1000)}.wav")
    exe = shutil.which("piper")
    ls = ["--length-scale", str(length_scale)]
    cmd = ([exe, "-m", model_path, "-f", out] + ls if exe
           else [sys.executable, "-m", "piper", "-m", model_path, "-f", out] + ls)
    subprocess.run(cmd, input=text, text=True, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    _pad_tail(out, 0.35)
    return out


def _pad_tail(path, seconds):
    """Append a little silence so the end of the clip isn't clipped on playback."""
    try:
        with wave.open(path, "rb") as w:
            params = w.getparams()
            frames = w.readframes(w.getnframes())
        pad = int(params.framerate * seconds) * params.nchannels * params.sampwidth
        with wave.open(path, "wb") as w:
            w.setparams(params)
            w.writeframes(frames + b"\x00" * pad)
    except Exception:
        pass
