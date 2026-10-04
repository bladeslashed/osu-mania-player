"""
Mania Player GUI & Standalone Launcher
High-performance osu!mania bot with real-time calibration synchronization and custom keybinds.
"""

import os
import sys
import time
import json
import random
import heapq
import collections
import importlib.util
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

# Explicitly import dependencies so PyInstaller packages them into the EXE
from PIL import Image, ImageTk, ImageGrab
from pynput.keyboard import Controller, Listener, Key

import mania_harness

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

# Enable High-DPI awareness & 1ms precision timer on Windows
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
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass


def parse_key(key_val):
    """Converts key string (e.g. 'q', 'space', 'left', 'up') into pynput Key object or char."""
    if not isinstance(key_val, str) or len(key_val) == 0:
        return key_val
    if len(key_val) == 1:
        return key_val
    normalized = key_val.lower().strip()
    if hasattr(Key, normalized):
        return getattr(Key, normalized)
    return key_val


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# Ensure required working folders exist at runtime
_base = get_base_dir()
(_base / "presets").mkdir(parents=True, exist_ok=True)
(_base / "backups").mkdir(parents=True, exist_ok=True)
(Path.cwd() / "presets").mkdir(parents=True, exist_ok=True)
(Path.cwd() / "backups").mkdir(parents=True, exist_ok=True)


def find_target_script() -> Path:
    """Robustly locates maniaplayer.py across multiple run environments, always prioritizing the current directory."""
    base_dir = get_base_dir()
    candidates = [
        base_dir / "maniaplayer.py",
        Path.cwd().resolve() / "maniaplayer.py",
        base_dir / "Pre Vibecoded" / "maniaplayer.py",
        base_dir.parent / "Pre Vibecoded" / "maniaplayer.py",
    ]
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "maniaplayer.py")

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


def get_harness_module():
    """Dynamically loads or reloads the most up-to-date mania_harness module.
    Prioritizes disk files in working directory or base directory so updates are
    immediately reflected at runtime, falling back to the bundled module."""
    base_dir = get_base_dir()
    candidates = [
        Path.cwd().resolve() / "mania_harness.py",
        base_dir / "mania_harness.py",
    ]
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "mania_harness.py")

    for p in candidates:
        if p and p.is_file():
            try:
                spec = importlib.util.spec_from_file_location("mania_harness", str(p))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod
            except Exception as e:
                print(f"[WARN] Failed to load external mania_harness from {p}: {e}")

    try:
        importlib.reload(mania_harness)
        return mania_harness
    except Exception:
        return mania_harness


class ModernManiaApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Osu!Mania Player v1.3.0")
        self.root.geometry("540x820")
        self.root.minsize(500, 740)
        self.root.configure(bg="#0f172a")

        # Global input controller
        self.keyboard = Controller()

        # Bot execution state
        self.is_running = False
        self.p_status = True
        self.bot_thread = None
        self.active_skill_sim = None

        # Window not always on top by default to prevent awkward maneuvering
        self.stay_on_top = tk.BooleanVar(value=False)
        self.root.attributes("-topmost", False)

        # Active calibration coordinates & keybinds
        self.active_bbox = getattr(maniaplayer, "BBOX", (677, 953, 1225, 954))
        self.active_jl = getattr(maniaplayer, "JUDGEMENENT_LINE", 0)

        # Dynamic Key count (1 to 20 keys)
        self.key_count = 4
        self.active_lanes = [39, 215, 353, 502]
        self.active_keys = ["q", "w", "[", "]"]

        # Delay & Skill Level settings (milliseconds)
        self.input_delay_ms = 0
        self.skill_level = 0
        self.misread_chance = 0   # % chance a note press is misread
        self.misread_ms = 0       # lane ignores input for this long after a misread
        self.stamina_max = 0      # max clicks in stamina pool (0 = off)
        self.stamina_regen = 0.0  # stamina regenerated per 20 ms
        self.strain_step_pct = 0    # every X% stamina lost (0 = off)
        self.strain_misread_pct = 0 # misread chance increases by y%
        self.strain_skill_ms = 0    # skill delay variance increases by z ms
        self.strain_regen_pct = 0   # stamina regen decreased by Z%

        # Load initial config from mania_config.json if available
        base_dir = get_base_dir()
        cfg_file = base_dir / "mania_config.json"
        if not cfg_file.exists():
            cfg_file = Path.cwd() / "mania_config.json"
        if cfg_file.exists():
            try:
                cfg_data = json.loads(cfg_file.read_text(encoding="utf-8"))
                c_bbox = cfg_data.get("bbox")
                if c_bbox and len(c_bbox) == 4:
                    self.active_bbox = tuple(int(x) for x in c_bbox)
                self.active_jl = int(cfg_data.get("judgement_line", self.active_jl))
                self.input_delay_ms = int(cfg_data.get("input_delay_ms", cfg_data.get("delay_ms", 0)))
                self.skill_level = int(cfg_data.get("skill_level", cfg_data.get("skill_level_ms", cfg_data.get("input_variance_ms", 0))))
                self.misread_chance = min(100.0, max(0.0, float(cfg_data.get("misread_chance", 0))))
                self.misread_ms = max(0.0, float(cfg_data.get("misread_ms", 0)))
                self.stamina_max = max(0.0, float(cfg_data.get("stamina_max", 0)))
                self.stamina_regen = max(0.0, float(cfg_data.get("stamina_regen", 0.0)))
                self.strain_step_pct = max(0.0, float(cfg_data.get("strain_step_pct", 0)))
                self.strain_misread_pct = max(0.0, float(cfg_data.get("strain_misread_pct", 0)))
                self.strain_skill_ms = max(0.0, float(cfg_data.get("strain_skill_ms", 0)))
                self.strain_regen_pct = max(0.0, float(cfg_data.get("strain_regen_pct", 0)))
                c_lanes = cfg_data.get("lanes", [])
                if c_lanes:
                    self.key_count = min(20, max(1, len(c_lanes)))
                    self.active_lanes = [int(l.get("x", 0)) for l in c_lanes[:self.key_count]]
                    self.active_keys = [str(l.get("key", "q")).lower() for l in c_lanes[:self.key_count]]
            except Exception:
                pass
        else:
            self.input_delay_ms = int(getattr(maniaplayer, "INPUT_DELAY_MS", getattr(maniaplayer, "DELAY_MS", 0)))
            self.skill_level = int(getattr(maniaplayer, "SKILL_LEVEL", getattr(maniaplayer, "SKILL_LEVEL_MS", 0)))
            self.misread_chance = float(getattr(maniaplayer, "MISREAD_CHANCE", 0))
            self.misread_ms = float(getattr(maniaplayer, "MISREAD_MS", 0))
            self.stamina_max = float(getattr(maniaplayer, "STAMINA_MAX", 0))
            self.stamina_regen = float(getattr(maniaplayer, "STAMINA_REGEN", 0.0))
            self.strain_step_pct = float(getattr(maniaplayer, "STRAIN_STEP_PCT", 0))
            self.strain_misread_pct = float(getattr(maniaplayer, "STRAIN_MISREAD_PCT", 0))
            self.strain_skill_ms = float(getattr(maniaplayer, "STRAIN_SKILL_MS", 0))
            self.strain_regen_pct = float(getattr(maniaplayer, "STRAIN_REGEN_PCT", 0))
            if hasattr(maniaplayer, "LANES") and hasattr(maniaplayer, "KEYS"):
                self.key_count = min(20, max(1, len(maniaplayer.LANES)))
                self.active_lanes = list(maniaplayer.LANES[:self.key_count])
                self.active_keys = [str(k).lower() for k in maniaplayer.KEYS[:self.key_count]]
            else:
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

        self.parsed_keys = [parse_key(k) for k in self.active_keys]
        self.config_updated = False

        # Live telemetry
        self.fps = 0.0
        self.loop_count = 0
        self.last_fps_time = time.time()
        self.current_fps = 0.0
        self.lane_states = [False] * self.key_count

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
            title_box, text="Osu!Mania Player v1.3.0",
            bg="#1e293b", fg="#f8fafc", font=("Segoe UI", 14, "bold")
        )
        lbl_title.pack(anchor="w")

        lbl_sub = tk.Label(
            title_box, text="Ultra-Fast Screen Engine | v1.3.0 Standalone",
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

        # 4. Lane State Visualizer Header & Dynamic Key Count Selector (1 to 20 Keys)
        vis_header = tk.Frame(self.root, bg="#0f172a")
        vis_header.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(8, 4))

        self.lbl_vis_title = tk.Label(
            vis_header, text=f"LIVE {self.key_count}-KEY LANE DETECTOR",
            bg="#0f172a", fg="#64748b", font=("Segoe UI", 8, "bold")
        )
        self.lbl_vis_title.pack(side=tk.LEFT)

        kc_box = tk.Frame(vis_header, bg="#0f172a")
        kc_box.pack(side=tk.RIGHT)

        tk.Label(kc_box, text="Keys (1-20):", bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 3))

        btn_dec = tk.Button(
            kc_box, text="−", bg="#1e293b", fg="white", activebackground="#334155",
            font=("Consolas", 8, "bold"), relief="flat", padx=4, pady=0, cursor="hand2",
            command=lambda: self.set_key_count(self.key_count - 1)
        )
        btn_dec.pack(side=tk.LEFT, padx=1)

        self.lbl_key_badge = tk.Label(
            kc_box, text=f"{self.key_count}K", bg="#1e293b", fg="#38bdf8",
            font=("Segoe UI", 8, "bold"), width=4
        )
        self.lbl_key_badge.pack(side=tk.LEFT, padx=1)

        btn_inc = tk.Button(
            kc_box, text="+", bg="#1e293b", fg="white", activebackground="#334155",
            font=("Consolas", 8, "bold"), relief="flat", padx=4, pady=0, cursor="hand2",
            command=lambda: self.set_key_count(self.key_count + 1)
        )
        btn_inc.pack(side=tk.LEFT, padx=1)

        for qk in (4, 7, 8, 10):
            btn_qk = tk.Button(
                kc_box, text=f"{qk}K", bg="#1e293b", fg="#cbd5e1", activebackground="#334155",
                font=("Segoe UI", 7), relief="flat", padx=3, pady=0, cursor="hand2",
                command=lambda val=qk: self.set_key_count(val)
            )
            btn_qk.pack(side=tk.LEFT, padx=1)

        self.lanes_box = tk.Frame(self.root, bg="#0f172a")
        self.lanes_box.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 6))

        self.lane_pads = []
        self._rebuild_lane_visualizer()

        # 5. Live Skill & Stamina Monitor Card
        self.skill_monitor_frame = tk.LabelFrame(
            self.root, text="⚡ LIVE SKILL & STAMINA MONITOR",
            bg="#0f172a", fg="#38bdf8", font=("Segoe UI", 9, "bold"), padx=10, pady=8
        )
        self.skill_monitor_frame.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 6))

        # Stamina row header
        sta_row = tk.Frame(self.skill_monitor_frame, bg="#0f172a")
        sta_row.pack(fill=tk.X, pady=(0, 2))

        lbl_sta_title = tk.Label(
            sta_row, text="Stamina Pool", bg="#0f172a", fg="#34d399",
            font=("Segoe UI", 8, "bold")
        )
        lbl_sta_title.pack(side=tk.LEFT)

        self.lbl_live_stamina = tk.Label(
            sta_row, text="-- / -- (100%)", bg="#0f172a", fg="#f8fafc",
            font=("Consolas", 8, "bold")
        )
        self.lbl_live_stamina.pack(side=tk.RIGHT)

        # Stamina progress bar canvas
        self.canvas_stamina_bar = tk.Canvas(
            self.skill_monitor_frame, bg="#1e293b", height=10,
            highlightthickness=1, highlightbackground="#334155"
        )
        self.canvas_stamina_bar.pack(fill=tk.X, pady=(2, 6))

        # 2-column cards for Regen & Misread
        stats_row = tk.Frame(self.skill_monitor_frame, bg="#0f172a")
        stats_row.pack(fill=tk.X, pady=(0, 4))

        card_regen = tk.Frame(stats_row, bg="#1e293b", padx=8, pady=4, highlightthickness=1, highlightbackground="#334155")
        card_regen.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        tk.Label(card_regen, text="Stamina Regen", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 7, "bold")).pack(anchor="w")
        self.lbl_live_regen = tk.Label(card_regen, text="--", bg="#1e293b", fg="#34d399", font=("Consolas", 9, "bold"))
        self.lbl_live_regen.pack(anchor="w")

        card_misread = tk.Frame(stats_row, bg="#1e293b", padx=8, pady=4, highlightthickness=1, highlightbackground="#334155")
        card_misread.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))
        tk.Label(card_misread, text="Misread Chance", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 7, "bold")).pack(anchor="w")
        self.lbl_live_misread = tk.Label(card_misread, text="--", bg="#1e293b", fg="#fb7185", font=("Consolas", 9, "bold"))
        self.lbl_live_misread.pack(anchor="w")

        # Strain telemetry box
        strain_box = tk.Frame(self.skill_monitor_frame, bg="#1e293b", padx=8, pady=3, highlightthickness=1, highlightbackground="#334155")
        strain_box.pack(fill=tk.X, pady=(2, 0))
        self.lbl_live_strain = tk.Label(
            strain_box, text="Strain: Nominal", bg="#1e293b", fg="#f59e0b",
            font=("Segoe UI", 8), anchor="w"
        )
        self.lbl_live_strain.pack(fill=tk.X)

        # 6. Configuration Display Card
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

        self.lbl_cfg_delay = tk.Label(cfg_frame, text=f"Input Delay: {self.input_delay_ms} ms", bg="#0f172a", fg="#38bdf8", font=("Consolas", 8), anchor="w")
        self.lbl_cfg_delay.pack(fill=tk.X, pady=1)

        # 6. Quick Controls & Actions (Exit)
        action_bar = tk.Frame(self.root, bg="#0f172a")
        action_bar.pack(side=tk.TOP, fill=tk.X, padx=12, pady=4)

        btn_quit = tk.Button(
            action_bar, text="❌ Exit Application (F4)", bg="#334155", fg="#f87171",
            activebackground="#475569", activeforeground="#f87171", font=("Segoe UI", 9, "bold"),
            relief="flat", padx=10, pady=6, cursor="hand2", command=self.on_close
        )
        btn_quit.pack(side=tk.LEFT, fill=tk.X, expand=True)

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

    def _rebuild_lane_visualizer(self):
        for widget in self.lanes_box.winfo_children():
            widget.destroy()

        self.lane_pads = []
        count = self.key_count

        if count <= 10:
            row_frame = tk.Frame(self.lanes_box, bg="#0f172a")
            row_frame.pack(side=tk.TOP, fill=tk.X)

            pad_padx = 6 if count <= 4 else (4 if count <= 7 else 2)
            pad_pady = 8 if count <= 4 else 5
            font_sz = 14 if count <= 4 else (11 if count <= 7 else 9)

            for i in range(count):
                color = mania_harness.get_lane_color(i)
                key_text = self.active_keys[i].upper() if i < len(self.active_keys) else f"K{i+1}"
                pad = tk.Frame(row_frame, bg="#1e293b", padx=pad_padx, pady=pad_pady, highlightthickness=1, highlightbackground="#334155")
                pad.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)

                l_name = tk.Label(pad, text=f"L{i+1}", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 7))
                l_name.pack()

                l_key = tk.Label(pad, text=key_text, bg="#1e293b", fg=color, font=("Segoe UI", font_sz, "bold"))
                l_key.pack(pady=1)

                l_state = tk.Label(pad, text="OFF", bg="#1e293b", fg="#64748b", font=("Segoe UI", 7, "bold"))
                l_state.pack()

                self.lane_pads.append((pad, l_name, l_key, l_state, color))
        else:
            mid = (count + 1) // 2
            row1 = tk.Frame(self.lanes_box, bg="#0f172a")
            row1.pack(side=tk.TOP, fill=tk.X, pady=1)
            row2 = tk.Frame(self.lanes_box, bg="#0f172a")
            row2.pack(side=tk.TOP, fill=tk.X, pady=1)

            for i in range(count):
                parent_row = row1 if i < mid else row2
                color = mania_harness.get_lane_color(i)
                key_text = self.active_keys[i].upper() if i < len(self.active_keys) else f"K{i+1}"
                pad = tk.Frame(parent_row, bg="#1e293b", padx=2, pady=3, highlightthickness=1, highlightbackground="#334155")
                pad.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1)

                l_name = tk.Label(pad, text=f"L{i+1}", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 6))
                l_name.pack()

                l_key = tk.Label(pad, text=key_text, bg="#1e293b", fg=color, font=("Segoe UI", 8, "bold"))
                l_key.pack(pady=0)

                l_state = tk.Label(pad, text="OFF", bg="#1e293b", fg="#64748b", font=("Segoe UI", 6, "bold"))
                l_state.pack()

                self.lane_pads.append((pad, l_name, l_key, l_state, color))

    def set_key_count(self, new_count: int, lanes=None, keys=None):
        new_count = max(1, min(20, int(new_count)))
        old_count = self.key_count
        self.key_count = new_count

        if hasattr(self, "lbl_vis_title"):
            self.lbl_vis_title.config(text=f"LIVE {new_count}-KEY LANE DETECTOR")
        if hasattr(self, "lbl_key_badge"):
            self.lbl_key_badge.config(text=f"{new_count}K")

        w = max(1, self.active_bbox[2] - self.active_bbox[0])

        if lanes is not None and len(lanes) >= new_count:
            self.active_lanes = [int(x) for x in lanes[:new_count]]
        else:
            if new_count > len(self.active_lanes):
                for i in range(len(self.active_lanes), new_count):
                    self.active_lanes.append(int((w / new_count) * (i + 0.5)))
            elif new_count < len(self.active_lanes):
                self.active_lanes = self.active_lanes[:new_count]

        if keys is not None and len(keys) >= new_count:
            self.active_keys = [str(k).lower().strip() for k in keys[:new_count]]
        elif old_count != new_count and new_count in mania_harness.DEFAULT_KEY_LAYOUTS:
            self.active_keys = list(mania_harness.DEFAULT_KEY_LAYOUTS[new_count])
        else:
            if new_count in mania_harness.DEFAULT_KEY_LAYOUTS and len(self.active_keys) != new_count:
                layout = mania_harness.DEFAULT_KEY_LAYOUTS[new_count]
                self.active_keys = list(layout)
            else:
                while len(self.active_keys) < new_count:
                    idx = len(self.active_keys)
                    if idx < len(mania_harness.ALL_20_KEYS):
                        self.active_keys.append(mania_harness.ALL_20_KEYS[idx])
                    else:
                        self.active_keys.append(f"k{idx+1}")
                self.active_keys = self.active_keys[:new_count]

        self.parsed_keys = [parse_key(k) for k in self.active_keys]
        self.lane_states = [False] * new_count
        self.config_updated = True

        if hasattr(self, "lanes_box"):
            self._rebuild_lane_visualizer()
        self._sync_with_maniaplayer()
        self._save_active_config()

    def _save_active_config(self):
        base_dir = get_base_dir()
        cfg_file = base_dir / "mania_config.json"
        try:
            cfg = {}
            if cfg_file.exists():
                try:
                    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            cfg["bbox"] = list(self.active_bbox)
            cfg["judgement_line"] = self.active_jl
            cfg["input_delay_ms"] = self.input_delay_ms
            cfg["delay_ms"] = self.input_delay_ms
            cfg["skill_level"] = self.skill_level
            cfg["skill_level_ms"] = self.skill_level
            cfg["misread_chance"] = self.misread_chance
            cfg["misread_ms"] = self.misread_ms
            cfg["stamina_max"] = self.stamina_max
            cfg["stamina_regen"] = self.stamina_regen
            cfg["strain_step_pct"] = self.strain_step_pct
            cfg["strain_misread_pct"] = self.strain_misread_pct
            cfg["strain_skill_ms"] = self.strain_skill_ms
            cfg["strain_regen_pct"] = self.strain_regen_pct
            cfg["key_count"] = self.key_count
            cfg["lanes"] = [
                {
                    "name": f"Lane {i+1}",
                    "x": self.active_lanes[i],
                    "key": self.active_keys[i],
                    "threshold": 30
                }
                for i in range(self.key_count)
            ]
            cfg_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

            settings_file = base_dir / "settings.json"
            s_data = {
                "bbox": list(self.active_bbox),
                "judgement_line": self.active_jl,
                "input_delay_ms": self.input_delay_ms,
                "delay_ms": self.input_delay_ms,
                "skill_level": self.skill_level,
                "skill_level_ms": self.skill_level,
                "misread_chance": self.misread_chance,
                "misread_ms": self.misread_ms,
                "stamina_max": self.stamina_max,
                "stamina_regen": self.stamina_regen,
                "strain_step_pct": self.strain_step_pct,
                "strain_misread_pct": self.strain_misread_pct,
                "strain_skill_ms": self.strain_skill_ms,
                "strain_regen_pct": self.strain_regen_pct,
                "global_threshold": 30,
                "input_mode": "hold",
                "lanes": cfg["lanes"]
            }
            settings_file.write_text(json.dumps(s_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _sync_with_maniaplayer(self):
        if not LOADED_MANIA:
            self.lbl_cfg_bbox.config(text=f"Error loading script: {load_error}")
            return

        if LOADED_MANIA and maniaplayer:
            bbox = getattr(maniaplayer, "BBOX", self.active_bbox)
            jl = getattr(maniaplayer, "JUDGEMENENT_LINE", self.active_jl)
            self.active_bbox = bbox
            self.active_jl = jl
            self.skill_level = int(getattr(maniaplayer, "SKILL_LEVEL", getattr(maniaplayer, "SKILL_LEVEL_MS", self.skill_level)))

        w = self.active_bbox[2] - self.active_bbox[0]
        h = self.active_bbox[3] - self.active_bbox[1]
        self.lbl_cfg_file.config(text=f"Source: {TARGET_SCRIPT.name} ({self.key_count} Keys)")
        self.lbl_cfg_bbox.config(text=f"BBOX: {self.active_bbox} ({w}x{h} px)")

        if self.key_count <= 6:
            lanes_str = " | ".join(f"L{i+1}: {self.active_lanes[i]} [{self.active_keys[i].upper()}]" for i in range(self.key_count))
        else:
            keys_preview = " ".join(f"[{k.upper()}]" for k in self.active_keys[:self.key_count])
            lanes_str = f"{self.key_count} Keys: {keys_preview}"
        self.lbl_cfg_lanes.config(text=lanes_str)
        self.lbl_cfg_jl.config(text=f"JUDGEMENENT_LINE: {self.active_jl}")
        if hasattr(self, "lbl_cfg_delay"):
            skill_text = f" | Skill: ±{self._round_fmt(self.skill_level, 1)} ms" if self.skill_level > 0 else " | Skill: Off (0 ms)"
            self.lbl_cfg_delay.config(text=f"Input Delay: {self.input_delay_ms} ms{skill_text}")

        for i in range(min(len(self.lane_pads), self.key_count)):
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

    def on_calibrator_update(self, bbox, judgement_line, lanes, keys=None, delay_ms=None, skill_level=None, skill_extras=None):
        """Callback invoked when Calibrator saves or applies new coordinates, keys, delay, or skill variance."""
        new_count = len(lanes)
        if delay_ms is not None:
            self.input_delay_ms = max(0, int(delay_ms))
        if skill_level is not None:
            self.skill_level = max(0, int(skill_level))
        if skill_extras:
            self.misread_chance = min(100.0, max(0.0, float(skill_extras.get("misread_chance", self.misread_chance))))
            self.misread_ms = max(0.0, float(skill_extras.get("misread_ms", self.misread_ms)))
            self.stamina_max = max(0.0, float(skill_extras.get("stamina_max", self.stamina_max)))
            self.stamina_regen = max(0.0, float(skill_extras.get("stamina_regen", self.stamina_regen)))
            self.strain_step_pct = max(0.0, float(skill_extras.get("strain_step_pct", self.strain_step_pct)))
            self.strain_misread_pct = max(0.0, float(skill_extras.get("strain_misread_pct", self.strain_misread_pct)))
            self.strain_skill_ms = max(0.0, float(skill_extras.get("strain_skill_ms", self.strain_skill_ms)))
            self.strain_regen_pct = max(0.0, float(skill_extras.get("strain_regen_pct", self.strain_regen_pct)))

        if LOADED_MANIA and maniaplayer:
            try:
                maniaplayer.BBOX = bbox
                maniaplayer.JUDGEMENENT_LINE = judgement_line
                maniaplayer.LANES = list(lanes)
                maniaplayer.INPUT_DELAY_MS = self.input_delay_ms
                maniaplayer.DELAY_MS = self.input_delay_ms
                maniaplayer.SKILL_LEVEL = self.skill_level
                maniaplayer.SKILL_LEVEL_MS = self.skill_level
                maniaplayer.MISREAD_CHANCE = self.misread_chance
                maniaplayer.MISREAD_MS = self.misread_ms
                maniaplayer.STAMINA_MAX = self.stamina_max
                maniaplayer.STAMINA_REGEN = self.stamina_regen
                maniaplayer.STRAIN_STEP_PCT = self.strain_step_pct
                maniaplayer.STRAIN_MISREAD_PCT = self.strain_misread_pct
                maniaplayer.STRAIN_SKILL_MS = self.strain_skill_ms
                maniaplayer.STRAIN_REGEN_PCT = self.strain_regen_pct
                if keys:
                    maniaplayer.KEYS = [str(k).lower() for k in keys]
                for i in range(min(4, len(lanes))):
                    setattr(maniaplayer, f"LANE{i+1}", lanes[i])
                    if keys and i < len(keys):
                        setattr(maniaplayer, f"KEY{i+1}", str(keys[i]).lower())
            except Exception:
                pass

        self.active_bbox = bbox
        self.active_jl = judgement_line

        if new_count != self.key_count:
            self.set_key_count(new_count, lanes=lanes, keys=keys)
        else:
            self.active_lanes = list(lanes)
            if keys:
                self.active_keys = [str(k).lower() for k in keys]
            self.parsed_keys = [parse_key(k) for k in self.active_keys]
            self._rebuild_lane_visualizer()
            self._sync_with_maniaplayer()

        self.config_updated = True
        keys_str = "/".join(self.active_keys).upper()
        skill_str = f" | Skill: ±{self._round_fmt(self.skill_level, 1)}ms" if self.skill_level > 0 else ""
        self.lbl_status_sub.config(text=f"Updated: {self.key_count} Keys [{keys_str}] | Delay: {self.input_delay_ms}ms{skill_str} | BBOX {bbox}")


    def open_calibrator(self):
        # Prevent opening multiple calibration windows concurrently
        if hasattr(self, "calib_window") and self.calib_window is not None:
            try:
                if self.calib_window.winfo_exists():
                    self.calib_window.lift()
                    self.calib_window.focus_force()
                    return
            except Exception:
                pass

        calib_win = tk.Toplevel(self.root)
        self.calib_window = calib_win
        calib_win.lift()
        calib_win.attributes("-topmost", False)

        base_dir = get_base_dir()
        target_file = find_target_script()
        
        candidates_cfg = [Path.cwd() / "mania_config.json", base_dir / "mania_config.json"]
        config_path = next((p for p in candidates_cfg if p.exists()), base_dir / "mania_config.json")

        presets_dir = Path.cwd() / "presets" if (Path.cwd() / "presets").exists() else (base_dir / "presets")
        backups_dir = Path.cwd() / "backups" if (Path.cwd() / "backups").exists() else (base_dir / "backups")
        presets_dir.mkdir(parents=True, exist_ok=True)
        backups_dir.mkdir(parents=True, exist_ok=True)

        harness_mod = get_harness_module()

        self.calib_app = harness_mod.ManiaHarnessApp(
            calib_win,
            on_save_callback=self.on_calibrator_update,
            target_file=target_file,
            config_file=config_path,
            presets_dir=presets_dir,
            backups_dir=backups_dir
        )

        def on_calib_close():
            self._reload_script()
            self._sync_with_maniaplayer()
            self.calib_window = None
            self.calib_app = None
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

        # Release keys safely using parsed representations
        keys_to_release = getattr(self, "parsed_keys", self.active_keys)
        for k in keys_to_release:
            try:
                self.keyboard.release(k)
            except Exception:
                pass
        self.lane_states = [False] * self.key_count

    def _make_skill_sim(self, num_lanes):
        """Builds a Misread/Stamina/Strain SkillSimulator from current settings; None when features are off."""
        sim_cls = getattr(maniaplayer, "SkillSimulator", None) if LOADED_MANIA else None
        if sim_cls is None:
            return None
        sim = sim_cls(
            num_lanes,
            misread_chance=self.misread_chance,
            misread_ms=self.misread_ms,
            stamina_max=self.stamina_max,
            stamina_regen=self.stamina_regen,
            strain_step_pct=self.strain_step_pct,
            strain_misread_pct=self.strain_misread_pct,
            strain_skill_ms=self.strain_skill_ms,
            strain_regen_pct=self.strain_regen_pct,
            base_skill_level=self.skill_level,
        )
        return sim if sim.enabled else None

    def _bot_worker(self):
        """Ultra-fast capture worker achieving 60-240+ FPS with dynamic coordinate & key reloading (1-20 keys).
        Fully optimized for 7K-20K layouts: pre-packed lane records, binary min-heap for delay/jitter,
        in-place visualizer buffer updates, and zero per-frame heap allocations."""
        jl = self.active_jl
        lanes = list(self.active_lanes)
        bbox = self.active_bbox
        num_lanes = len(lanes)
        keys = [parse_key(k) for k in self.active_keys[:num_lanes]]
        pressed_states = [False] * num_lanes
        current_hits = [False] * num_lanes
        lane_hold_offsets = [0.0] * num_lanes
        delayed_events = [] # Binary min-heap: (due_time, seq, action, key, lane_idx)
        event_seq = 0
        delay_sec = max(0.0, float(self.input_delay_ms) / 1000.0)
        skill_level = self.skill_level
        skill_sim = self._make_skill_sim(num_lanes)
        self.active_skill_sim = skill_sim
        has_delay_or_skill = (delay_sec > 0 or skill_level > 0 or (skill_sim is not None and (skill_sim.curr_skill_level > 0 or skill_sim.strain_skill_ms > 0)))
        lane_skipped = [False] * num_lanes
        thresh_sums = tuple(90 for _ in range(num_lanes))

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
                    jl_clamp = min(max(0, jl), h - 1)
                    stride = w * 4
                    offsets = [(jl_clamp * stride) + (min(max(0, lx), w - 1) * 4) for lx in lanes]
                    lane_records = tuple((offsets[i], thresh_sums[i], keys[i], i) for i in range(num_lanes))

                    while self.is_running and self.p_status:
                        # Process due delayed events in exact chronological order before grab
                        if has_delay_or_skill and delayed_events:
                            t_now = time.perf_counter()
                            while delayed_events and delayed_events[0][0] <= t_now:
                                _, _, act, k, _ = heapq.heappop(delayed_events)
                                if act == 1:
                                    try:
                                        self.keyboard.press(k)
                                    except Exception:
                                        pass
                                else:
                                    try:
                                        self.keyboard.release(k)
                                    except Exception:
                                        pass

                        # Check dynamic updates from calibrator or GUI
                        if self.config_updated or current_bbox != self.active_bbox:
                            bbox = self.active_bbox
                            current_bbox = bbox
                            jl = self.active_jl
                            lanes = list(self.active_lanes)
                            num_lanes = len(lanes)
                            keys = [parse_key(k) for k in self.active_keys[:num_lanes]]
                            pressed_states = [False] * num_lanes
                            current_hits = [False] * num_lanes
                            lane_hold_offsets = [0.0] * num_lanes
                            thresh_sums = tuple(90 for _ in range(num_lanes))
                            delay_sec = max(0.0, float(self.input_delay_ms) / 1000.0)
                            skill_level = self.skill_level
                            skill_sim = self._make_skill_sim(num_lanes)
                            self.active_skill_sim = skill_sim
                            has_delay_or_skill = (delay_sec > 0 or skill_level > 0 or (skill_sim is not None and (skill_sim.curr_skill_level > 0 or skill_sim.strain_skill_ms > 0)))
                            lane_skipped = [False] * num_lanes
                            delayed_events.clear()
                            monitor = {
                                "left": bbox[0],
                                "top": bbox[1],
                                "width": max(1, bbox[2] - bbox[0]),
                                "height": max(1, bbox[3] - bbox[1])
                            }
                            w = monitor["width"]
                            h = monitor["height"]
                            jl_clamp = min(max(0, jl), h - 1)
                            stride = w * 4
                            offsets = [(jl_clamp * stride) + (min(max(0, lx), w - 1) * 4) for lx in lanes]
                            lane_records = tuple((offsets[i], thresh_sums[i], keys[i], i) for i in range(num_lanes))
                            self.config_updated = False

                        shot = sct.grab(monitor)
                        raw = shot.raw
                        t_now = time.perf_counter()

                        # Process due delayed events immediately after grab
                        if has_delay_or_skill and delayed_events:
                            while delayed_events and delayed_events[0][0] <= t_now:
                                _, _, act, k, _ = heapq.heappop(delayed_events)
                                if act == 1:
                                    try:
                                        self.keyboard.press(k)
                                    except Exception:
                                        pass
                                else:
                                    try:
                                        self.keyboard.release(k)
                                    except Exception:
                                        pass

                        for off, th, k, i in lane_records:
                            hit = (raw[off] + raw[off + 1] + raw[off + 2]) > th
                            current_hits[i] = hit

                            if hit:
                                if not pressed_states[i]:
                                    pressed_states[i] = True
                                    if skill_sim is not None and not skill_sim.allow_press(i, t_now):
                                        lane_skipped[i] = True
                                        continue
                                    lane_skipped[i] = False
                                    if has_delay_or_skill:
                                        eff_skill = skill_sim.curr_skill_level if skill_sim is not None else skill_level
                                        var_sec = (random.uniform(-eff_skill, eff_skill) / 1000.0) if eff_skill > 0 else 0.0
                                        eff_delay = max(0.0, delay_sec + var_sec)
                                        lane_hold_offsets[i] = eff_delay
                                        if eff_delay > 0:
                                            event_seq += 1
                                            heapq.heappush(delayed_events, (t_now + eff_delay, event_seq, 1, k, i))
                                        else:
                                            try:
                                                self.keyboard.press(k)
                                            except Exception:
                                                pass
                                    else:
                                        try:
                                            self.keyboard.press(k)
                                        except Exception:
                                            pass
                            else:
                                if pressed_states[i]:
                                    pressed_states[i] = False
                                    if lane_skipped[i]:
                                        lane_skipped[i] = False
                                        continue
                                    if has_delay_or_skill:
                                        hold_offset = lane_hold_offsets[i]
                                        if hold_offset > 0:
                                            event_seq += 1
                                            heapq.heappush(delayed_events, (t_now + hold_offset, event_seq, 0, k, i))
                                        else:
                                            try:
                                                self.keyboard.release(k)
                                            except Exception:
                                                pass
                                    else:
                                        try:
                                            self.keyboard.release(k)
                                        except Exception:
                                            pass

                        # In-place update: zero heap allocation per frame
                        if len(self.lane_states) == num_lanes:
                            self.lane_states[:] = current_hits
                        else:
                            self.lane_states = list(current_hits)
                        self.loop_count += 1

                    # Cleanup on stop
                    self.active_skill_sim = None
                    delayed_events.clear()
                    for k in keys:
                        try:
                            self.keyboard.release(k)
                        except Exception:
                            pass
                    return
            except Exception:
                self.active_skill_sim = None

        # Fallback using standard ImageGrab.grab()
        while self.is_running and self.p_status:
            try:
                if self.config_updated:
                    bbox = self.active_bbox
                    jl = self.active_jl
                    lanes = list(self.active_lanes)
                    num_lanes = len(lanes)
                    keys = [parse_key(k) for k in self.active_keys[:num_lanes]]
                    pressed_states = [False] * num_lanes
                    current_hits = [False] * num_lanes
                    lane_hold_offsets = [0.0] * num_lanes
                    thresh_sums = tuple(90 for _ in range(num_lanes))
                    delay_sec = max(0.0, float(self.input_delay_ms) / 1000.0)
                    skill_level = self.skill_level
                    skill_sim = self._make_skill_sim(num_lanes)
                    self.active_skill_sim = skill_sim
                    has_delay_or_skill = (delay_sec > 0 or skill_level > 0 or (skill_sim is not None and (skill_sim.curr_skill_level > 0 or skill_sim.strain_skill_ms > 0)))
                    lane_skipped = [False] * num_lanes
                    delayed_events.clear()
                    self.config_updated = False

                t_now = time.perf_counter()
                if has_delay_or_skill and delayed_events:
                    while delayed_events and delayed_events[0][0] <= t_now:
                        _, _, act, k, _ = heapq.heappop(delayed_events)
                        if act == 1:
                            try:
                                self.keyboard.press(k)
                            except Exception:
                                pass
                        else:
                            try:
                                self.keyboard.release(k)
                            except Exception:
                                pass

                check = ImageGrab.grab(bbox=bbox)
                px = check.load()
                t_now = time.perf_counter()

                w = max(1, bbox[2] - bbox[0])
                h = max(1, bbox[3] - bbox[1])
                jl_clamp = min(max(0, jl), h - 1)

                for i in range(num_lanes):
                    lx = min(max(0, lanes[i]), w - 1)
                    hit = sum(px[lx, jl_clamp][:3]) > thresh_sums[i]
                    current_hits[i] = hit
                    k = keys[i]

                    if hit:
                        if not pressed_states[i]:
                            pressed_states[i] = True
                            if skill_sim is not None and not skill_sim.allow_press(i, t_now):
                                lane_skipped[i] = True
                                continue
                            lane_skipped[i] = False
                            if has_delay_or_skill:
                                eff_skill = skill_sim.curr_skill_level if skill_sim is not None else skill_level
                                var_sec = (random.uniform(-eff_skill, eff_skill) / 1000.0) if eff_skill > 0 else 0.0
                                eff_delay = max(0.0, delay_sec + var_sec)
                                lane_hold_offsets[i] = eff_delay
                                if eff_delay > 0:
                                    event_seq += 1
                                    heapq.heappush(delayed_events, (t_now + eff_delay, event_seq, 1, k, i))
                                else:
                                    try:
                                        self.keyboard.press(k)
                                    except Exception:
                                        pass
                            else:
                                try:
                                    self.keyboard.press(k)
                                except Exception:
                                    pass
                    else:
                        if pressed_states[i]:
                            pressed_states[i] = False
                            if lane_skipped[i]:
                                lane_skipped[i] = False
                                continue
                            if has_delay_or_skill:
                                hold_offset = lane_hold_offsets[i]
                                if hold_offset > 0:
                                    event_seq += 1
                                    heapq.heappush(delayed_events, (t_now + hold_offset, event_seq, 0, k, i))
                                else:
                                    try:
                                        self.keyboard.release(k)
                                    except Exception:
                                        pass
                            else:
                                try:
                                    self.keyboard.release(k)
                                except Exception:
                                    pass

                if len(self.lane_states) == num_lanes:
                    self.lane_states[:] = current_hits
                else:
                    self.lane_states = list(current_hits)
                self.loop_count += 1
            except Exception:
                pass

        # Cleanup fallback
        self.active_skill_sim = None
        delayed_events.clear()
        for k in keys:
            try:
                self.keyboard.release(k)
            except Exception:
                pass

    # -------------------------------------------------------------
    # Global Hotkeys Listener (F1, F2, F4)
    # -------------------------------------------------------------
    def _start_global_hotkeys(self):
        def on_press(key):
            try:
                if key == Key.f1:
                    self.root.after(0, self.start_bot)
                elif key == Key.f2:
                    self.root.after(0, self.stop_bot)
                elif key == Key.f4:
                    self.root.after(0, self.on_close)
            except Exception:
                pass

        self.listener = Listener(on_press=on_press)
        self.listener.daemon = True
        self.listener.start()

    @staticmethod
    def _round_fmt(val, decimals=1):
        """Rounds a float and formats it cleanly without long trailing zeroes (e.g. 5.0 -> '5', 5.25 -> '5.3')."""
        try:
            f = float(val)
            r = round(f, decimals)
            if r.is_integer():
                return str(int(r))
            return f"{r:.{decimals}f}".rstrip("0").rstrip(".")
        except Exception:
            return str(val)

    # -------------------------------------------------------------
    # UI Refresh Loop (FPS & Lane Visualizer)
    # -------------------------------------------------------------
    def _start_ui_refresh_loop(self):
        self._last_rendered_lane_states = []

        def refresh():
            now = time.time()
            elapsed = now - self.last_fps_time
            if elapsed >= 1.0:
                self.current_fps = round(self.loop_count / elapsed, 1)
                self.lbl_fps.config(text=f"{self._round_fmt(self.current_fps, 1)} FPS")
                self.loop_count = 0
                self.last_fps_time = now

            n = min(len(self.lane_pads), len(self.lane_states))
            if len(self._last_rendered_lane_states) != n:
                self._last_rendered_lane_states = [None] * n

            for i in range(n):
                active = self.lane_states[i]
                if active != self._last_rendered_lane_states[i]:
                    self._last_rendered_lane_states[i] = active
                    pad, l_name, l_key, l_state, color = self.lane_pads[i]
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

            # Live Skill / Stamina / Misread / Strain Display
            if hasattr(self, "lbl_live_stamina"):
                if self.active_skill_sim is not None:
                    stats = self.active_skill_sim.get_live_stats()
                    stamina = stats["stamina"]
                    stamina_max = stats["stamina_max"]
                    stamina_pct = stats["stamina_pct"]
                    steps = stats["strain_steps"]
                    misread_chance = stats["misread_chance"]
                    regen_per_20ms = stats["regen_per_20ms"]

                    if stamina_max > 0:
                        s_cur = self._round_fmt(stamina, 1)
                        s_max = self._round_fmt(stamina_max, 1)
                        s_pct = round(stamina_pct)
                        self.lbl_live_stamina.config(text=f"{s_cur} / {s_max} ({s_pct:.0f}%)")
                        c_w = self.canvas_stamina_bar.winfo_width()
                        c_h = self.canvas_stamina_bar.winfo_height()
                        if c_w > 10 and c_h > 2:
                            self.canvas_stamina_bar.delete("bar")
                            fill_w = max(0, min(c_w, int(c_w * (stamina / stamina_max))))
                            bar_color = "#10b981" if stamina_pct > 50 else ("#f59e0b" if stamina_pct > 20 else "#ef4444")
                            if fill_w > 0:
                                self.canvas_stamina_bar.create_rectangle(0, 0, fill_w, c_h, fill=bar_color, width=0, tags="bar")
                    else:
                        self.lbl_live_stamina.config(text="Unlimited (Off)")
                        c_w = self.canvas_stamina_bar.winfo_width()
                        c_h = self.canvas_stamina_bar.winfo_height()
                        if c_w > 10 and c_h > 2:
                            self.canvas_stamina_bar.delete("bar")
                            self.canvas_stamina_bar.create_rectangle(0, 0, c_w, c_h, fill="#334155", width=0, tags="bar")

                    # Stamina Regen
                    if stamina_max > 0:
                        reg_str = self._round_fmt(regen_per_20ms, 2)
                        if steps > 0 and self.strain_regen_pct > 0:
                            red_pct = self._round_fmt(min(100.0, steps * self.strain_regen_pct), 1)
                            self.lbl_live_regen.config(text=f"+{reg_str}/20ms (-{red_pct}%)", fg="#f59e0b" if float(red_pct) < 100 else "#ef4444")
                        else:
                            self.lbl_live_regen.config(text=f"+{reg_str}/20ms", fg="#34d399")
                    else:
                        self.lbl_live_regen.config(text="Off", fg="#64748b")

                    # Misread Chance
                    if misread_chance > 0 or self.misread_chance > 0:
                        mis_str = self._round_fmt(misread_chance, 1)
                        if steps > 0 and self.strain_misread_pct > 0:
                            add_pct = self._round_fmt(steps * self.strain_misread_pct, 1)
                            self.lbl_live_misread.config(text=f"{mis_str}% (+{add_pct}%)", fg="#fb7185")
                        else:
                            dur_str = self._round_fmt(self.misread_ms, 1)
                            self.lbl_live_misread.config(text=f"{mis_str}% ({dur_str}ms)", fg="#fb7185")
                    else:
                        self.lbl_live_misread.config(text="0% (Off)", fg="#64748b")

                    # Strain Status
                    if self.strain_step_pct > 0 and stamina_max > 0:
                        if steps > 0:
                            mis_add = self._round_fmt(steps * self.strain_misread_pct, 1)
                            del_add = self._round_fmt(steps * self.strain_skill_ms, 1)
                            reg_sub = self._round_fmt(steps * self.strain_regen_pct, 1)
                            self.lbl_live_strain.config(
                                text=f"Strain: Tier {steps} (+{mis_add}% Misread, +{del_add}ms Delay, -{reg_sub}% Regen)",
                                fg="#f97316"
                            )
                        else:
                            lost_pct = max(0.0, (1.0 - (stamina / stamina_max)) * 100.0)
                            rem = self.strain_step_pct - (lost_pct % self.strain_step_pct)
                            rem_str = self._round_fmt(rem, 1)
                            self.lbl_live_strain.config(
                                text=f"Strain: Nominal (Step in {rem_str}% loss)",
                                fg="#94a3b8"
                            )
                    else:
                        self.lbl_live_strain.config(text="Strain: Off", fg="#64748b")
                else:
                    # Idle / bot stopped
                    if self.stamina_max > 0:
                        s_max = self._round_fmt(self.stamina_max, 1)
                        self.lbl_live_stamina.config(text=f"{s_max} clicks (Ready)")
                        c_w = self.canvas_stamina_bar.winfo_width()
                        c_h = self.canvas_stamina_bar.winfo_height()
                        if c_w > 10 and c_h > 2:
                            self.canvas_stamina_bar.delete("bar")
                            self.canvas_stamina_bar.create_rectangle(0, 0, c_w, c_h, fill="#10b981", width=0, tags="bar")
                        r_str = self._round_fmt(self.stamina_regen, 2)
                        self.lbl_live_regen.config(text=f"+{r_str}/20ms", fg="#34d399")
                    else:
                        self.lbl_live_stamina.config(text="Unlimited (Off)")
                        c_w = self.canvas_stamina_bar.winfo_width()
                        c_h = self.canvas_stamina_bar.winfo_height()
                        if c_w > 10 and c_h > 2:
                            self.canvas_stamina_bar.delete("bar")
                            self.canvas_stamina_bar.create_rectangle(0, 0, c_w, c_h, fill="#334155", width=0, tags="bar")
                        self.lbl_live_regen.config(text="Off", fg="#64748b")

                    if self.misread_chance > 0:
                        m_str = self._round_fmt(self.misread_chance, 1)
                        d_str = self._round_fmt(self.misread_ms, 1)
                        self.lbl_live_misread.config(text=f"{m_str}% ({d_str}ms)", fg="#fb7185")
                    else:
                        self.lbl_live_misread.config(text="0% (Off)", fg="#64748b")

                    if self.strain_step_pct > 0 and self.stamina_max > 0:
                        s_step = self._round_fmt(self.strain_step_pct, 1)
                        s_mis = self._round_fmt(self.strain_misread_pct, 1)
                        s_ms = self._round_fmt(self.strain_skill_ms, 1)
                        s_reg = self._round_fmt(self.strain_regen_pct, 1)
                        self.lbl_live_strain.config(
                            text=f"Strain: Every {s_step}% lost (+{s_mis}%, +{s_ms}ms, -{s_reg}%)",
                            fg="#94a3b8"
                        )
                    else:
                        self.lbl_live_strain.config(text="Strain: Off", fg="#64748b")

            self.root.after(30, refresh)

        self.root.after(30, refresh)

    def on_close(self):
        self.is_running = False
        self.p_status = False
        keys_to_release = getattr(self, "parsed_keys", getattr(self, "active_keys", []))
        for k in keys_to_release:
            try:
                self.keyboard.release(k)
            except Exception:
                pass
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ModernManiaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
