"""Main GUI: ties capture, soundboard, training, TTS and settings together."""
import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

from .config import (CAPTURE_HOTKEY, DEFAULT_BUFFER_SECONDS, CLIPS_DIR, SOUNDS_DIR, ensure_dirs)
from .theme import apply_theme
from . import audio_utils, storage, updater, dataset, tts, recorder
from .capture import AudioEngine
from .transcribe import Transcriber
from .mixer import MixerEngine

try:
    import winsound
    HAVE_WINSOUND = True
except ImportError:
    HAVE_WINSOUND = False


class App:
    def __init__(self, root):
        self.root = root
        root.title("Discord Voice Cloner")
        root.geometry("1000x680")
        root.minsize(880, 560)
        self.p = apply_theme(root)
        ensure_dirs()

        self.q = queue.Queue()
        self.settings = storage.load_settings()
        self.index = storage.load_index()
        self.engine = AudioEngine(self.q)
        self.transcriber = Transcriber(self.q)
        self.mixer = MixerEngine(self.q)
        self.hotkey_listener = None

        # shared toggle vars
        self.auto_transcribe = tk.BooleanVar(value=self.settings.get("auto_transcribe", True))
        self.enable_capture_hotkey = tk.BooleanVar(value=self.settings.get("enable_capture_hotkey", True))
        self.enable_sound_hotkeys = tk.BooleanVar(value=self.settings.get("enable_sound_hotkeys", True))

        self._build_header()
        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.tab_capture = ttk.Frame(nb); nb.add(self.tab_capture, text="  Capture  ")
        self.tab_board = ttk.Frame(nb);   nb.add(self.tab_board, text="  Soundboard  ")
        self.tab_train = ttk.Frame(nb);   nb.add(self.tab_train, text="  Training  ")
        self.tab_tts = ttk.Frame(nb);     nb.add(self.tab_tts, text="  Voice (TTS)  ")
        self.tab_pitch = ttk.Frame(nb);   nb.add(self.tab_pitch, text="  Pitch  ")
        self.tab_set = ttk.Frame(nb);     nb.add(self.tab_set, text="  Settings  ")

        self.status_var = tk.StringVar(value=f"Ready.   Capture hotkey: {CAPTURE_HOTKEY}")
        ttk.Label(root, textvariable=self.status_var, style="Status.TLabel",
                  anchor="w").pack(fill="x", side="bottom")

        self._build_capture_tab()
        self._build_board_tab()
        self._build_train_tab()
        self._build_tts_tab()
        self._build_pitch_tab()
        self._build_settings_tab()

        self._refresh_devices()
        self._refresh_clip_list()
        self._scan_sound_folder()
        self._update_hotkey_listener()

        self.root.after(120, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- header ----------
    def _build_header(self):
        h = tk.Frame(self.root, bg=self.p["header"])
        h.pack(fill="x")
        tk.Label(h, text="Discord Voice Cloner", bg=self.p["header"], fg="#ffffff",
                 font=("Segoe UI Semibold", 16)).pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(h, text="Capture \u2022 Transcribe \u2022 Soundboard \u2022 Train \u2022 Speak",
                 bg=self.p["header"], fg="#dfe1ff",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(0, 12))

    # ---------- capture tab ----------
    def _build_capture_tab(self):
        t = self.tab_capture
        top = ttk.Frame(t, padding=12); top.pack(fill="x")
        ttk.Label(top, text="Audio device").grid(row=0, column=0, sticky="w")
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(top, textvariable=self.device_var, width=46, state="readonly")
        self.device_combo.grid(row=0, column=1, padx=6, sticky="w")
        ttk.Button(top, text="Refresh", command=self._refresh_devices).grid(row=0, column=2, padx=4)
        ttk.Label(top, text="Buffer (sec)").grid(row=1, column=0, sticky="w", pady=6)
        self.buffer_var = tk.IntVar(value=DEFAULT_BUFFER_SECONDS)
        ttk.Spinbox(top, from_=3, to=60, textvariable=self.buffer_var, width=6).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(top, text="Speaker").grid(row=2, column=0, sticky="w")
        self.speaker_var = tk.StringVar(value="friend1")
        ttk.Entry(top, textvariable=self.speaker_var, width=22).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Checkbutton(top, text="Auto-transcribe new clips",
                        variable=self.auto_transcribe).grid(row=2, column=2, sticky="w", padx=6)
        self.monitor_btn = ttk.Button(top, text="Start Monitoring", style="Accent.TButton",
                                      command=self._toggle_monitor)
        self.monitor_btn.grid(row=0, column=3, rowspan=2, padx=12)

        mid = ttk.Frame(t, padding=(12, 0)); mid.pack(fill="both", expand=True)
        cols = ("time", "speaker", "dur", "status", "transcript")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended")
        for c, w, lbl in [("time", 130, "Time"), ("speaker", 90, "Speaker"),
                          ("dur", 55, "Dur"), ("status", 80, "Status"),
                          ("transcript", 470, "Transcript")]:
            self.tree.heading(c, text=lbl); self.tree.column(c, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y"); self.tree.configure(yscrollcommand=sb.set)

        bar = ttk.Frame(t, padding=12); bar.pack(fill="x")
        ttk.Button(bar, text="Record Now", command=self._record_fixed).pack(side="left", padx=3)
        ttk.Button(bar, text="Play", command=self._play_selected).pack(side="left", padx=3)
        ttk.Button(bar, text="Edit Transcript", command=self._edit_transcript).pack(side="left", padx=3)
        ttk.Button(bar, text="Transcribe Selected", command=self._transcribe_selected).pack(side="left", padx=3)
        ttk.Button(bar, text="Transcribe Pending", command=self._transcribe_pending).pack(side="left", padx=3)
        ttk.Button(bar, text="Delete", style="Danger.TButton", command=self._delete_selected).pack(side="right", padx=3)

    # ---------- soundboard tab ----------
    def _build_board_tab(self):
        t = self.tab_board
        top = ttk.Frame(t, padding=12); top.pack(fill="x")
        ttk.Label(top, text="Your mic").grid(row=0, column=0, sticky="w")
        self.mic_var = tk.StringVar()
        self.mic_combo = ttk.Combobox(top, textvariable=self.mic_var, width=44, state="readonly")
        self.mic_combo.grid(row=0, column=1, padx=6, sticky="w")
        ttk.Label(top, text="Virtual cable out").grid(row=1, column=0, sticky="w", pady=6)
        self.cable_var = tk.StringVar()
        self.cable_combo = ttk.Combobox(top, textvariable=self.cable_var, width=44, state="readonly")
        self.cable_combo.grid(row=1, column=1, padx=6, sticky="w")
        self.monitor_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Also hear it myself (monitor)",
                        variable=self.monitor_var).grid(row=2, column=1, sticky="w")
        self.mixer_btn = ttk.Button(top, text="Start Mixer", style="Accent.TButton",
                                    command=self._toggle_mixer)
        self.mixer_btn.grid(row=0, column=2, rowspan=2, padx=12)

        g1 = ttk.Frame(t, padding=(12, 2)); g1.pack(fill="x")
        ttk.Label(g1, text="My mic volume", width=16).pack(side="left")
        self.mic_gain_var = tk.IntVar(value=self.settings.get("mic_gain", 100))
        ttk.Scale(g1, from_=0, to=300, orient="horizontal", variable=self.mic_gain_var,
                  command=self._on_mic_gain).pack(side="left", fill="x", expand=True, padx=10)
        self.mic_gain_lbl = ttk.Label(g1, text=f"{self.mic_gain_var.get()}%", width=6)
        self.mic_gain_lbl.pack(side="left")

        g2 = ttk.Frame(t, padding=(12, 2)); g2.pack(fill="x")
        ttk.Label(g2, text="Soundboard volume", width=16).pack(side="left")
        self.sound_gain_var = tk.IntVar(value=self.settings.get("sound_gain", 100))
        ttk.Scale(g2, from_=0, to=300, orient="horizontal", variable=self.sound_gain_var,
                  command=self._on_sound_gain).pack(side="left", fill="x", expand=True, padx=10)
        self.sound_gain_lbl = ttk.Label(g2, text=f"{self.sound_gain_var.get()}%", width=6)
        self.sound_gain_lbl.pack(side="left")
        ttk.Label(t, style="Muted.TLabel", padding=(12, 0),
                  text="(>100% = peaked. Mic and sounds mix together, so you can talk over sounds.)").pack(anchor="w")

        mid = ttk.Frame(t, padding=12); mid.pack(fill="both", expand=True)
        self.sound_list = tk.Listbox(mid, selectmode="browse", relief="flat",
                                     bg=self.p["field"], highlightthickness=1,
                                     highlightbackground="#d7d9de", font=("Segoe UI", 10))
        self.sound_list.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.sound_list.yview)
        sb.pack(side="right", fill="y"); self.sound_list.configure(yscrollcommand=sb.set)

        bar = ttk.Frame(t, padding=12); bar.pack(fill="x")
        ttk.Button(bar, text="Add Sound", command=self._add_sound).pack(side="left", padx=3)
        ttk.Button(bar, text="Open Folder", command=self._open_sound_folder).pack(side="left", padx=3)
        ttk.Button(bar, text="Rescan", command=self._scan_sound_folder).pack(side="left", padx=3)
        ttk.Button(bar, text="Remove", style="Danger.TButton", command=self._remove_sound).pack(side="left", padx=3)
        ttk.Button(bar, text="Play into Discord", style="Accent.TButton", command=self._play_sound).pack(side="left", padx=3)
        ttk.Button(bar, text="Stop Sounds", command=self.mixer.stop_all_sounds).pack(side="left", padx=3)
        ttk.Button(bar, text="Set Hotkey", command=self._set_sound_hotkey).pack(side="left", padx=3)
        ttk.Button(bar, text="Clear Hotkey", command=self._clear_sound_hotkey).pack(side="left", padx=3)

    # ---------- training tab ----------
    def _build_train_tab(self):
        f = ttk.Frame(self.tab_train, padding=16); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Export dataset for training", style="Title.TLabel").pack(anchor="w")
        msg = (
            "Export a speaker's transcribed clips into a Piper dataset "
            "(dataset/<speaker>/wav + metadata.csv).\n\n"
            "Training runs in WSL/Linux - see PIPER_TRAINING_GUIDE.md. "
            "Copy the finished model.onnx + model.onnx.json into "
            "trained_models/<speaker>/ then load it on the Voice (TTS) tab."
        )
        ttk.Label(f, justify="left", style="Muted.TLabel", wraplength=620, text=msg).pack(anchor="w", pady=8)
        ttk.Button(f, text="Export Piper Dataset", style="Accent.TButton",
                   command=self._export_dataset).pack(anchor="w", pady=4)
        self.train_status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.train_status, wraplength=620, justify="left").pack(anchor="w", pady=6)

    def _build_tts_tab(self):
        f = ttk.Frame(self.tab_tts, padding=16); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Speak with a Piper voice", style="Title.TLabel").pack(anchor="w")
        row = ttk.Frame(f); row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text="Model (.onnx)").pack(side="left")
        self.tts_model_var = tk.StringVar(value=self.settings.get("tts_model", ""))
        ttk.Entry(row, textvariable=self.tts_model_var, width=46).pack(side="left", padx=6)
        ttk.Button(row, text="Browse", command=self._tts_pick_model).pack(side="left", padx=1)
        ttk.Button(row, text="Load Trained", command=self._tts_load_trained).pack(side="left", padx=1)
        ttk.Label(f, text="Text").pack(anchor="w", pady=(10, 2))
        self.tts_text = tk.Text(f, height=5, wrap="word", relief="flat",
                                bg=self.p["field"], highlightthickness=1,
                                highlightbackground="#d7d9de", font=("Segoe UI", 10))
        self.tts_text.pack(fill="x")
        bar = ttk.Frame(f); bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="Speak into Discord", style="Accent.TButton",
                   command=self._tts_speak_discord).pack(side="left", padx=3)
        ttk.Button(bar, text="Play to Speakers", command=self._tts_play_local).pack(side="left", padx=3)
        ttk.Label(f, style="Muted.TLabel", wraplength=640, justify="left", text=(
            "The model's .onnx.json config must sit beside the .onnx file. "
            "'Speak into Discord' routes through the Soundboard mixer, so start the mixer first."
        )).pack(anchor="w", pady=4)

    def _hotkey_toggle_pitch(self):
        self.pitch_enabled_var.set(not self.pitch_enabled_var.get())
        self._on_pitch_toggle()

    # ---------- pitch tab ----------
    def _build_pitch_tab(self):
        f = ttk.Frame(self.tab_pitch, padding=16); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Voice pitch modulator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, style="Muted.TLabel", wraplength=620, justify="left", text=(
            "Shifts your mic pitch in real time (routes through the Soundboard mixer, "
            "so start the mixer to use it in Discord). Small shifts sound natural; "
            "big shifts get chipmunk/demon character."
        )).pack(anchor="w", pady=(4, 10))

        self.pitch_enabled_var = tk.BooleanVar(value=self.settings.get("pitch_enabled", False))
        ttk.Checkbutton(f, text="Pitch shifting ON", variable=self.pitch_enabled_var,
                        command=self._on_pitch_toggle).pack(anchor="w")

        row = ttk.Frame(f); row.pack(fill="x", pady=8)
        ttk.Label(row, text="Semitones", width=10).pack(side="left")
        self.pitch_var = tk.DoubleVar(value=self.settings.get("pitch_semitones", 0))
        ttk.Scale(row, from_=-12, to=12, orient="horizontal", variable=self.pitch_var,
                  command=self._on_pitch_change).pack(side="left", fill="x", expand=True, padx=10)
        self.pitch_lbl = ttk.Label(row, text=f"{int(self.pitch_var.get())}", width=5)
        self.pitch_lbl.pack(side="left")

        pf = ttk.Labelframe(f, text="Presets", padding=10); pf.pack(fill="both", expand=True, pady=10)
        self.pitch_preset_list = tk.Listbox(pf, height=8, relief="flat", bg=self.p["field"],
                                            highlightthickness=1, highlightbackground="#d7d9de",
                                            font=("Segoe UI", 10))
        self.pitch_preset_list.pack(side="left", fill="both", expand=True)
        self.pitch_preset_list.bind("<<ListboxSelect>>", self._on_pitch_preset_pick)
        sb = ttk.Scrollbar(pf, orient="vertical", command=self.pitch_preset_list.yview)
        sb.pack(side="right", fill="y"); self.pitch_preset_list.configure(yscrollcommand=sb.set)

        bar = ttk.Frame(f); bar.pack(fill="x")
        ttk.Button(bar, text="Save current as preset", command=self._pitch_save_preset).pack(side="left", padx=3)
        ttk.Button(bar, text="Delete preset", style="Danger.TButton",
                   command=self._pitch_delete_preset).pack(side="left", padx=3)
        ttk.Label(bar, style="Muted.TLabel",
                  text="Hotkeys for pitch are on the Settings tab.").pack(side="right")

        self._refresh_pitch_presets()

    def _refresh_pitch_presets(self):
        self.pitch_preset_list.delete(0, "end")
        for name, semi in self.settings.get("pitch_presets", {}).items():
            self.pitch_preset_list.insert("end", f"{name}   ({semi:+g})")

    def _on_pitch_toggle(self):
        on = self.pitch_enabled_var.get()
        self.settings["pitch_enabled"] = on
        storage.save_settings(self.settings)
        self.mixer.set_pitch_semitones(self.pitch_var.get() if on else 0)
        self.status_var.set(f"Pitch shifting {'ON' if on else 'OFF'}.")

    def _on_pitch_change(self, _=None):
        semi = int(float(self.pitch_var.get()))
        self.pitch_lbl.config(text=str(semi))
        self.settings["pitch_semitones"] = semi
        storage.save_settings(self.settings)
        if self.pitch_enabled_var.get():
            self.mixer.set_pitch_semitones(semi)

    def _on_pitch_preset_pick(self, _=None):
        sel = self.pitch_preset_list.curselection()
        if not sel:
            return
        name = list(self.settings.get("pitch_presets", {}).keys())[sel[0]]
        self._apply_pitch_preset(name)

    def _apply_pitch_preset(self, name):
        presets = self.settings.get("pitch_presets", {})
        if name not in presets:
            return
        semi = presets[name]
        self.pitch_var.set(semi)
        self.pitch_lbl.config(text=str(int(semi)))
        self.settings["pitch_semitones"] = semi
        storage.save_settings(self.settings)
        if self.pitch_enabled_var.get():
            self.mixer.set_pitch_semitones(semi)
        self.status_var.set(f"Pitch preset: {name} ({semi:+g})")

    def _pitch_save_preset(self):
        name = simpledialog.askstring("Save preset", "Preset name:")
        if not name:
            return
        self.settings.setdefault("pitch_presets", {})[name] = int(float(self.pitch_var.get()))
        storage.save_settings(self.settings)
        self._refresh_pitch_presets()

    def _pitch_delete_preset(self):
        sel = self.pitch_preset_list.curselection()
        if not sel:
            return
        name = list(self.settings.get("pitch_presets", {}).keys())[sel[0]]
        self.settings.get("pitch_presets", {}).pop(name, None)
        storage.save_settings(self.settings)
        self._refresh_pitch_presets()
        self._update_hotkey_listener()

        # ---------- settings tab ----------
    def _build_settings_tab(self):
        f = ttk.Frame(self.tab_set, padding=16); f.pack(fill="both", expand=True)

        tg = ttk.Labelframe(f, text="Toggles", padding=10); tg.pack(fill="x", pady=(0, 12))
        ttk.Checkbutton(tg, text="Auto-transcribe new clips",
                        variable=self.auto_transcribe, command=self._save_prefs).pack(anchor="w")
        ttk.Checkbutton(tg, text="Capture hotkey (Ctrl+Shift+C) while monitoring",
                        variable=self.enable_capture_hotkey, command=self._on_toggle_hotkeys).pack(anchor="w")
        ttk.Checkbutton(tg, text="Soundboard hotkeys (Ctrl+Alt+1..9) while mixer runs",
                        variable=self.enable_sound_hotkeys, command=self._on_toggle_hotkeys).pack(anchor="w")

        kbf = ttk.Labelframe(f, text="Keybinds", padding=10); kbf.pack(fill="x", pady=(0, 12))
        self.kb_vars = {}
        for action, label in [("capture", "Grab clip"), ("stop_sounds", "Stop sounds"), ("pitch_toggle", "Toggle pitch")]:
            row = ttk.Frame(kbf); row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=14).pack(side="left")
            var = tk.StringVar(); self.kb_vars[action] = var
            ttk.Label(row, textvariable=var, width=22).pack(side="left")
            ttk.Button(row, text="Set", command=lambda a=action: self._set_action_hotkey(a)).pack(side="left", padx=3)
            ttk.Button(row, text="Clear", command=lambda a=action: self._clear_action_hotkey(a)).pack(side="left")
        ttk.Label(kbf, style="Muted.TLabel",
                  text="Per-sound hotkeys: Soundboard tab -> pick a sound -> Set Hotkey.").pack(anchor="w", pady=(6, 0))

        prow = ttk.Frame(kbf); prow.pack(fill="x", pady=(8, 0))
        ttk.Label(prow, text="Pitch preset", width=14).pack(side="left")
        self.pitch_bind_combo = ttk.Combobox(prow, width=18, state="readonly")
        self.pitch_bind_combo.pack(side="left", padx=4)
        ttk.Button(prow, text="Set", command=self._set_pitch_preset_hotkey).pack(side="left", padx=3)
        ttk.Button(prow, text="Clear", command=self._clear_pitch_preset_hotkey).pack(side="left")
        self._refresh_pitch_bind_combo()
        self._refresh_keybind_labels()

        up = ttk.Labelframe(f, text="Updates", padding=10); up.pack(fill="x")
        self.auto_update_var = tk.BooleanVar(value=self.settings.get("auto_update", True))
        ttk.Checkbutton(up, text="Auto-update from git on launch",
                        variable=self.auto_update_var, command=self._save_prefs).pack(anchor="w")
        self.git_status = tk.StringVar(value=self._git_status_text())
        ttk.Label(up, textvariable=self.git_status, style="Muted.TLabel").pack(anchor="w", pady=6)
        row = ttk.Frame(up); row.pack(anchor="w")
        ttk.Button(row, text="Check for Updates", command=self._manual_update).pack(side="left", padx=3)
        ttk.Button(row, text="Restart App", command=self._restart).pack(side="left", padx=3)

    def _git_status_text(self):
        if updater.git_available():
            return f"Git repo detected. Version: {updater.current_commit()}"
        return "No git repo detected. Clone from your GitHub repo to enable updates."

    # ---------- devices ----------
    def _refresh_devices(self):
        self.in_devices = audio_utils.list_input_devices()
        self.out_devices = audio_utils.list_output_devices()
        in_labels = [f"[{i}] {n} ({c}ch)" for (i, n, c) in self.in_devices]
        out_labels = [f"[{i}] {n} ({c}ch)" for (i, n, c) in self.out_devices]
        self.device_combo["values"] = in_labels
        self._auto_select(self.device_combo, in_labels,
                          ["stereo mix", "what u hear", "cable output", "loopback"])
        self.mic_combo["values"] = in_labels
        self._auto_select(self.mic_combo, in_labels, ["realtek hd audio mic", "microphone (realtek"])
        self.cable_combo["values"] = out_labels
        self._auto_select(self.cable_combo, out_labels, ["cable input"])

    def _auto_select(self, combo, labels, keywords):
        for idx, lbl in enumerate(labels):
            if any(k in lbl.lower() for k in keywords):
                combo.current(idx); return
        if labels and combo.current() < 0:
            combo.current(0)

    def _sel_in(self, combo):
        i = combo.current()
        return self.in_devices[i] if i >= 0 else None

    def _sel_out(self, combo):
        i = combo.current()
        return self.out_devices[i] if i >= 0 else None

    # ---------- monitoring ----------
    def _toggle_monitor(self):
        if self.engine.running:
            self.engine.stop()
            self.monitor_btn.config(text="Start Monitoring")
            self.status_var.set("Monitoring stopped.")
        else:
            dev = self._sel_in(self.device_combo)
            if not dev:
                messagebox.showerror("No device", "Pick an audio device."); return
            if self.engine.start(dev[0], dev[2], self.buffer_var.get()):
                self.monitor_btn.config(text="Stop Monitoring")
        self._update_hotkey_listener()

    # ---------- mixer ----------
    def _toggle_mixer(self):
        if self.mixer.running:
            self.mixer.stop()
            self.mixer_btn.config(text="Start Mixer")
            self.status_var.set("Mixer stopped (your mic no longer routed).")
            self._update_hotkey_listener()
            return
        mic = self._sel_in(self.mic_combo)
        cable = self._sel_out(self.cable_combo)
        if not mic or not cable:
            messagebox.showerror("Devices", "Pick both your mic and the virtual cable output."); return
        mon = audio_utils.default_output_index() if self.monitor_var.get() else None
        self.mixer.set_mic_gain_percent(self.mic_gain_var.get())
        self.mixer.set_sound_gain_percent(self.sound_gain_var.get())
        self.mixer.set_pitch_semitones(self.settings.get('pitch_semitones', 0) if self.settings.get('pitch_enabled') else 0)
        if self.mixer.start(mic[0], cable[0], mon):
            self.mixer_btn.config(text="Stop Mixer")
        self._update_hotkey_listener()

    def _on_mic_gain(self, _=None):
        pct = int(float(self.mic_gain_var.get()))
        self.mic_gain_lbl.config(text=f"{pct}%")
        self.mixer.set_mic_gain_percent(pct)
        self.settings["mic_gain"] = pct; storage.save_settings(self.settings)

    def _on_sound_gain(self, _=None):
        pct = int(float(self.sound_gain_var.get()))
        self.sound_gain_lbl.config(text=f"{pct}%")
        self.mixer.set_sound_gain_percent(pct)
        self.settings["sound_gain"] = pct; storage.save_settings(self.settings)

    # ---------- sounds ----------
    def _refresh_sound_list(self):
        self.sound_list.delete(0, "end")
        binds = self.settings.get("sound_binds", {})
        for pth in self.settings.get("sounds", []):
            name = os.path.basename(pth)
            hk = binds.get(pth)
            self.sound_list.insert("end", f"{name}    [{hk}]" if hk else name)

    def _open_sound_folder(self):
        folder = os.path.abspath(SOUNDS_DIR)
        os.makedirs(folder, exist_ok=True)
        try:
            os.startfile(folder)          # Windows: open in Explorer
        except Exception:
            self.status_var.set(f"Drop sounds into: {folder}")

    def _scan_sound_folder(self):
        exts = (".wav", ".mp3", ".ogg", ".flac")
        folder = os.path.abspath(SOUNDS_DIR)
        os.makedirs(folder, exist_ok=True)
        sounds = self.settings.setdefault("sounds", [])
        existing = {os.path.abspath(p) for p in sounds}
        try:
            for name in sorted(os.listdir(folder)):
                if name.lower().endswith(exts):
                    ap = os.path.join(folder, name)
                    if ap not in existing:
                        sounds.append(ap); existing.add(ap)
        except Exception:
            pass
        # prune files that were deleted out of the folder
        kept = []
        for p in sounds:
            ap = os.path.abspath(p)
            if ap.startswith(folder + os.sep) and not os.path.exists(ap):
                self.settings.get("sound_binds", {}).pop(p, None)
                continue
            kept.append(p)
        self.settings["sounds"] = kept
        storage.save_settings(self.settings)
        self._refresh_sound_list()
        self._update_hotkey_listener()

    def _add_sound(self):
        path = filedialog.askopenfilename(title="Add sound",
                                          filetypes=[("Audio", "*.wav *.mp3 *.ogg *.flac"), ("All", "*.*")])
        if path:
            self.settings.setdefault("sounds", []).append(path)
            storage.save_settings(self.settings)
            self._refresh_sound_list(); self._update_hotkey_listener()

    def _remove_sound(self):
        sel = self.sound_list.curselection()
        if not sel:
            return
        del self.settings["sounds"][sel[0]]
        storage.save_settings(self.settings)
        self._refresh_sound_list(); self._update_hotkey_listener()

    def _play_sound(self, idx=None):
        sounds = self.settings.get("sounds", [])
        if idx is None:
            sel = self.sound_list.curselection()
            if not sel:
                return
            idx = sel[0]
        if idx >= len(sounds):
            return
        self._play_path(sounds[idx])

    def _play_path(self, path):
        if not self.mixer.running:
            self.status_var.set("Start the mixer first - sounds only play once the mixer is running.")
            return
        self.mixer.trigger(path)

    # ---------- hotkeys ----------
    def _update_hotkey_listener(self):
        from pynput import keyboard
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
            self.hotkey_listener = None
        mapping = {}

        def add(hk, fn):
            if not hk:
                return
            try:
                keyboard.HotKey.parse(hk)   # validate
            except Exception:
                self.q.put(("error", f"Ignoring invalid hotkey: {hk}"))
                return
            mapping[hk] = fn

        kb = self.settings.get("keybinds", {})
        if self.engine.running and self.enable_capture_hotkey.get():
            add(kb.get("capture", CAPTURE_HOTKEY),
                lambda: self.engine.save_last_clip(self.speaker_var.get()))
        if self.mixer.running:
            add(kb.get("stop_sounds", ""), self.mixer.stop_all_sounds)
            add(kb.get("pitch_toggle", ""), self._hotkey_toggle_pitch)
            for pname, pk in self.settings.get("pitch_preset_binds", {}).items():
                add(pk, (lambda n=pname: self._apply_pitch_preset(n)))
            for path, hk in self.settings.get("sound_binds", {}).items():
                add(hk, (lambda p=path: self._play_path(p)))
            if self.enable_sound_hotkeys.get():
                sounds = self.settings.get("sounds", [])
                bound = set(self.settings.get("sound_binds", {}).values())
                for n in range(1, 10):
                    hk = f"<ctrl>+<alt>+{n}"
                    if n - 1 < len(sounds) and hk not in bound:
                        add(hk, (lambda i=n - 1: self._play_sound(i)))
        if mapping:
            # Build resiliently: if one hotkey is malformed, drop just that one
            # instead of letting it kill the whole listener (which used to break
            # all the sound binds after the pitch update).
            good = {}
            for hk, fn in mapping.items():
                try:
                    test = keyboard.GlobalHotKeys({hk: fn})
                    test.stop()
                    good[hk] = fn
                except Exception:
                    self.q.put(("error", f"Skipping bad hotkey: {hk}"))
            try:
                self.hotkey_listener = keyboard.GlobalHotKeys(good)
                self.hotkey_listener.start()
            except Exception as e:
                self.q.put(("error", f"Hotkey setup failed: {e}"))
                self.hotkey_listener = None

    # ---------- hotkey capture / binding ----------
    def _capture_hotkey(self, on_done):
        from pynput import keyboard
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
            self.hotkey_listener = None
        win = tk.Toplevel(self.root)
        win.title("Set hotkey"); win.geometry("360x120"); win.configure(bg=self.p["bg"])
        win.transient(self.root); win.grab_set()
        ttk.Label(win, text="Press the key or combo you want.\n(Esc to cancel)",
                  justify="center").pack(pady=18)
        mods = []
        MOD = {
            keyboard.Key.ctrl: "<ctrl>", keyboard.Key.ctrl_l: "<ctrl>", keyboard.Key.ctrl_r: "<ctrl>",
            keyboard.Key.alt: "<alt>", keyboard.Key.alt_l: "<alt>", keyboard.Key.alt_r: "<alt>",
            keyboard.Key.alt_gr: "<alt>",
            keyboard.Key.shift: "<shift>", keyboard.Key.shift_l: "<shift>", keyboard.Key.shift_r: "<shift>",
            keyboard.Key.cmd: "<cmd>", keyboard.Key.cmd_l: "<cmd>", keyboard.Key.cmd_r: "<cmd>",
        }
        holder = {"l": None}

        def finish(hk):
            try:
                if holder["l"]:
                    holder["l"].stop()
            except Exception:
                pass
            if win.winfo_exists():
                win.destroy()
            if hk is not None:
                on_done(hk)
            self.root.after(60, self._update_hotkey_listener)

        def token(key):
            if isinstance(key, keyboard.KeyCode):
                if key.char and key.char.isprintable() and not key.char.isspace():
                    return key.char.lower()
                if key.vk is not None:
                    return f"<{key.vk}>"
                return None
            if isinstance(key, keyboard.Key):
                return f"<{key.name}>"
            return None

        def on_press(key):
            if key == keyboard.Key.esc:
                self.root.after(0, lambda: finish(None)); return False
            if key in MOD:
                if MOD[key] not in mods:
                    mods.append(MOD[key])
                return
            tok = token(key)
            if not tok:
                return
            order = {"<ctrl>": 0, "<alt>": 1, "<shift>": 2, "<cmd>": 3}
            parts = sorted(set(mods), key=lambda m: order.get(m, 9)) + [tok]
            hk = "+".join(parts)
            self.root.after(0, lambda: finish(hk)); return False

        def on_release(key):
            if key in MOD and MOD[key] in mods:
                try:
                    mods.remove(MOD[key])
                except ValueError:
                    pass

        holder["l"] = keyboard.Listener(on_press=on_press, on_release=on_release)
        holder["l"].start()
        win.protocol("WM_DELETE_WINDOW", lambda: finish(None))

    def _set_action_hotkey(self, action):
        def done(hk):
            self.settings.setdefault("keybinds", {})[action] = hk
            storage.save_settings(self.settings)
            self._refresh_keybind_labels()
        self._capture_hotkey(done)

    def _clear_action_hotkey(self, action):
        self.settings.setdefault("keybinds", {})[action] = ""
        storage.save_settings(self.settings)
        self._refresh_keybind_labels()
        self._update_hotkey_listener()

    def _refresh_keybind_labels(self):
        kb = self.settings.get("keybinds", {})
        for action, var in getattr(self, "kb_vars", {}).items():
            var.set(kb.get(action, "") or "(none)")

    def _refresh_pitch_bind_combo(self):
        names = list(self.settings.get("pitch_presets", {}).keys())
        self.pitch_bind_combo["values"] = names
        if names and not self.pitch_bind_combo.get():
            self.pitch_bind_combo.current(0)

    def _set_pitch_preset_hotkey(self):
        name = self.pitch_bind_combo.get()
        if not name:
            self.status_var.set("Pick a pitch preset first."); return
        def done(hk):
            self.settings.setdefault("pitch_preset_binds", {})[name] = hk
            storage.save_settings(self.settings)
            self.status_var.set(f"Bound {hk} -> pitch preset '{name}'")
        self._capture_hotkey(done)

    def _clear_pitch_preset_hotkey(self):
        name = self.pitch_bind_combo.get()
        if name:
            self.settings.get("pitch_preset_binds", {}).pop(name, None)
            storage.save_settings(self.settings)
            self._update_hotkey_listener()
            self.status_var.set(f"Cleared hotkey for '{name}'")

    def _set_sound_hotkey(self):
        sel = self.sound_list.curselection()
        if not sel:
            self.status_var.set("Select a sound first, then Set Hotkey."); return
        path = self.settings.get("sounds", [])[sel[0]]
        def done(hk):
            self.settings.setdefault("sound_binds", {})[path] = hk
            storage.save_settings(self.settings)
            self._refresh_sound_list()
        self._capture_hotkey(done)

    def _clear_sound_hotkey(self):
        sel = self.sound_list.curselection()
        if not sel:
            return
        path = self.settings.get("sounds", [])[sel[0]]
        self.settings.get("sound_binds", {}).pop(path, None)
        storage.save_settings(self.settings)
        self._refresh_sound_list()
        self._update_hotkey_listener()

    def _on_toggle_hotkeys(self):
        self._save_prefs()
        self._update_hotkey_listener()

    # ---------- recording own voice ----------
    def _record_fixed(self):
        dev = self._sel_in(self.device_combo)
        if not dev:
            messagebox.showerror("No device", "Pick an audio device (your mic for your own voice)."); return
        threading.Thread(target=recorder.record_fixed,
                         args=(self.q, dev[0], dev[2], self.buffer_var.get(), self.speaker_var.get()),
                         daemon=True).start()

    # ---------- clip ops ----------
    def _refresh_clip_list(self):
        self.tree.delete(*self.tree.get_children())
        seen = set()
        for c in self.index:
            fname = c.get("filename")
            if not fname or fname in seen:
                continue          # skip blanks / duplicates instead of crashing
            seen.add(fname)
            preview = (c.get("transcript", "") or "")[:80]
            try:
                self.tree.insert("", "end", iid=fname, values=(
                    c.get("timestamp", ""), c.get("speaker", ""), c.get("duration", ""),
                    c.get("status", ""), preview))
            except Exception:
                pass              # one bad row can never blank the whole list

    def _sel_files(self):
        return list(self.tree.selection())

    def _clip(self, fname):
        for c in self.index:
            if c["filename"] == fname:
                return c
        return None

    def _play_selected(self):
        sel = self._sel_files()
        if sel and HAVE_WINSOUND:
            winsound.PlaySound(os.path.join(CLIPS_DIR, sel[0]),
                               winsound.SND_FILENAME | winsound.SND_ASYNC)

    def _transcribe_one(self, fname):
        def worker():
            try:
                text = self.transcriber.transcribe_file(os.path.join(CLIPS_DIR, fname))
                self.q.put(("transcript", (fname, text)))
            except Exception as e:
                self.q.put(("error", f"Transcribe failed: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    def _transcribe_selected(self):
        for f in self._sel_files():
            self._transcribe_one(f)

    def _transcribe_pending(self):
        for c in self.index:
            if not c.get("transcript"):
                self._transcribe_one(c["filename"])

    def _edit_transcript(self):
        sel = self._sel_files()
        if not sel:
            return
        clip = self._clip(sel[0])
        if not clip:
            return
        win = tk.Toplevel(self.root)
        win.title(f"Edit - {sel[0]}")
        win.geometry("560x300")
        win.configure(bg=self.p["bg"])
        win.transient(self.root)
        win.grab_set()

        btns = ttk.Frame(win, padding=(10, 8))
        btns.pack(side="bottom", fill="x")

        txt = tk.Text(win, wrap="word", relief="flat", bg=self.p["field"],
                      highlightthickness=1, highlightbackground="#d7d9de", font=("Segoe UI", 11))
        txt.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 0))
        txt.insert("1.0", clip.get("transcript", ""))
        txt.focus_set()

        def save():
            clip["transcript"] = txt.get("1.0", "end").strip()
            clip["status"] = "done"
            storage.save_index(self.index)
            self._refresh_clip_list()
            win.destroy()

        ttk.Button(btns, text="Save", style="Accent.TButton", command=save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=6)

        win.bind("<Control-s>", lambda e: save())
        win.bind("<Escape>", lambda e: win.destroy())

    def _delete_selected(self):
        sel = self._sel_files()
        if not sel or not messagebox.askyesno("Delete", f"Delete {len(sel)} clip(s)?"):
            return
        for fname in sel:
            fpath = os.path.join(CLIPS_DIR, fname)
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass
            self.index = [c for c in self.index if c["filename"] != fname]
        storage.save_index(self.index); self._refresh_clip_list()

    # ---------- dataset ----------
    def _export_dataset(self):
        speakers = sorted({c.get("speaker", "unknown") for c in self.index if c.get("transcript")})
        if not speakers:
            messagebox.showinfo("Export", "No transcribed clips yet."); return
        speaker = simpledialog.askstring("Export", f"Speaker to export?\nAvailable: {', '.join(speakers)}",
                                         initialvalue=speakers[0])
        if not speaker:
            return
        threading.Thread(target=dataset.export_dataset, args=(self.q, self.index, speaker),
                         daemon=True).start()

    # ---------- tts ----------
    def _tts_load_trained(self):
        """Load a trained model from trained_models/<speaker>/"""
        import os
        trained_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trained_models")
        if not os.path.exists(trained_dir):
            messagebox.showinfo("No trained models", f"No 'trained_models' folder found.\nTrain a voice first on the Training tab.")
            return
        speakers = [d for d in os.listdir(trained_dir) if os.path.isdir(os.path.join(trained_dir, d))]
        if not speakers:
            messagebox.showinfo("No trained models", "No trained models found in trained_models/")
            return
        speaker = simpledialog.askstring("Load trained model", f"Available voices:\n{', '.join(speakers)}", initialvalue=speakers[0] if speakers else "")
        if not speaker:
            return
        model_path = os.path.join(trained_dir, speaker, "model.onnx")
        if os.path.exists(model_path):
            self.settings["tts_model"] = model_path
            storage.save_settings(self.settings)
            self.tts_model_var.set(model_path)
            self.status_var.set(f"Loaded trained voice: {speaker}")
        else:
            messagebox.showerror("Not found", f"model.onnx not found in trained_models/{speaker}/")

    def _tts_pick_model(self):
        p = filedialog.askopenfilename(title="Piper model",
                                       filetypes=[("ONNX", "*.onnx"), ("All", "*.*")])
        if p:
            self.settings["tts_model"] = p; storage.save_settings(self.settings)
            self.tts_model_var.set(p)

    def _tts_run(self, then_discord):
        def worker():
            try:
                out = tts.generate(self.settings.get("tts_model", ""),
                                   self.tts_text.get("1.0", "end"))
            except Exception as e:
                self.q.put(("error", f"TTS failed: {e}")); return
            if then_discord:
                if not self.mixer.running:
                    self.q.put(("status", "Start the mixer so Discord can hear the TTS."))
                self.mixer.trigger(out)
                self.q.put(("status", "Sent TTS into the mix."))
            elif HAVE_WINSOUND:
                winsound.PlaySound(out, winsound.SND_FILENAME | winsound.SND_ASYNC)
        threading.Thread(target=worker, daemon=True).start()

    def _tts_speak_discord(self):
        self._tts_run(True)

    def _tts_play_local(self):
        self._tts_run(False)

    # ---------- updates ----------
    def _manual_update(self):
        changed, msg = updater.pull()
        self.git_status.set(self._git_status_text())
        messagebox.showinfo("Update", msg + ("\n\nRestart to apply." if changed else ""))

    def _restart(self):
        self._on_close(restart=True)

    def _save_prefs(self):
        self.settings.update({
            "auto_update": self.auto_update_var.get() if hasattr(self, "auto_update_var") else self.settings.get("auto_update", True),
            "auto_transcribe": self.auto_transcribe.get(),
            "enable_capture_hotkey": self.enable_capture_hotkey.get(),
            "enable_sound_hotkeys": self.enable_sound_hotkeys.get(),
        })
        storage.save_settings(self.settings)

    # ---------- event pump ----------
    def _poll(self):
        try:
            while True:
                try:
                    kind, payload = self.q.get_nowait()
                except queue.Empty:
                    break
                try:
                    if kind == "status":
                        self.status_var.set(payload)
                    elif kind == "error":
                        self.status_var.set("ERROR: " + payload)
                    elif kind == "train_status":
                        self.train_status.set(payload)
                    elif kind == "new_clip":
                        self.index.append(payload); storage.save_index(self.index)
                        self._refresh_clip_list()
                        self.status_var.set(f"Saved {payload['filename']} ({payload['duration']}s)")
                        if self.auto_transcribe.get():
                            self._transcribe_one(payload["filename"])
                    elif kind == "transcript":
                        fname, text = payload
                        for c in self.index:
                            if c["filename"] == fname:
                                c["transcript"] = text; c["status"] = "done"
                        storage.save_index(self.index); self._refresh_clip_list()
                except Exception as e:
                    self.status_var.set(f"UI error (recovered): {e}")
        finally:
            active = self.engine.running or self.mixer.running
            self.root.after(120 if active else 500, self._poll)

    # ---------- close ----------
    def _on_close(self, restart=False):
        try:
            if self.hotkey_listener:
                self.hotkey_listener.stop()
            self.engine.terminate()
            self.mixer.terminate()
            audio_utils.release_pa()
        finally:
            if restart:
                self.root.destroy()
                os.execv(sys.executable, [sys.executable] + sys.argv)
            else:
                self.root.destroy()


def launch():
    root = tk.Tk()
    App(root)
    root.mainloop()