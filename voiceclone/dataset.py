"""Export transcribed clips into a Piper-ready dataset (per speaker)."""
import os

from .config import CLIPS_DIR, DATASET_DIR


def export_dataset(event_queue, index, speaker):
    clips = [c for c in index if c.get("speaker") == speaker and c.get("transcript")]
    if not clips:
        event_queue.put(("error", f"No transcribed clips for '{speaker}'."))
        return
    try:
        import librosa
        import soundfile as sf
        out_dir = os.path.join(DATASET_DIR, speaker)
        wav_dir = os.path.join(out_dir, "wav")
        os.makedirs(wav_dir, exist_ok=True)
        lines = []
        for i, c in enumerate(clips):
            event_queue.put(("train_status", f"Exporting {i + 1}/{len(clips)}..."))
            y, _ = librosa.load(os.path.join(CLIPS_DIR, c["filename"]), sr=22050, mono=True)
            cid = f"{speaker}_{i:04d}"
            sf.write(os.path.join(wav_dir, cid + ".wav"), y, 22050)
            text = c["transcript"].replace("|", " ").replace("\n", " ").strip()
            lines.append(f"{cid}|{text}")
        with open(os.path.join(out_dir, "metadata.csv"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        total = sum(c.get("duration", 0) for c in clips)
        event_queue.put(("train_status",
                         f"Exported {len(clips)} clips (~{total / 60:.1f} min) to {out_dir}"))
    except Exception as e:
        event_queue.put(("error", f"Export failed: {e}"))
