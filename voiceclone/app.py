"""Main GUI: ties capture, soundboard, training, TTS and settings together."""
import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

from .config import (CAPTURE_HOTKEY, DEFAULT_BUFFER_SECONDS, CLIPS_DIR, ensure_dirs)
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
        self.tab_set = ttk.Frame(nb);     nb.add(self.tab_set, text="  Settings  ")

        self.status_var = tk.StringVar(value=f"Ready.   Capture hotkey: {CAPTURE_HOTKEY}")
        ttk.Label(root, textvariable=self.status_var, style="Status.TLabel",
                  anchor="w").pack(fill="x", side="bottom")

        self._build_capture_tab()
        self._build_board_tab()
        self._build_train_tab()
        self._build_tts_tab()
        self._build_settings_tab()

        self._refresh_devices()
        self._refresh_clip_list()
        self._refresh_sound_list()
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

        gain = ttk.Frame(t, padding=(12, 0)); gain.pack(fill="x")
        ttk.Label(gain, text="Output volume / gain").pack(side="left")
        self.gain_var = tk.IntVar(value=self.settings.get("gain", 100))
        ttk.Scale(gain, from_=0, to=300, orient="horizontal", variable=self.gain_var,
                  command=self._on_gain).pack(side="left", fill="x", expand=True, padx=10)
        self.gain_lbl = ttk.Label(gain, text=f"{self.gain_var.get()}%")
        self.gain_lbl.pack(side="left")
        ttk.Label(gain, text="(>100% = peaked)", style="Muted.TLabel").pack(side="left", padx=8)

        mid = ttk.Frame(t, padding=12); mid.pack(fill="both", expand=True)
        self.sound_list = tk.Listbox(mid, selectmode="browse", relief="flat",
                                     bg=self.p["field"], highlightthickness=1,
                                     highlightbackground="#d7d9de", font=("Segoe UI", 10))
        self.sound_list.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.sound_list.yview)
        sb.pack(side="right", fill="y"); self.sound_list.configure(yscrollcommand=sb.set)

        bar = ttk.Frame(t, padding=12); bar.pack(fill="x")
        ttk.Button(bar, text="Add Sound", command=self._add_sound).pack(side="left", padx=3)
        ttk.Button(bar, text="Remove", style="Danger.TButton", command=self._remove_sound).pack(side="left", padx=3)
        ttk.Button(bar, text="Play into Discord", style="Accent.TButton", command=self._play_sound).pack(side="left", padx=3)
        ttk.Button(bar, text="Stop All", command=self.mixer.stop_all_sounds).pack(side="left", padx=3)
        ttk.Label(bar, text="Ctrl+Alt+1..9 = first 9 sounds", style="Muted.TLabel").pack(side="right")

    # ---------- training tab ----------
    def _build_train_tab(self):
        f = ttk.Frame(self.tab_train, padding=16); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Dataset export", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, justify="left", style="Muted.TLabel", text=(
            "Exports one speaker's transcribed clips into a Piper-ready dataset:\n"
            "   dataset/<speaker>/wav/*.wav   (22050 Hz mono)\n"
            "   dataset/<speaker>/metadata.csv   (id|transcript)\n\n"
            "GPU training runs on Google Colab (free) - CPU training is impractical.\n"
            "Export a dataset, then load the resulting model on the Voice (TTS) tab."
        )).pack(anchor="w", pady=8)
        ttk.Button(f, text="Export Piper Dataset", style="Accent.TButton",
                   command=self._export_dataset).pack(anchor="w", pady=4)
        self.train_status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.train_status).pack(anchor="w", pady=6)

    # ---------- tts tab ----------
    def _build_tts_tab(self):
        f = ttk.Frame(self.tab_tts, padding=16); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Speak with a Piper voice", style="Title.TLabel").pack(anchor="w")
        row = ttk.Frame(f); row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text="Model (.onnx)").pack(side="left")
        self.tts_model_var = tk.StringVar(value=self.settings.get("tts_model", ""))
        ttk.Entry(row, textvariable=self.tts_model_var, width=52).pack(side="left", padx=6)
        ttk.Button(row, text="Browse", command=self._tts_pick_model).pack(side="left")
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
        self.mixer.set_gain_percent(self.gain_var.get())
        if self.mixer.start(mic[0], cable[0], mon):
            self.mixer_btn.config(text="Stop Mixer")
        self._update_hotkey_listener()

    def _on_gain(self, _=None):
        pct = int(float(self.gain_var.get()))
        self.gain_lbl.config(text=f"{pct}%")
        self.mixer.set_gain_percent(pct)
        self.settings["gain"] = pct; storage.save_settings(self.settings)

    # ---------- sounds ----------
    def _refresh_sound_list(self):
        self.sound_list.delete(0, "end")
        for pth in self.settings.get("sounds", []):
            self.sound_list.insert("end", os.path.basename(pth))

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
        if idx < len(sounds):
            if not self.mixer.running:
                self.status_var.set("Start the mixer first so Discord can hear the sound.")
            self.mixer.trigger(sounds[idx])

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
        if self.engine.running and self.enable_capture_hotkey.get():
            mapping[CAPTURE_HOTKEY] = lambda: self.engine.save_last_clip(self.speaker_var.get())
        if self.mixer.running and self.enable_sound_hotkeys.get():
            for n in range(1, 10):
                mapping[f"<ctrl>+<alt>+{n}"] = (lambda i=n - 1: self._play_sound(i))
        if mapping:
            self.hotkey_listener = keyboard.GlobalHotKeys(mapping)
            self.hotkey_listener.start()

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
        for c in self.index:
            preview = (c.get("transcript", "") or "")[:80]
            self.tree.insert("", "end", iid=c["filename"], values=(
                c.get("timestamp", ""), c.get("speaker", ""), c.get("duration", ""),
                c.get("status", ""), preview))

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
        win = tk.Toplevel(self.root); win.title(f"Edit - {sel[0]}"); win.geometry("520x240")
        win.configure(bg=self.p["bg"])
        txt = tk.Text(win, wrap="word", relief="flat", bg=self.p["field"],
                      highlightthickness=1, highlightbackground="#d7d9de", font=("Segoe UI", 10))
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.insert("1.0", clip.get("transcript", ""))
        def save():
            clip["transcript"] = txt.get("1.0", "end").strip(); clip["status"] = "done"
            storage.save_index(self.index); self._refresh_clip_list(); win.destroy()
        ttk.Button(win, text="Save", style="Accent.TButton", command=save).pack(pady=8)

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
                kind, payload = self.q.get_nowait()
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
        except queue.Empty:
            pass
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
