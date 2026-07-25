import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

import keyboard
import pyperclip
import pythoncom
import win32com.client
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
DEFAULTS = {"rate": 150, "voice": 0, "volume": 100}

# SAPI async flags
_ASYNC = 1
_PURGE_AND_ASYNC = 3  # SVSFPurgeBeforeSpeak | SVSFlagsAsync

_q = queue.Queue()
_worker_state = {}  # populated by worker thread: "voice_names"


def wpm_to_sapi(wpm):
    """Convert words-per-minute (50-300) to SAPI rate (-10 to 10)."""
    return max(-10, min(10, round((wpm - 150) / 15)))


# --- Settings ---

def load_settings():
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        return {**DEFAULTS, **data}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save_settings(rate, voice_index, volume):
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"rate": rate, "voice": voice_index, "volume": volume}, f, indent=2)
    _q.put(("settings", rate, voice_index, volume))


# --- SAPI worker thread ---

def _apply(speaker, settings):
    voices = speaker.GetVoices()
    vi = settings["voice"]
    if 0 <= vi < voices.Count:
        speaker.Voice = voices.Item(vi)
    speaker.Rate = wpm_to_sapi(settings["rate"])
    speaker.Volume = int(settings["volume"])


def _worker():
    pythoncom.CoInitialize()
    try:
        speaker = win32com.client.Dispatch("SAPI.SpVoice")

        # Cache voice names for the settings dialog
        voices = speaker.GetVoices()
        _worker_state["voice_names"] = [voices.Item(i).GetDescription() for i in range(voices.Count)]

        settings = load_settings()
        _apply(speaker, settings)
        _worker_state["ready"] = True

        while True:
            item = _q.get()
            if item is None:
                break
            cmd = item[0]
            if cmd == "speak":
                speaker.Speak(item[1], _PURGE_AND_ASYNC)
            elif cmd == "stop":
                speaker.Speak("", _PURGE_AND_ASYNC)
            elif cmd == "settings":
                _, rate, vi, vol = item
                _apply(speaker, {"rate": rate, "voice": vi, "volume": vol})
            elif cmd == "test":
                _, rate, vi, vol = item
                _apply(speaker, {"rate": rate, "voice": vi, "volume": vol})
                speaker.Speak("This is a preview of the selected voice.", _PURGE_AND_ASYNC)
    finally:
        pythoncom.CoUninitialize()


# --- Speech actions ---

def read_clipboard():
    text = pyperclip.paste()
    if text and text.strip():
        _q.put(("speak", text))


def stop_reading():
    _q.put(("stop",))


# --- Tray icon ---

def create_icon():
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=(30, 100, 220))
    draw.text((20, 14), "R", fill="white")
    return img


# --- Settings dialog ---

def open_settings():
    def _run_dialog():
        settings = load_settings()
        voice_names = _worker_state.get("voice_names", ["(none)"])

        root = tk.Tk()
        root.title("TTS Settings")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        pad = {"padx": 10, "pady": 6}

        # Voice
        tk.Label(root, text="Voice:").grid(row=0, column=0, sticky="w", **pad)
        current_vi = min(settings["voice"], len(voice_names) - 1)
        voice_var = tk.StringVar(value=voice_names[current_vi])
        ttk.Combobox(root, textvariable=voice_var, values=voice_names,
                     state="readonly", width=38).grid(row=0, column=1, **pad)

        # Speed
        tk.Label(root, text="Speed (wpm):").grid(row=1, column=0, sticky="w", **pad)
        rate_var = tk.IntVar(value=settings["rate"])
        rate_frame = tk.Frame(root)
        rate_frame.grid(row=1, column=1, sticky="w", **pad)
        tk.Scale(rate_frame, from_=50, to=300, orient="horizontal",
                 variable=rate_var, length=220).pack(side="left")
        tk.Label(rate_frame, textvariable=rate_var, width=4).pack(side="left")

        # Volume
        tk.Label(root, text="Volume (%):").grid(row=2, column=0, sticky="w", **pad)
        vol_var = tk.IntVar(value=int(settings["volume"]))
        vol_frame = tk.Frame(root)
        vol_frame.grid(row=2, column=1, sticky="w", **pad)
        tk.Scale(vol_frame, from_=0, to=100, orient="horizontal",
                 variable=vol_var, length=220).pack(side="left")
        tk.Label(vol_frame, textvariable=vol_var, width=4).pack(side="left")

        # Buttons
        btn_frame = tk.Frame(root)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)

        def on_save():
            vi = voice_names.index(voice_var.get()) if voice_var.get() in voice_names else 0
            save_settings(rate_var.get(), vi, vol_var.get())
            root.destroy()

        def on_test():
            vi = voice_names.index(voice_var.get()) if voice_var.get() in voice_names else 0
            _q.put(("test", rate_var.get(), vi, vol_var.get()))

        tk.Button(btn_frame, text="Test Voice", width=10, command=on_test).pack(side="left", padx=8)
        tk.Button(btn_frame, text="Save", width=10, command=on_save).pack(side="left", padx=8)
        tk.Button(btn_frame, text="Cancel", width=10, command=root.destroy).pack(side="left", padx=8)

        root.mainloop()

    threading.Thread(target=_run_dialog, daemon=True).start()


# --- Main ---

def main():
    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()

    # Wait for SAPI to be ready before registering hotkeys
    while not _worker_state.get("ready"):
        threading.Event().wait(0.05)

    keyboard.add_hotkey("shift+`", read_clipboard)
    keyboard.add_hotkey("shift+esc", stop_reading)

    menu = Menu(
        MenuItem("Read Clipboard  (Shift+`)", lambda icon, item: read_clipboard()),
        MenuItem("Stop  (Shift+Esc)", lambda icon, item: stop_reading()),
        Menu.SEPARATOR,
        MenuItem("Settings", lambda icon, item: open_settings()),
        Menu.SEPARATOR,
        MenuItem("Exit", lambda icon, item: icon.stop()),
    )

    tray = Icon("ClipboardReader", create_icon(), "Clipboard TTS Reader", menu)
    tray.run()

    # Cleanup
    keyboard.unhook_all_hotkeys()
    _q.put(None)


if __name__ == "__main__":
    main()
