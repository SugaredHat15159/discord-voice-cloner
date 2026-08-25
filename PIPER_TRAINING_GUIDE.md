# Piper Voice Training — Portable Guide

Train a Piper voice clone on any PC with WSL (Ubuntu). Assumes you've emailed
the dataset over and WSL/Ubuntu is already installed on the machine.

The dataset folder from the app looks like:
    <speaker>/
      wav/            <- the .wav clips
      metadata.csv    <- id|transcript per line

Replace `alex` below with your speaker name everywhere.

--------------------------------------------------------------------------------
## 0. Put the dataset somewhere WSL can read it

Say you saved the emailed dataset to  C:\Users\<you>\Downloads\alex
From WSL that path is:  /mnt/c/Users/<you>/Downloads/alex

Set a variable so the rest is copy-paste (edit the path to match yours):

    DS=/mnt/c/Users/$USER/Downloads/alex
    ls "$DS"        # should show: metadata.csv  wav

--------------------------------------------------------------------------------
## 1. One-time setup (only on a fresh WSL)

    sudo apt-get update
    sudo apt-get install -y build-essential cmake ninja-build python3-venv python3-pip git
    git clone https://github.com/OHF-voice/piper1-gpl.git
    cd piper1-gpl
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e '.[train]'
    pip install scikit-build torchaudio onnxscript
    bash build_monotonic_align.sh
    python3 setup.py build_ext --inplace

--------------------------------------------------------------------------------
## 2. Download a base checkpoint to fine-tune from (one-time)

Fine-tuning from a checkpoint is MUCH faster/better than from scratch.

    mkdir -p ~/checkpoints

Download an English medium checkpoint (the .ckpt file) from:
  https://huggingface.co/datasets/rhasspy/piper-checkpoints/tree/main/en/en_US/lessac/medium
Save it, then move it in as ~/checkpoints/base.ckpt
(If it's in Windows Downloads:  cp "/mnt/c/Users/$USER/Downloads/"epoch*.ckpt ~/checkpoints/base.ckpt )

--------------------------------------------------------------------------------
## 3. Normalize the metadata (each run, quick)

piper1-gpl wants:  filename.wav|text   with files in --data.audio_dir.
This rewrites the app's metadata.csv into that format:

    python3 - <<PY
    import os
    ds=os.environ["DS"]
    out=[]
    for line in open(ds+"/metadata.csv", encoding="utf-8"):
        line=line.rstrip("\n")
        if not line: continue
        p=line.split("|")
        name=os.path.basename(p[0]).strip()
        if not name.lower().endswith(".wav"): name+=".wav"
        out.append(f"{name}|{p[-1].strip()}")
    open(ds+"/metadata_piper.csv","w",encoding="utf-8").write("\n".join(out)+"\n")
    print("wrote metadata_piper.csv:", len(out), "lines")
    PY

Check it:  head -2 "$DS/metadata_piper.csv"

--------------------------------------------------------------------------------
## 4. Create the training launcher (each machine, once)

This wrapper handles the PyTorch-2.x quirks (safe checkpoint load, no worker
subprocesses, warmstart instead of resume). Edit the DS path inside if needed.

    cat > ~/train_voice.py <<'PY'
    import os, torch, pathlib
    torch.serialization.add_safe_globals([pathlib.PosixPath])
    _orig = torch.load
    def _patched(*a, **k):
        k.setdefault("weights_only", False)
        return _orig(*a, **k)
    torch.load = _patched

    DS   = os.environ.get("DS", "/mnt/c/Users/USER/Downloads/alex")
    NAME = os.environ.get("VOICE", "alex")
    EPOCHS = os.environ.get("EPOCHS", "2000")

    def run():
        from piper.train.__main__ import main
        import sys
        sys.argv = [
            "piper.train", "fit",
            "--data.voice_name", NAME,
            "--data.csv_path", f"{DS}/metadata_piper.csv",
            "--data.audio_dir", f"{DS}/wav",
            "--model.sample_rate", "22050",
            "--data.espeak_voice", "en-us",
            "--data.cache_dir", os.path.expanduser(f"~/piper_cache_{NAME}"),
            "--data.config_path", os.path.expanduser(f"~/{NAME}.config.json"),
            "--data.batch_size", "8",
            "--data.num_workers", "0",
            "--trainer.accelerator", "cpu",
            "--trainer.max_epochs", EPOCHS,
            "--model.warmstart_ckpt", os.path.expanduser("~/checkpoints/base.ckpt"),
        ]
        main()

    if __name__ == "__main__":
        run()
    PY

--------------------------------------------------------------------------------
## 5. Fix the ONNX export step (one-time, per machine)

Newer torch defaults to a broken exporter for this model. Force the legacy one:

    cd ~/piper1-gpl
    python3 - <<PY
    f="src/piper/train/export_onnx.py"
    s=open(f).read()
    if "dynamo=" not in s:
        s=s.replace("torch.onnx.export(\n", "torch.onnx.export(\n        dynamo=False,\n", 1)
        open(f,"w").write(s)
        print("patched exporter")
    else:
        print("already patched")
    PY

--------------------------------------------------------------------------------
## 6. TRAIN  (this is the long part — leave it running)

    cd ~/piper1-gpl
    source .venv/bin/activate
    export DS=/mnt/c/Users/$USER/Downloads/alex     # edit to your path
    export VOICE=alex
    export EPOCHS=2000
    python3 ~/train_voice.py

- It saves checkpoints to  ~/piper1-gpl/lightning_logs/version_*/checkpoints/
- ~25-30 sec/epoch on CPU. More epochs = closer to the voice.
- Stop anytime with Ctrl+C (once) — saved checkpoints are safe.
- To run for hours unattended, that's fine; just leave the terminal open.

TIP: to keep it running even if the terminal closes, start it with:
    nohup python3 ~/train_voice.py > ~/train.log 2>&1 &
then watch progress with:  tail -f ~/train.log
(stop it later with:  pkill -f train_voice.py )

--------------------------------------------------------------------------------
## 7. Export the trained model to .onnx

Find the best checkpoint (highest val_mos):

    ls -t ~/piper1-gpl/lightning_logs/version_*/checkpoints/*.ckpt | head -5

Export it (paste the path, keep the quotes — filenames contain '='):

    cd ~/piper1-gpl && source .venv/bin/activate
    python3 -m piper.train.export_onnx \
      --checkpoint "PASTE_BEST_CKPT_PATH_HERE" \
      --output-file ~/alex.onnx

--------------------------------------------------------------------------------
## 8. Get the two files back to your main PC

You need BOTH:
  ~/alex.onnx            (the model)
  ~/alex.config.json     (written during training)

Copy them to Windows so you can email/USB them back:

    cp ~/alex.onnx        /mnt/c/Users/$USER/Downloads/model.onnx
    cp ~/alex.config.json /mnt/c/Users/$USER/Downloads/model.onnx.json

On your MAIN PC, put both into:
    discord-voice-cloner\trained_models\alex\
        model.onnx
        model.onnx.json
Then: app -> Voice (TTS) tab -> Load Trained -> alex.

--------------------------------------------------------------------------------
## 9. Clean up the other PC when done (reclaim ~15-20 GB)

If you might train again, keep piper1-gpl; just clear caches:
    rm -rf ~/.cache/pip ~/.cache/torch ~/piper_cache_*

If you're fully done, nuke everything from PowerShell on that PC:
    wsl --shutdown
    wsl --unregister Ubuntu

--------------------------------------------------------------------------------
## Notes
- Storage: the INSTALL is the bulk (~10 GB venv). Training adds ~3-5 GB of
  checkpoints. The dataset + final .onnx are tiny (< 100 MB).
- Better voice = clean transcripts + more epochs. Fix metadata.csv so the text
  exactly matches each clip before a real run.
- Multi-speaker not needed here — one voice per dataset folder.
