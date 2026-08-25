"""Soundboard + mic passthrough mixer.

Sample-rate aware: each device is opened at its OWN native sample rate and audio
is resampled internally, which prevents the "deep/slow voice" and most crackle
caused by forcing a single rate onto devices that don't run at it.
"""
import threading

import numpy as np

from .config import CHUNK, FORMAT, INT16_MAX
from .audio_utils import get_pa, bytes_to_mono_f32, mono_f32_to_stereo_int16_bytes


def _device_rate(pa, index, fallback=48000):
    try:
        return int(round(pa.get_device_info_by_index(index)["defaultSampleRate"]))
    except Exception:
        return fallback


def _resample_linear(x, src, dst):
    """Fast linear resample of a mono float array. Good enough for voice/SFX."""
    if src == dst or len(x) == 0:
        return x
    n_out = int(round(len(x) * dst / src))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    src_idx = np.linspace(0.0, len(x) - 1, n_out)
    return np.interp(src_idx, np.arange(len(x)), x).astype(np.float32)


def _pitch_shift(x, semitones, rate):
    """Granular (overlap-add) pitch shift of a mono float array.
    Preserves duration (tempo) so it stays in sync for a live mic.
    Good for +/- a few semitones; larger shifts get 'chipmunk'/'demon' character.
    Returns an array the SAME length as x. Falls back to x on any error.
    """
    if not semitones or len(x) == 0:
        return x
    try:
        ratio = float(2.0 ** (semitones / 12.0))
        n = len(x)
        # grain ~ 30ms, hop = grain/4 for overlap-add
        grain = max(256, int(rate * 0.03))
        hop = grain // 4
        win = np.hanning(grain).astype(np.float32)
        out = np.zeros(n, dtype=np.float32)
        norm = np.zeros(n, dtype=np.float32)
        # read positions advance at 'ratio' so pitch changes, write advances at hop
        read_pos = 0.0
        wp = 0
        idx = np.arange(grain)
        while wp + grain <= n:
            r0 = int(read_pos)
            frac = read_pos - r0
            if r0 + grain + 1 <= n:
                a = x[r0:r0 + grain]
                b = x[r0 + 1:r0 + grain + 1]
                seg = (a * (1.0 - frac) + b * frac)
            else:
                seg = x[r0:r0 + grain]
                if len(seg) < grain:
                    seg = np.pad(seg, (0, grain - len(seg)))
            out[wp:wp + grain] += seg * win
            norm[wp:wp + grain] += win
            wp += hop
            read_pos += hop * ratio
            if read_pos + grain >= n:
                read_pos = max(0.0, n - grain - 1)
        norm[norm < 1e-6] = 1.0
        return (out / norm).astype(np.float32)
    except Exception:
        return x


class MixerEngine:
    def __init__(self, event_queue):
        self.q = event_queue
        self.mic_stream = None
        self.out_stream = None
        self.monitor_stream = None
        self.thread = None
        self.running = False
        self.mic_channels = 1
        self.in_rate = None
        self.out_rate = None
        self.mon_rate = None
        self.mic_gain = 1.0
        self.pitch_semitones = 0.0
        self.sound_gain = 1.0
        self._cache = {}       # (path, rate) -> mono float32 (int16 scale)
        self._active = []      # [ [data, pos], ... ]
        self._lock = threading.Lock()

    def set_mic_gain_percent(self, pct):
        self.mic_gain = max(0.0, pct / 100.0)

    def set_pitch_semitones(self, semi):
        try:
            self.pitch_semitones = float(semi)
        except Exception:
            self.pitch_semitones = 0.0

    def set_sound_gain_percent(self, pct):
        self.sound_gain = max(0.0, pct / 100.0)

    def _get_sound(self, path, rate):
        key = (path, rate)
        if key not in self._cache:
            import librosa
            y, _ = librosa.load(path, sr=rate, mono=True)
            self._cache[key] = (y * INT16_MAX).astype(np.float32)
        return self._cache[key]

    def trigger(self, path):
        rate = self.out_rate or 48000
        try:
            arr = self._get_sound(path, rate)
        except Exception as e:
            self.q.put(("error", f"Could not load sound: {e}"))
            return
        with self._lock:
            self._active.append([arr, 0])

    def stop_all_sounds(self):
        with self._lock:
            self._active = []

    def start(self, mic_index, cable_out_index, monitor_index=None):
        if self.running:
            self.stop()
        pa = get_pa()
        self.in_rate = _device_rate(pa, mic_index)
        self.out_rate = _device_rate(pa, cable_out_index)
        self.mon_rate = _device_rate(pa, monitor_index) if monitor_index is not None else None

        self.mic_stream = None
        for ch in (1, 2):
            try:
                self.mic_stream = pa.open(format=FORMAT, channels=ch, rate=self.in_rate, input=True,
                                          input_device_index=mic_index, frames_per_buffer=CHUNK)
                self.mic_channels = ch
                break
            except Exception:
                self.mic_stream = None
        if self.mic_stream is None:
            self.q.put(("error", "Could not open mic."))
            return False
        try:
            self.out_stream = pa.open(format=FORMAT, channels=2, rate=self.out_rate, output=True,
                                      output_device_index=cable_out_index, frames_per_buffer=CHUNK)
        except Exception as e:
            self.q.put(("error", f"Could not open cable output: {e}"))
            self.stop()
            return False
        if monitor_index is not None:
            try:
                self.monitor_stream = pa.open(format=FORMAT, channels=2, rate=self.mon_rate, output=True,
                                              output_device_index=monitor_index, frames_per_buffer=CHUNK)
            except Exception:
                self.monitor_stream = None

        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.q.put(("status", f"Mixer running (mic {self.in_rate}Hz -> out {self.out_rate}Hz)."))
        return True

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        for s in (self.mic_stream, self.out_stream, self.monitor_stream):
            if s:
                try:
                    s.stop_stream(); s.close()
                except Exception:
                    pass
        self.mic_stream = self.out_stream = self.monitor_stream = None

    def _loop(self):
        while self.running and self.mic_stream and self.out_stream:
            try:
                data = self.mic_stream.read(CHUNK, exception_on_overflow=False)
            except Exception as e:
                self.q.put(("error", f"Mixer mic error: {e}"))
                break
            mic = bytes_to_mono_f32(data, self.mic_channels)
            mix = _resample_linear(mic, self.in_rate, self.out_rate)
            n = len(mix)
            if n == 0:
                continue
            if self.pitch_semitones:
                mix = _pitch_shift(mix, self.pitch_semitones, self.out_rate)
            mix = mix * self.mic_gain
            with self._lock:
                still = []
                for item in self._active:
                    sdata, pos = item
                    seg = sdata[pos:pos + n]
                    mix[:len(seg)] += seg * self.sound_gain
                    pos += len(seg)
                    if pos < len(sdata):
                        item[1] = pos
                        still.append(item)
                self._active = still
            out_bytes = mono_f32_to_stereo_int16_bytes(mix)
            try:
                self.out_stream.write(out_bytes)
                if self.monitor_stream:
                    if self.mon_rate == self.out_rate:
                        self.monitor_stream.write(out_bytes)
                    else:
                        mon = _resample_linear(mix, self.out_rate, self.mon_rate)
                        self.monitor_stream.write(mono_f32_to_stereo_int16_bytes(mon))
            except Exception as e:
                self.q.put(("error", f"Mixer output error: {e}"))
                break

    def terminate(self):
        self.stop()
