"""Soundboard + mic passthrough mixer -> virtual cable (and optional monitor)."""
import threading

import numpy as np

from .config import RATE, CHUNK, FORMAT, INT16_MAX
from .audio_utils import get_pa, bytes_to_mono_f32, mono_f32_to_stereo_int16_bytes


class MixerEngine:
    def __init__(self, event_queue):
        self.q = event_queue
        self.mic_stream = None
        self.out_stream = None
        self.monitor_stream = None
        self.thread = None
        self.running = False
        self.mic_channels = 1
        self.gain = 1.0
        self._cache = {}       # path -> mono float32 (int16 scale)
        self._active = []      # [ [data, pos], ... ]
        self._lock = threading.Lock()

    def set_gain_percent(self, pct):
        self.gain = max(0.0, pct / 100.0)

    def load_sound(self, path):
        if path in self._cache:
            return True
        try:
            import librosa
            y, _ = librosa.load(path, sr=RATE, mono=True)
            self._cache[path] = (y * INT16_MAX).astype(np.float32)
            return True
        except Exception as e:
            self.q.put(("error", f"Could not load sound: {e}"))
            return False

    def trigger(self, path):
        if self.load_sound(path):
            with self._lock:
                self._active.append([self._cache[path], 0])

    def stop_all_sounds(self):
        with self._lock:
            self._active = []

    def start(self, mic_index, cable_out_index, monitor_index=None):
        if self.running:
            self.stop()
        pa = get_pa()
        for ch in (1, 2):
            try:
                self.mic_stream = pa.open(format=FORMAT, channels=ch, rate=RATE, input=True,
                                          input_device_index=mic_index, frames_per_buffer=CHUNK)
                self.mic_channels = ch
                break
            except Exception:
                self.mic_stream = None
        if self.mic_stream is None:
            self.q.put(("error", "Could not open mic."))
            return False
        try:
            self.out_stream = pa.open(format=FORMAT, channels=2, rate=RATE, output=True,
                                      output_device_index=cable_out_index, frames_per_buffer=CHUNK)
        except Exception as e:
            self.q.put(("error", f"Could not open cable output: {e}"))
            self.stop()
            return False
        if monitor_index is not None:
            try:
                self.monitor_stream = pa.open(format=FORMAT, channels=2, rate=RATE, output=True,
                                              output_device_index=monitor_index, frames_per_buffer=CHUNK)
            except Exception:
                self.monitor_stream = None
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.q.put(("status", "Mixer running - set Discord input to CABLE Output."))
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
            mix = bytes_to_mono_f32(data, self.mic_channels)
            if len(mix) < CHUNK:
                mix = np.pad(mix, (0, CHUNK - len(mix)))
            with self._lock:
                still = []
                for item in self._active:
                    sdata, pos = item
                    seg = sdata[pos:pos + CHUNK]
                    mix[:len(seg)] += seg
                    pos += len(seg)
                    if pos < len(sdata):
                        item[1] = pos
                        still.append(item)
                self._active = still
            mix = mix * self.gain
            out_bytes = mono_f32_to_stereo_int16_bytes(mix)
            try:
                self.out_stream.write(out_bytes)
                if self.monitor_stream:
                    self.monitor_stream.write(out_bytes)
            except Exception as e:
                self.q.put(("error", f"Mixer output error: {e}"))
                break

    def terminate(self):
        self.stop()
