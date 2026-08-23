"""Shared PyAudio instance + conversion/device helpers."""
import numpy as np
import pyaudio

from .config import INT16_MAX

_PA = None


def get_pa():
    global _PA
    if _PA is None:
        _PA = pyaudio.PyAudio()
    return _PA


def release_pa():
    global _PA
    if _PA is not None:
        try:
            _PA.terminate()
        except Exception:
            pass
        _PA = None


def list_input_devices():
    pa = get_pa()
    out = []
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("maxInputChannels", 0) > 0:
            out.append((i, info["name"], int(info["maxInputChannels"])))
    return out


def list_output_devices():
    pa = get_pa()
    out = []
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("maxOutputChannels", 0) > 0:
            out.append((i, info["name"], int(info["maxOutputChannels"])))
    return out


def default_output_index():
    try:
        return get_pa().get_default_output_device_info()["index"]
    except Exception:
        return None


def bytes_to_mono_f32(data, channels):
    arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    if channels > 1:
        arr = arr.reshape(-1, channels).mean(axis=1)
    return arr


def mono_f32_to_stereo_int16_bytes(mono):
    mono = np.clip(mono, -INT16_MAX, INT16_MAX).astype(np.int16)
    return np.stack([mono, mono], axis=1).ravel().tobytes()
