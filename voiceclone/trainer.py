"""Local Piper TTS voice model training."""
import os
import sys
import json
import subprocess
from pathlib import Path

def train_voice(q, dataset_dir, output_dir, speaker_name, num_epochs=100):
    """Fine-tune Piper on a local dataset.
    
    Args:
        q: Event queue for status updates
        dataset_dir: Path to dataset folder (must have wav/ and metadata.csv)
        output_dir: Where to save trained models
        speaker_name: Name of the speaker (for folder organization)
        num_epochs: Number of training epochs
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # Verify dataset structure
        dataset_path = Path(dataset_dir)
        wav_dir = dataset_path / "wav"
        metadata_file = dataset_path / "metadata.csv"
        
        if not wav_dir.exists() or not metadata_file.exists():
            q.put(("error", f"Dataset missing wav/ or metadata.csv in {dataset_dir}"))
            return
        
        num_wavs = len(list(wav_dir.glob("*.wav")))
        q.put(("train_status", f"Starting training on {num_wavs} clips..."))
        
        # Build training command
        # Using piper_train as a module (subprocess)
        cmd = [
            sys.executable, "-m", "piper_train",
            "--dataset-dir", str(dataset_dir),
            "--output-dir", str(output_dir),
            "--quality", "medium",
            "--num-workers", "2",
            "--batch-size", "8",
            "--num-epochs", str(num_epochs),
        ]
        
        q.put(("train_status", "Running training (this takes 1-2 hours on CPU)..."))
        
        # Run training and capture output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=os.path.dirname(__file__)
        )
        
        # Stream output and look for progress indicators
        for line in process.stdout:
            line = line.strip()
            if line:
                # Parse progress from Piper output
                if "epoch" in line.lower():
                    q.put(("train_status", line))
                elif "loss" in line.lower():
                    q.put(("train_status", line))
        
        process.wait()
        
        if process.returncode != 0:
            q.put(("error", f"Training failed with code {process.returncode}"))
            return
        
        # Find the latest checkpoint and export as .onnx
        checkpoints = sorted([d for d in Path(output_dir).glob("checkpoint_*")], reverse=True)
        if not checkpoints:
            q.put(("error", "Training completed but no checkpoints found"))
            return
        
        latest_ckpt = checkpoints[0]
        model_path = latest_ckpt / "model.onnx"
        config_path = latest_ckpt / "model.onnx.json"
        
        if not model_path.exists():
            q.put(("error", f"Model file not found in {latest_ckpt}"))
            return
        
        # Copy to trained_models/<speaker>/
        trained_dir = Path(output_dir).parent / "trained_models" / speaker_name
        trained_dir.mkdir(parents=True, exist_ok=True)
        
        import shutil
        final_model = trained_dir / "model.onnx"
        final_config = trained_dir / "model.onnx.json"
        
        shutil.copy(model_path, final_model)
        if config_path.exists():
            shutil.copy(config_path, final_config)
        
        q.put(("train_status", f"✓ Training complete! Model saved to {trained_dir}"))
        q.put(("status", f"Voice '{speaker_name}' trained. Load it in Voice (TTS) tab."))
        
    except Exception as e:
        q.put(("error", f"Training error: {e}"))

