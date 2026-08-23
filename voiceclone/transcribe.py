"""faster-whisper transcription (CPU, lazy-loaded)."""
from .config import WHISPER_MODEL_SIZE


class Transcriber:
    def __init__(self, event_queue):
        self.q = event_queue
        self.model = None

    def _ensure(self):
        if self.model is None:
            self.q.put(("status", f"Loading Whisper '{WHISPER_MODEL_SIZE}' (first time)..."))
            from faster_whisper import WhisperModel
            self.model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
            self.q.put(("status", "Whisper loaded."))

    def unload(self):
        self.model = None

    def transcribe_file(self, fpath):
        self._ensure()
        segments, _ = self.model.transcribe(fpath, beam_size=1)
        return " ".join(s.text.strip() for s in segments).strip()
