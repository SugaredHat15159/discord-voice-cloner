# Discord Voice Cloner + Soundboard

Capture Discord voice-chat audio, auto-transcribe it, build a Piper-ready
dataset, run a soundboard through a virtual mic, and speak with a trained
Piper voice - all from one app. **Only clone voices of people who have agreed.**

## Features
- **Capture**: rolling buffer; a global hotkey (Ctrl+Shift+C) saves the last N seconds. Auto-transcribes with faster-whisper.
- **Record Now**: fixed-length recording for reading prompts in your own voice.
- **Soundboard**: mic passthrough + play sounds into a virtual cable; volume/gain slider (past 100% = peaked).
- **Training**: export a per-speaker Piper dataset (wav + metadata.csv). GPU training runs on Colab.
- **Voice (TTS)**: type text, synthesize with a Piper model, and play it into Discord like a soundboard clip.
- **Auto-update**: pulls your git repo on launch.

## Install (Windows + conda)
```
git clone <your-repo-url> discord-voice-cloner
cd discord-voice-cloner
install.bat
```
Then run:
```
conda activate discord-voice-cloner
python run.py
```

## Prerequisites
- **Stereo Mix** (to capture Discord audio): Sound settings -> Recording -> enable Stereo Mix. In Discord set Output to your Realtek device.
- **VB-CABLE** (for the soundboard / TTS-into-Discord): https://vb-audio.com/Cable/
  In the app pick your mic + `CABLE Input`; in Discord set Input to `CABLE Output`.
  Your mic only reaches Discord while the mixer is running.

## Auto-update
Runs from a git clone. On launch `run.py` does `git pull --ff-only`; if anything
changed it reloads. Toggle it in Settings.

## Training (Colab)
Export a dataset here, upload `dataset/<speaker>/` to a Colab notebook with a GPU,
fine-tune Piper, download the `.onnx` + `.onnx.json`, and load them on the Voice (TTS) tab.

## Notes
- Stereo Mix mixes ALL system audio - capture clean, single-speaker moments.
- Real-time Python mixing has some latency; VB-Audio Voicemeeter is a sturdier alternative for heavy soundboard use.
