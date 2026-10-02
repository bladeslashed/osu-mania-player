"""
Mania Player GUI & Standalone Launcher
High-performance osu!mania bot with real-time calibration synchronization and custom keybinds.
"""

import os
import sys
import time
import json
import importlib.util
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

# Explicitly import dependencies so PyInstaller packages them into the EXE
import cv2
from PIL import Image, ImageTk, ImageGrab
from pynput.keyboard import Controller, Listener, Key

import mania_harness

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

# Enable High-DPI awareness on Windows
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_target_script() -> Path:
    """Robustly locates maniaplayer.py across multiple run environments, always prioritizing the current directory."""
    base_dir = get_base_dir()
    candidates = [
        base_dir / "maniaplayer.py",
        Path.cwd().resolve() / "maniaplayer.py",
        base_dir / "Pre Vibecoded" / "maniaplayer.py",
        base_dir.parent / "Pre Vibecoded" / "maniaplayer.py",
    ]

    for p in candidates:
        if p and p.exists():
            return p.resolve()

    return base_dir / "maniaplayer.py"


TARGET_SCRIPT = find_target_script()

# Load the maniaplayer module dynamically
maniaplayer = None
LOADED_MANIA = False
load_error = ""


def load_mania_module():
    global maniaplayer, LOADED_MANIA, load_error, TARGET_SCRIPT
    TARGET_SCRIPT = find_target_script()
    if not TARGET_SCRIPT.exists():
        LOADED_MANIA = False
        load_error = f"File not found: {TARGET_SCRIPT}"
        return

    try:
        spec = importlib.util.spec_from_file_location("raw_maniaplayer", str(TARGET_SCRIPT))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        maniaplayer = mod
        LOADED_MANIA = True
        load_error = ""
    except Exception as e:
        LOADED_MANIA = False
        load_error = str(e)


load_mania_module()


class ModernManiaApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("osu!mania Player Pro V1.0")
        self.root.geometry("520x660")
        self.root.minsize(480, 600)
        self.root.configure(bg="#0f172a")

        # Global input controller
        self.keyboard = Controller()

        # Bot execution state
        self.is_running = False
        self.p_status = True
        self.bot_thread = None
        self.stay_on_top = tk.BooleanVar(value=True)
        self.root.attributes("-topmost", True)

        # Active calibration coordinates & keybinds
        self.active_bbox = getattr(maniaplayer, "BBOX", (677, 953, 1225, 954))
        self.active_jl = getattr(maniaplayer, "JUDGEMENENT_LINE", 0)
        self.active_lanes = [
            getattr(maniaplayer, "LANE1", 39),
            getattr(maniaplayer, "LANE2", 215),
            getattr(maniaplayer, "LANE3", 353),
            getattr(maniaplayer, "LANE4", 502),
        ]
        self.active_keys = [
            str(getattr(maniaplayer, "KEY1", "q")).lower(),
            str(getattr(maniaplayer, "KEY2", "w")).lower(),
            str(getattr(maniaplayer, "KEY3", "[")).lower(),
            str(getattr(maniaplayer, "KEY4", "]")).lower(),
        ]
        self.config_updated = False

        # Live telemetry
        self.fps = 0.0
        self.loop_count = 0
        self.last_fps_time = time.time()
        self.current_fps = 0.0
        self.lane_states = [False, False, False, False]  # L1, L2, L3, L4

        # Build UI layout
        self._build_ui()
        self._sync_with_maniaplayer()

        # Start global keyboard hotkeys listener
        self._start_global_hotkeys()

        # Start UI refresh loop (FPS & Lane visualizer)
        self._start_ui_refresh_loop()

        # Protocol handling
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        # 1. Top Header Banner
        header = tk.Frame(self.root, bg="#1e293b", height=60, padx=16, pady=12)
        header.pack(side=tk.TOP, fill=tk.X)

        title_box = tk.Frame(header, bg="#1e293b")
        title_box.pack(side=tk.LEFT)

        lbl_title = tk.Label(
            title_box, text="osu!mania Player Pro",
            bg="#1e293b", fg="#f8fafc", font=("Segoe UI", 14, "bold")
        )
        lbl_title.pack(anchor="w")

        lbl_sub = tk.Label(
            title_box, text="Ultra-Fast Screen Engine | V1.0 Standalone",
            bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8)
        )
        lbl_sub.pack(anchor="w")

        # Engine pill badge
        engine_str = "MSS High-FPS" if HAS_MSS else "PIL ImageGrab"
        lbl_engine = tk.Label(
            header, text=engine_str, bg="#334155", fg="#38bdf8",
            font=("Segoe UI", 8, "bold"), padx=8, pady=3
        )
        lbl_engine.pack(side=tk.RIGHT)

        # 2. Status Banner
        self.status_banner = tk.Frame(self.root, bg="#334155", pady=10, padx=16)
        self.status_banner.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(12, 6))

        self.lbl_status_icon = tk.Label(
            self.status_banner, text="⏸️", bg="#334155", fg="#f8fafc",
            font=("Segoe UI", 16)
        )
        self.lbl_status_icon.pack(side=tk.LEFT, padx=(0, 10))

        status_text_box = tk.Frame(self.status_banner, bg="#334155")
        status_text_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.lbl_status_text = tk.Label(
            status_text_box, text="STANDBY / IDLE", bg="#334155", fg="#f8fafc",
            font=("Segoe UI", 11, "bold"), anchor="w"
        )
        self.lbl_status_text.pack(fill=tk.X)

        self.lbl_status_sub = tk.Label(
            status_text_box, text="Press F1 to start playing or F2 to stop",
            bg="#334155", fg="#94a3b8", font=("Segoe UI", 8), anchor="w"
        )
        self.lbl_status_sub.pack(fill=tk.X)

        self.lbl_fps = tk.Label(
            self.status_banner, text="0.0 FPS", bg="#334155", fg="#38bdf8",
            font=("Consolas", 11, "bold")
        )
        self.lbl_fps.pack(side=tk.RIGHT)

        # 3. Big Start / Stop Button
        self.btn_toggle = tk.Button(
            self.root, text="▶ START PLAYER  (F1)",
            bg="#16a34a", fg="white", activebackground="#15803d", activeforeground="white",
            font=("Segoe UI", 12, "bold"), relief="flat", pady=10, cursor="hand2",
            command=self.toggle_running
        )
        self.btn_toggle.pack(side=tk.TOP, fill=tk.X, padx=12, pady=6)

        # 4. Lane State Visualizer
        lbl_vis_title = tk.Label(
            self.root, text="LIVE 4-KEY LANE DETECTOR",
            bg="#0f172a", fg="#64748b", font=("Segoe UI", 8, "bold"), anchor="w"
        )
        lbl_vis_title.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(8, 4))

        lanes_box = tk.Frame(self.root, bg="#0f172a")
        lanes_box.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 6))

        self.lane_pads = []
        lane_labels = [("Lane 1", self.active_keys[0].upper(), "#38bdf8"),
                       ("Lane 2", self.active_keys[1].upper(), "#4ade80"),
                       ("Lane 3", self.active_keys[2].upper(), "#fb923c"),
                       ("Lane 4", self.active_keys[3].upper(), "#c084fc")]

        for i, (name, key, color) in enumerate(lane_labels):
            pad = tk.Frame(lanes_box, bg="#1e293b", padx=6, pady=8, highlightthickness=1, highlightbackground="#334155")
            pad.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)

            l_name = tk.Label(pad, text=name, bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8))
            l_name.pack()

            l_key = tk.Label(pad, text=key, bg="#1e293b", fg=color, font=("Segoe UI", 14, "bold"))
            l_key.pack(pady=2)

            l_state = tk.Label(pad, text="OFF", bg="#1e293b", fg="#64748b", font=("Segoe UI", 8, "bold"))
            l_state.pack()

            self.lane_pads.append((pad, l_name, l_key, l_state, color))

        # 5. Configuration Display Card
        cfg_frame = tk.LabelFrame(
            self.root, text="Active Script Coordinates & Keybinds",
            bg="#0f172a", fg="#38bdf8", font=("Segoe UI", 9, "bold"), padx=10, pady=6
        )
        cfg_frame.pack(side=tk.TOP, fill=tk.X, padx=12, pady=6)

        self.lbl_cfg_file = tk.Label(cfg_frame, text=f"Source: {TARGET_SCRIPT.name}", bg="#0f172a", fg="#f8fafc", font=("Segoe UI", 8, "bold"), anchor="w")
        self.lbl_cfg_file.pack(fill=tk.X)

        self.lbl_cfg_bbox = tk.Label(cfg_frame, text="BBOX: --", bg="#0f172a", fg="#cbd5e1", font=("Consolas", 8), anchor="w")
        self.lbl_cfg_bbox.pack(fill=tk.X, pady=1)

        self.lbl_cfg_lanes = tk.Label(cfg_frame, text="Lanes: --", bg="#0f172a", fg="#cbd5e1", font=("Consolas", 8), anchor="w")
        self.lbl_cfg_lanes.pack(fill=tk.X, pady=1)

        self.lbl_cfg_jl = tk.Label(cfg_frame, text="Judgement Line: --", bg="#0f172a", fg="#cbd5e1", font=("Consolas", 8), anchor="w")
        self.lbl_cfg_jl.pack(fill=tk.X, pady=1)

        # 6. Quick Controls & Actions
        action_bar = tk.Frame(self.root, bg="#0f172a")
        action_bar.pack(side=tk.TOP, fill=tk.X, padx=12, pady=4)

        btn_screenshot = tk.Button(
            action_bar, text="📸 Screenshot (F3)", bg="#334155", fg="white",
            activebackground="#475569", activeforeground="white", font=("Segoe UI", 9),
            relief="flat", padx=10, pady=5, cursor="hand2", command=self.take_screenshot
        )
        btn_screenshot.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        btn_quit = tk.Button(
            action_bar, text="❌ Exit (F4)", bg="#334155", fg="#f87171",
            activebackground="#475569", activeforeground="#f87171", font=("Segoe UI", 9),
            relief="flat", padx=10, pady=5, cursor="hand2", command=self.on_close
        )
        btn_quit.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        # 7. Bottom Bar with Calibration Button & Always on top
        bot_bar = tk.Frame(self.root, bg="#0f172a")
        bot_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 8))

        chk_top = tk.Checkbutton(
            bot_bar, text="Always on Top", variable=self.stay_on_top,
            bg="#0f172a", fg="#94a3b8", selectcolor="#1e293b", activebackground="#0f172a",
            activeforeground="#f8fafc", command=self._toggle_topmost
        )
        chk_top.pack(side=tk.LEFT)

        btn_harness = tk.Button(
            bot_bar, text="🎯 Open Calibrator", bg="#2563eb", fg="white",
            activebackground="#1d4ed8", activeforeground="white", font=("Segoe UI", 9, "bold"),
            relief="flat", padx=12, pady=4, cursor="hand2", command=self.open_calibrator
        )
        btn_harness.pack(side=tk.RIGHT)

        btn_reload = tk.Button(
            bot_bar, text="🔄 Reload Script", bg="#334155", fg="white",
            activebackground="#475569", activeforeground="white", font=("Segoe UI", 8),
            relief="flat", padx=10, pady=4, cursor="hand2", command=self._reload_script
        )
        btn_reload.pack(side=tk.RIGHT, padx=4)

    def _sync_with_maniaplayer(self):
        if not LOADED_MANIA:
            self.lbl_cfg_bbox.config(text=f"Error loading script: {load_error}")
            return

        bbox = getattr(maniaplayer, "BBOX", self.active_bbox)
        l1 = getattr(maniaplayer, "LANE1", self.active_lanes[0])
        l2 = getattr(maniaplayer, "LANE2", self.active_lanes[1])
        l3 = getattr(maniaplayer, "LANE3", self.active_lanes[2])
        l4 = getattr(maniaplayer, "LANE4", self.active_lanes[3])
        jl = getattr(maniaplayer, "JUDGEMENENT_LINE", self.active_jl)

        k1 = str(getattr(maniaplayer, "KEY1", self.active_keys[0])).lower()
        k2 = str(getattr(maniaplayer, "KEY2", self.active_keys[1])).lower()
        k3 = str(getattr(maniaplayer, "KEY3", self.active_keys[2])).lower()
        k4 = str(getattr(maniaplayer, "KEY4", self.active_keys[3])).lower()

        self.active_bbox = bbox
        self.active_jl = jl
        self.active_lanes = [l1, l2, l3, l4]
        self.active_keys = [k1, k2, k3, k4]

        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        self.lbl_cfg_file.config(text=f"Source: {TARGET_SCRIPT.name}")
        self.lbl_cfg_bbox.config(text=f"BBOX: {bbox} ({w}x{h} px)")
        self.lbl_cfg_lanes.config(text=f"L1: {l1} [{k1.upper()}] | L2: {l2} [{k2.upper()}] | L3: {l3} [{k3.upper()}] | L4: {l4} [{k4.upper()}]")
        self.lbl_cfg_jl.config(text=f"JUDGEMENENT_LINE: {jl}")

        # Update lane visualizer pads
        for i in range(4):
            self.lane_pads[i][2].config(text=self.active_keys[i].upper())

    def _toggle_topmost(self):
        self.root.attributes("-topmost", self.stay_on_top.get())

    def _reload_script(self):
        load_mania_module()
        self._sync_with_maniaplayer()
        if LOADED_MANIA:
            messagebox.showinfo("Reloaded", f"Successfully reloaded:\n{TARGET_SCRIPT.name}")
        else:
            messagebox.showerror("Reload Failed", f"Could not load script:\n{load_error}")

    def on_calibrator_update(self, bbox, judgement_line, lanes, keys=None):
        """Callback invoked when Calibrator saves or applies new coordinates or keys."""
        if LOADED_MANIA and maniaplayer:
            try:
                maniaplayer.BBOX = bbox
                maniaplayer.JUDGEMENENT_LINE = judgement_line
                maniaplayer.LANE1 = lanes[0]
                maniaplayer.LANE2 = lanes[1]
                maniaplayer.LANE3 = lanes[2]
                maniaplayer.LANE4 = lanes[3]
                if keys and len(keys) >= 4:
                    maniaplayer.KEY1 = str(keys[0]).lower()
                    maniaplayer.KEY2 = str(keys[1]).lower()
                    maniaplayer.KEY3 = str(keys[2]).lower()
                    maniaplayer.KEY4 = str(keys[3]).lower()
            except Exception:
                pass

        self.active_bbox = bbox
        self.active_jl = judgement_line
        self.active_lanes = list(lanes)
        if keys and len(keys) >= 4:
            self.active_keys = [str(k).lower() for k in keys]

        self.config_updated = True
        self._sync_with_maniaplayer()

        keys_str = "/".join(self.active_keys).upper()
        self.lbl_status_sub.config(text=f"Updated: BBOX {bbox} | Keys: {keys_str}")

    def open_calibrator(self):
        calib_win = tk.Toplevel(self.root)
        calib_win.lift()
        calib_win.attributes("-topmost", True)

        base_dir = get_base_dir()
        target_file = base_dir / "maniaplayer.py"
        config_path = base_dir / "mania_config.json"
        presets_dir = base_dir / "presets"

        app = mania_harness.ManiaHarnessApp(
            calib_win,
            on_save_callback=self.on_calibrator_update,
            target_file=target_file,
            config_file=config_path,
            presets_dir=presets_dir
        )

        def on_calib_close():
            self._reload_script()
            self._sync_with_maniaplayer()
            calib_win.destroy()

        calib_win.protocol("WM_DELETE_WINDOW", on_calib_close)

    # -------------------------------------------------------------
    # High-Performance Bot Core Loop (60 - 240+ FPS)
    # -------------------------------------------------------------
    def toggle_running(self):
        if self.is_running:
            self.stop_bot()
        else:
            self.start_bot()

    def start_bot(self):
        if self.is_running:
            return
        if not LOADED_MANIA:
            self._reload_script()
            if not LOADED_MANIA:
                messagebox.showerror("Cannot Start", f"Target script could not be loaded:\n{load_error}")
                return

        self.is_running = True
        if LOADED_MANIA:
            maniaplayer.is_running = True

        self.btn_toggle.config(
            text="⏹ STOP PLAYER  (F2)", bg="#dc2626", activebackground="#b91c1c"
        )
        self.status_banner.config(bg="#14532d")
        self.lbl_status_icon.config(text="⚡", bg="#14532d")
        self.lbl_status_text.config(text="RECORDING & PLAYING", bg="#14532d", fg="#4ade80")
        self.lbl_status_sub.config(bg="#14532d", fg="#86efac")

        # Start execution thread
        self.bot_thread = threading.Thread(target=self._bot_worker, daemon=True)
        self.bot_thread.start()

    def stop_bot(self):
        self.is_running = False
        if LOADED_MANIA:
            maniaplayer.is_running = False

        self.btn_toggle.config(
            text="▶ START PLAYER  (F1)", bg="#16a34a", activebackground="#15803d"
        )
        self.status_banner.config(bg="#334155")
        self.lbl_status_icon.config(text="⏸️", bg="#334155")
        self.lbl_status_text.config(text="STANDBY / IDLE", bg="#334155", fg="#f8fafc")
        self.lbl_status_sub.config(bg="#334155", fg="#94a3b8")

        # Release keys safely
        for k in self.active_keys:
            try:
                self.keyboard.release(k)
            except Exception:
                pass
        for k in ['q', 'w', '[', ']']:
            try:
                self.keyboard.release(k)
            except Exception:
                pass
        self.lane_states = [False, False, False, False]

    def _bot_worker(self):
        """Ultra-fast capture worker achieving 60-240+ FPS with dynamic coordinate & key reloading."""
        jl = self.active_jl
        l1, l2, l3, l4 = self.active_lanes
        k1, k2, k3, k4 = self.active_keys
        bbox = self.active_bbox

        if HAS_MSS:
            try:
                with mss.mss() as sct:
                    current_bbox = bbox
                    monitor = {
                        "left": bbox[0],
                        "top": bbox[1],
                        "width": max(1, bbox[2] - bbox[0]),
                        "height": max(1, bbox[3] - bbox[1])
                    }
                    w = monitor["width"]
                    h = monitor["height"]
                    jl_clamp = min(jl, h - 1)
                    stride = w * 4
                    off1 = (jl_clamp * stride) + (min(l1, w - 1) * 4)
                    off2 = (jl_clamp * stride) + (min(l2, w - 1) * 4)
                    off3 = (jl_clamp * stride) + (min(l3, w - 1) * 4)
                    off4 = (jl_clamp * stride) + (min(l4, w - 1) * 4)

                    while self.is_running and self.p_status:
                        # Check dynamic updates from calibrator
                        if self.config_updated or current_bbox != self.active_bbox:
                            bbox = self.active_bbox
                            current_bbox = bbox
                            jl = self.active_jl
                            l1, l2, l3, l4 = self.active_lanes
                            k1, k2, k3, k4 = self.active_keys
                            monitor = {
                                "left": bbox[0],
                                "top": bbox[1],
                                "width": max(1, bbox[2] - bbox[0]),
                                "height": max(1, bbox[3] - bbox[1])
                            }
                            w = monitor["width"]
                            h = monitor["height"]
                            jl_clamp = min(jl, h - 1)
                            stride = w * 4
                            off1 = (jl_clamp * stride) + (min(l1, w - 1) * 4)
                            off2 = (jl_clamp * stride) + (min(l2, w - 1) * 4)
                            off3 = (jl_clamp * stride) + (min(l3, w - 1) * 4)
                            off4 = (jl_clamp * stride) + (min(l4, w - 1) * 4)
                            self.config_updated = False

                        shot = sct.grab(monitor)
                        raw = shot.raw

                        hit1 = (raw[off1 + 2] + raw[off1 + 1] + raw[off1]) > 90
                        hit2 = (raw[off2 + 2] + raw[off2 + 1] + raw[off2]) > 90
                        hit3 = (raw[off3 + 2] + raw[off3 + 1] + raw[off3]) > 90
                        hit4 = (raw[off4 + 2] + raw[off4 + 1] + raw[off4]) > 90

                        if hit1:
                            self.keyboard.press(k1)
                        else:
                            self.keyboard.release(k1)

                        if hit2:
                            self.keyboard.press(k2)
                        else:
                            self.keyboard.release(k2)

                        if hit3:
                            self.keyboard.press(k3)
                        else:
                            self.keyboard.release(k3)

                        if hit4:
                            self.keyboard.press(k4)
                        else:
                            self.keyboard.release(k4)

                        self.lane_states = [hit1, hit2, hit3, hit4]
                        self.loop_count += 1
                    return
            except Exception:
                pass

        # Fallback using standard ImageGrab.grab()
        while self.is_running and self.p_status:
            try:
                if self.config_updated:
                    bbox = self.active_bbox
                    jl = self.active_jl
                    l1, l2, l3, l4 = self.active_lanes
                    k1, k2, k3, k4 = self.active_keys
                    self.config_updated = False

                check = ImageGrab.grab(bbox=bbox)
                px = check.load()

                hit1 = sum(px[l1, jl]) / 3 > 30
                if hit1:
                    self.keyboard.press(k1)
                else:
                    self.keyboard.release(k1)

                hit2 = sum(px[l2, jl]) / 3 > 30
                if hit2:
                    self.keyboard.press(k2)
                else:
                    self.keyboard.release(k2)

                hit3 = sum(px[l3, jl]) / 3 > 30
                if hit3:
                    self.keyboard.press(k3)
                else:
                    self.keyboard.release(k3)

                hit4 = sum(px[l4, jl]) / 3 > 30
                if hit4:
                    self.keyboard.press(k4)
                else:
                    self.keyboard.release(k4)

                self.lane_states = [hit1, hit2, hit3, hit4]
                self.loop_count += 1
            except Exception:
                pass

    def take_screenshot(self):
        try:
            self.root.withdraw()
            self.root.update()
            time.sleep(0.25)
            bbox = self.active_bbox
            screen_path = TARGET_SCRIPT.parent / "Screenshot.png"
            check = ImageGrab.grab(bbox=bbox)
            check.save(str(screen_path))
            self.lbl_status_sub.config(text=f"Screenshot saved to {screen_path.name}!")
        except Exception as e:
            messagebox.showerror("Screenshot Error", str(e))
        finally:
            self.root.deiconify()
            self.root.lift()
            if self.stay_on_top.get():
                try:
                    self.root.attributes("-topmost", True)
                except Exception:
                    pass

    # -------------------------------------------------------------
    # Global Hotkeys Listener (F1..F4)
    # -------------------------------------------------------------
    def _start_global_hotkeys(self):
        def on_press(key):
            try:
                if key == Key.f1:
                    self.root.after(0, self.start_bot)
                elif key == Key.f2:
                    self.root.after(0, self.stop_bot)
                elif key == Key.f3:
                    self.root.after(0, self.take_screenshot)
                elif key == Key.f4:
                    self.root.after(0, self.on_close)
            except Exception:
                pass

        self.listener = Listener(on_press=on_press)
        self.listener.daemon = True
        self.listener.start()

    # -------------------------------------------------------------
    # UI Refresh Loop (FPS & Lane Visualizer)
    # -------------------------------------------------------------
    def _start_ui_refresh_loop(self):
        def refresh():
            now = time.time()
            elapsed = now - self.last_fps_time
            if elapsed >= 1.0:
                self.current_fps = round(self.loop_count / elapsed, 1)
                self.lbl_fps.config(text=f"{self.current_fps} FPS")
                self.loop_count = 0
                self.last_fps_time = now

            for i in range(4):
                pad, l_name, l_key, l_state, color = self.lane_pads[i]
                active = self.lane_states[i]
                if active:
                    pad.config(bg=color, highlightbackground="white")
                    l_name.config(bg=color, fg="black")
                    l_key.config(bg=color, fg="black")
                    l_state.config(bg=color, fg="black", text="PRESS")
                else:
                    pad.config(bg="#0f172a", highlightbackground="#334155")
                    l_name.config(bg="#0f172a", fg="#94a3b8")
                    l_key.config(bg="#0f172a", fg=color)
                    l_state.config(bg="#0f172a", fg="#64748b", text="OFF")

            self.root.after(30, refresh)

        self.root.after(30, refresh)

    def on_close(self):
        self.is_running = False
        self.p_status = False
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ModernManiaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
