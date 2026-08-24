"""One-shot fixed-length recording (for reading prompts in your own voice)."""
import os
import wave
import datetime

from .config import RATE, CHUNK, FORMAT, SAMPWIDTH, CLIPS_DIR
from .audio_utils import get_pa


def record_fixed(event_queue, device_index, channels, seconds, speaker):
    channels = max(1, min(2, channels))
    try:
        event_queue.put(("status", f"Recording {seconds}s..."))
        stream = get_pa().open(format=FORMAT, channels=channels, rate=RATE,
                               input=True, input_device_index=device_index,
                               frames_per_buffer=CHUNK)
        frames = [stream.read(CHUNK, exception_on_overflow=False)
                  for _ in range(int(RATE / CHUNK * seconds))]
        stream.stop_stream(); stream.close()
        data = b"".join(frames)
        os.makedirs(CLIPS_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        fname = f"clip_{ts}.wav"
        with wave.open(os.path.join(CLIPS_DIR, fname), "wb") as wf:
            wf.setnchannels(channels); wf.setsampwidth(SAMPWIDTH)
            wf.setframerate(RATE); wf.writeframes(data)
        event_queue.put(("new_clip", {
            "filename": fname, "speaker": speaker or "unknown", "transcript": "",
            "duration": round(len(data) / (RATE * channels * SAMPWIDTH), 1),
            "timestamp": ts, "status": "pending"}))
    except Exception as e:
        event_queue.put(("error", f"Record failed: {e}"))
