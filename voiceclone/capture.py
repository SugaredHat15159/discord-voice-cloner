"""Rolling-buffer capture engine (hotkey grabs the last N seconds)."""
import os
import wave
import threading
import datetime
from collections import deque

from .config import RATE, CHUNK, FORMAT, SAMPWIDTH, CLIPS_DIR, DEFAULT_BUFFER_SECONDS
from .audio_utils import get_pa


class AudioEngine:
    def __init__(self, event_queue):
        self.q = event_queue
        self.stream = None
        self.thread = None
        self.running = False
        self.channels = 2
        self.buffer_seconds = DEFAULT_BUFFER_SECONDS
        self.ring = deque()
        self._lock = threading.Lock()

    def start(self, device_index, channels, buffer_seconds):
        if self.running:
            self.stop()
        self.channels = max(1, min(2, channels))
        self.buffer_seconds = buffer_seconds
        with self._lock:
            self.ring = deque(maxlen=int(RATE / CHUNK * buffer_seconds))
        try:
            self.stream = get_pa().open(format=FORMAT, channels=self.channels, rate=RATE,
                                        input=True, input_device_index=device_index,
                                        frames_per_buffer=CHUNK)
        except Exception as e:
            self.q.put(("error", f"Could not open capture device: {e}"))
            return False
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.q.put(("status", "Monitoring VC audio. Capture hotkey armed."))
        return True

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        if self.stream:
            try:
                self.stream.stop_stream(); self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _loop(self):
        while self.running and self.stream:
            try:
                data = self.stream.read(CHUNK, exception_on_overflow=False)
            except Exception as e:
                self.q.put(("error", f"Capture error: {e}"))
                break
            with self._lock:
                self.ring.append(data)

    def save_last_clip(self, speaker):
        if not self.running:
            self.q.put(("error", "Not monitoring - start it first."))
            return
        with self._lock:
            frames = b"".join(self.ring)
        if not frames:
            self.q.put(("error", "Buffer empty - wait a moment."))
            return
        os.makedirs(CLIPS_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        fname = f"clip_{ts}.wav"
        with wave.open(os.path.join(CLIPS_DIR, fname), "wb") as wf:
            wf.setnchannels(self.channels); wf.setsampwidth(SAMPWIDTH)
            wf.setframerate(RATE); wf.writeframes(frames)
        dur = len(frames) / (RATE * self.channels * SAMPWIDTH)
        self.q.put(("new_clip", {
            "filename": fname, "speaker": speaker or "unknown", "transcript": "",
            "duration": round(dur, 1), "timestamp": ts, "status": "pending"}))

    def terminate(self):
        self.stop()
