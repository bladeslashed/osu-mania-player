"""
Mania Player Calibration Harness
Interactive GUI tool for calibrating Bounding Box (BBOX), Lane targets, and Keybinds
for maniaplayer.py, mania_config.json, and settings.json.

Features:
- Change keybinds for each lane (custom keys or quick presets: QW[], DFJK, ASKL, ZX./)
- Presets manager: Save and load custom namable JSON presets from the 'presets/' folder
- Always on Top support so it stays above osu!mania and all other windows
- Disappearing window during screenshot capture (instant or countdown) and reappearing cleanly
- Live synchronization to the active Mania Player
- Load existing screenshots from disk
- Interactive Bounding Box drag & resize with 1px snap option
- Interactive Lane target point-and-click or drag markers (LANE1..LANE4)
- Live pixel magnifier (loupe) with RGB & brightness inspector
- Live BBox preview strip showing note detection preview (> 30 threshold)
- Direct load/save to maniaplayer.py (with automatic backups in 'backups/' folder) & JSON configs
"""

import os
import sys
import re
import ast
import time
import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

# Pillow for image processing and Tkinter integration
try:
    from PIL import Image, ImageTk, ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# MSS for high-performance screen capture fallback
try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

# Enable High-DPI awareness on Windows so coordinates match 1:1 true screen pixels
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


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT_DIR = get_base_dir()


def find_default_target_file() -> Path:
    script_dir = ROOT_DIR
    candidates = [
        script_dir / "maniaplayer.py",
        Path.cwd().resolve() / "maniaplayer.py",
        script_dir / "Pre Vibecoded" / "maniaplayer.py",
        script_dir.parent / "Pre Vibecoded" / "maniaplayer.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    return script_dir / "maniaplayer.py"


def find_default_config_file() -> Path:
    script_dir = ROOT_DIR
    candidates = [
        script_dir / "mania_config.json",
        Path.cwd().resolve() / "mania_config.json",
        script_dir / "settings.json",
        Path.cwd().resolve() / "settings.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return script_dir / "mania_config.json"


DEFAULT_TARGET_FILE = find_default_target_file()
DEFAULT_CONFIG_FILE = find_default_config_file()
DEFAULT_SCREENSHOT = ROOT_DIR / "Screenshot.png"
DEFAULT_BACKUPS_DIR = ROOT_DIR / "backups"
DEFAULT_PRESETS_DIR = ROOT_DIR / "presets"

# Ensure essential runtime directories exist in script and current working directory
DEFAULT_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
(Path.cwd() / "backups").mkdir(parents=True, exist_ok=True)
(Path.cwd() / "presets").mkdir(parents=True, exist_ok=True)

LANE_COLORS = [
    "#38bdf8",  # Lane 1: Cyan / Sky
    "#4ade80",  # Lane 2: Bright Green
    "#fb923c",  # Lane 3: Orange
    "#c084fc",  # Lane 4: Purple
    "#f43f5e",  # Lane 5: Rose
    "#eab308",  # Lane 6: Yellow
    "#06b6d4",  # Lane 7: Teal
    "#a855f7",  # Lane 8: Violet
    "#ec4899",  # Lane 9: Pink
    "#10b981",  # Lane 10: Emerald
    "#3b82f6",  # Lane 11: Blue
    "#f97316",  # Lane 12: Bright Orange
    "#84cc16",  # Lane 13: Lime
    "#14b8a6",  # Lane 14: Dark Teal
    "#8b5cf6",  # Lane 15: Indigo
    "#d946ef",  # Lane 16: Magenta
    "#ef4444",  # Lane 17: Red
    "#0ea5e9",  # Lane 18: Ocean
    "#22c55e",  # Lane 19: Pure Green
    "#f59e0b",  # Lane 20: Amber
]


def get_lane_color(i: int) -> str:
    return LANE_COLORS[i % len(LANE_COLORS)]


DEFAULT_KEY_LAYOUTS = {
    1: ["space"],
    2: ["d", "k"],
    3: ["d", "space", "k"],
    4: ["q", "w", "[", "]"],
    5: ["d", "f", "space", "j", "k"],
    6: ["s", "d", "f", "j", "k", "l"],
    7: ["s", "d", "f", "space", "j", "k", "l"],
    8: ["a", "s", "d", "f", "j", "k", "l", ";"],
    9: ["a", "s", "d", "f", "space", "j", "k", "l", ";"],
    10: ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";"],
    11: ["a", "s", "d", "f", "g", "space", "h", "j", "k", "l", ";"],
    12: ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]"],
    13: ["q", "w", "e", "r", "t", "y", "space", "u", "i", "o", "p", "[", "]"],
    14: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "[", "]"],
    15: ["1", "2", "3", "4", "5", "6", "7", "space", "8", "9", "0", "-", "=", "[", "]"],
    16: ["1", "2", "3", "4", "5", "6", "7", "8", "q", "w", "e", "r", "u", "i", "o", "p"],
    17: ["1", "2", "3", "4", "5", "6", "7", "8", "space", "q", "w", "e", "r", "u", "i", "o", "p"],
    18: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "q", "w", "e", "r", "u", "i", "o", "p", "["],
    19: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "space", "q", "w", "e", "r", "u", "i", "o", "p", "["],
    20: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
}

ALL_20_KEYS = [
    "q", "w", "e", "r", "t", "y", "u", "i", "o", "p",
    "a", "s", "d", "f", "g", "h", "j", "k", "l", ";"
]


class ManiaHarnessApp:
    def __init__(self, root: tk.Tk, on_save_callback=None, target_file: Path = None, config_file: Path = None, presets_dir: Path = None, backups_dir: Path = None):
        self.root = root
        self.on_save_callback = on_save_callback

        self.root.title("Mania Player Calibration Harness v1.3.0")
        self.root.geometry("1320x840")
        self.root.minsize(1080, 690)

        # Mania Harness topmost setting (defaults to False)
        self.stay_on_top = tk.BooleanVar(value=False)
        try:
            self.root.attributes("-topmost", False)
        except Exception:
            pass

        # Target file resolution
        if target_file is not None:
            self.target_file = Path(target_file)
        else:
            self.target_file = find_default_target_file()

        if config_file is not None:
            self.config_file = Path(config_file)
        else:
            self.config_file = find_default_config_file()

        # Presets directory
        if presets_dir is not None:
            self.presets_dir = Path(presets_dir)
        else:
            self.presets_dir = self.target_file.parent / "presets"
        self.presets_dir.mkdir(parents=True, exist_ok=True)

        # Backups directory (dedicated folder for automatic target backups)
        if backups_dir is not None:
            self.backups_dir = Path(backups_dir)
        else:
            self.backups_dir = self.target_file.parent / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)

        self.screenshot_path = self.target_file.parent / "Screenshot.png"

        self.current_image: Image.Image = None
        self.tk_image: ImageTk.PhotoImage = None
        self.zoom_factor = 1.0

        # Calibration parameters
        self.bbox_left = 677
        self.bbox_top = 953
        self.bbox_right = 1225
        self.bbox_bottom = 954
        self.judgement_line = 0
        self.input_delay_ms = 0
        self.var_delay_ms = tk.IntVar(value=0)
        self.skill_level = 0
        self.var_skill_level = tk.IntVar(value=0)

        # Skill simulation extras: Misread, Stamina, and Strain
        self.misread_chance = 0.0
        self.misread_ms = 0.0
        self.stamina_max = 0.0
        self.stamina_regen = 0.0
        self.strain_step_pct = 0.0
        self.strain_misread_pct = 0.0
        self.strain_skill_ms = 0.0
        self.strain_regen_pct = 0.0
        self.var_misread_chance = tk.StringVar(value="0")
        self.var_misread_ms = tk.StringVar(value="0")
        self.var_stamina_max = tk.StringVar(value="0")
        self.var_stamina_regen = tk.StringVar(value="0.0")
        self.var_strain_step_pct = tk.StringVar(value="0")
        self.var_strain_misread_pct = tk.StringVar(value="0")
        self.var_strain_skill_ms = tk.StringVar(value="0")
        self.var_strain_regen_pct = tk.StringVar(value="0")

        # Lane target positions (relative to bbox_left) and keybinds (1 to 20 keys)
        self.key_count = 4
        self.lane_rel_x = [39, 215, 353, 502]
        self.lane_keys = ["q", "w", "[", "]"]

        # Interaction mode: 'box' or 'lane'
        self.current_mode = "box"
        self.selected_lane_idx = 0  # 0..(key_count-1)

        # Drag tracking
        self.is_dragging_box = False
        self.is_resizing_box = False
        self.is_moving_box = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.active_handle = None
        self.active_drag_lane = None

        self._build_ui()
        self._bind_events()

        # Load initial values after UI elements are constructed
        self.load_from_target_file(silent=True)

        # Try loading an existing screenshot on startup if available
        self._try_load_initial_image()

    def _toggle_topmost(self):
        try:
            self.root.attributes("-topmost", self.stay_on_top.get())
        except Exception:
            pass

    def _build_ui(self):
        # Apply dark modern theme
        self.bg_main = "#18181b"
        self.bg_panel = "#27272a"
        self.bg_input = "#3f3f46"
        self.fg_main = "#f4f4f5"
        self.fg_dim = "#a1a1aa"
        self.accent = "#38bdf8"
        self.accent_hover = "#0284c7"

        self.root.configure(bg=self.bg_main)

        # Style configuration
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure(".", background=self.bg_panel, foreground=self.fg_main)
        self.style.configure("TLabel", background=self.bg_panel, foreground=self.fg_main)
        self.style.configure("TFrame", background=self.bg_panel)
        self.style.configure(
            "TCombobox",
            fieldbackground="#1e293b",
            background=self.bg_panel,
            foreground="#ffffff",
            selectbackground="#0284c7",
            selectforeground="#ffffff",
            arrowcolor="#38bdf8",
            font=("Segoe UI", 9, "bold")
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", "#1e293b"),
                ("active", "#334155"),
                ("focus", "#1e293b"),
                ("disabled", "#18181b")
            ],
            foreground=[
                ("readonly", "#ffffff"),
                ("active", "#ffffff"),
                ("focus", "#ffffff"),
                ("disabled", "#71717a")
            ],
            selectbackground=[
                ("readonly", "#0284c7"),
                ("active", "#0284c7"),
                ("focus", "#0284c7")
            ],
            selectforeground=[
                ("readonly", "#ffffff"),
                ("active", "#ffffff"),
                ("focus", "#ffffff")
            ],
            background=[
                ("readonly", "#27272a"),
                ("active", "#3f3f46")
            ],
            arrowcolor=[
                ("readonly", "#38bdf8"),
                ("active", "#ffffff")
            ]
        )

        # Dropdown popdown listbox styling for crisp readability
        self.root.option_add("*TCombobox*Listbox.background", "#1e293b")
        self.root.option_add("*TCombobox*Listbox.foreground", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#0284c7")
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 9, "bold"))

        self.style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), foreground=self.accent)
        self.style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground=self.fg_dim)

        # Top Control Bar
        top_bar = tk.Frame(self.root, bg=self.bg_panel, pady=6, padx=10, relief="flat")
        top_bar.pack(side=tk.TOP, fill=tk.X)

        # Screenshot buttons
        tk.Label(top_bar, text="Capture:", bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))

        self.btn_capture_now = tk.Button(
            top_bar, text="📸 Capture Now", bg="#2563eb", fg="white", activebackground="#1d4ed8",
            activeforeground="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=3,
            cursor="hand2", command=self.capture_screen_now
        )
        self.btn_capture_now.pack(side=tk.LEFT, padx=3)

        self.btn_capture_delay = tk.Button(
            top_bar, text="⏱️ In 2s (Switch Window)", bg="#4b5563", fg="white", activebackground="#374151",
            activeforeground="white", font=("Segoe UI", 9), relief="flat", padx=8, pady=3,
            cursor="hand2", command=lambda: self.capture_screen_delayed(2.0)
        )
        self.btn_capture_delay.pack(side=tk.LEFT, padx=3)

        self.btn_load_file = tk.Button(
            top_bar, text="📂 Load Screenshot", bg="#4b5563", fg="white", activebackground="#374151",
            activeforeground="white", font=("Segoe UI", 9), relief="flat", padx=8, pady=3,
            cursor="hand2", command=self.browse_and_load_image
        )
        self.btn_load_file.pack(side=tk.LEFT, padx=3)

        # Always on Top checkbox
        chk_top = tk.Checkbutton(
            top_bar, text="📌 Always on Top", variable=self.stay_on_top,
            bg=self.bg_panel, fg=self.fg_dim, selectcolor=self.bg_input,
            activebackground=self.bg_panel, activeforeground=self.fg_main,
            font=("Segoe UI", 9), relief="flat", command=self._toggle_topmost
        )
        chk_top.pack(side=tk.LEFT, padx=(6, 4))

        # Separator
        tk.Frame(top_bar, bg="#52525b", width=1).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        # Mode Selection
        tk.Label(top_bar, text="Mode:", bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))

        self.btn_mode_box = tk.Button(
            top_bar, text="🔲 Box Mode (B)", bg=self.accent if self.current_mode == "box" else "#3f3f46",
            fg="black" if self.current_mode == "box" else "white", font=("Segoe UI", 9, "bold"),
            relief="flat", padx=10, pady=3, cursor="hand2", command=lambda: self.set_mode("box")
        )
        self.btn_mode_box.pack(side=tk.LEFT, padx=3)

        self.btn_mode_lane = tk.Button(
            top_bar, text="🎯 Lane Mode (L)", bg=self.accent if self.current_mode == "lane" else "#3f3f46",
            fg="black" if self.current_mode == "lane" else "white", font=("Segoe UI", 9, "bold"),
            relief="flat", padx=10, pady=3, cursor="hand2", command=lambda: self.set_mode("lane")
        )
        self.btn_mode_lane.pack(side=tk.LEFT, padx=3)

        # Separator
        tk.Frame(top_bar, bg="#52525b", width=1).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        # Zoom Controls
        tk.Label(top_bar, text="Zoom:", bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        self.btn_zoom_out = tk.Button(top_bar, text="−", bg="#3f3f46", fg="white", relief="flat", padx=6, pady=2, command=self.zoom_out)
        self.btn_zoom_out.pack(side=tk.LEFT, padx=1)
        self.lbl_zoom = tk.Label(top_bar, text="100%", bg=self.bg_panel, fg=self.fg_main, font=("Segoe UI", 9), width=5)
        self.lbl_zoom.pack(side=tk.LEFT, padx=2)
        self.btn_zoom_in = tk.Button(top_bar, text="+", bg="#3f3f46", fg="white", relief="flat", padx=6, pady=2, command=self.zoom_in)
        self.btn_zoom_in.pack(side=tk.LEFT, padx=1)
        self.btn_zoom_fit = tk.Button(top_bar, text="Fit View", bg="#3f3f46", fg="white", relief="flat", padx=6, pady=2, command=self.zoom_fit)
        self.btn_zoom_fit.pack(side=tk.LEFT, padx=3)

        # Right Action Buttons: Save & Live Sync
        self.btn_save_file = tk.Button(
            top_bar, text="💾 Save to maniaplayer.py", bg="#16a34a", fg="white", activebackground="#15803d",
            activeforeground="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=3,
            cursor="hand2", command=self.save_to_target_file
        )
        self.btn_save_file.pack(side=tk.RIGHT, padx=4)

        self.btn_apply_live = tk.Button(
            top_bar, text="⚡ Apply to Player", bg="#0284c7", fg="white", activebackground="#0369a1",
            activeforeground="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=3,
            cursor="hand2", command=self.apply_live_to_player
        )
        self.btn_apply_live.pack(side=tk.RIGHT, padx=4)

        self.btn_copy_code = tk.Button(
            top_bar, text="📋 Copy Code", bg="#4b5563", fg="white", activebackground="#374151",
            activeforeground="white", font=("Segoe UI", 9), relief="flat", padx=8, pady=3,
            cursor="hand2", command=self.copy_python_code
        )
        self.btn_copy_code.pack(side=tk.RIGHT, padx=4)

        self.btn_reload = tk.Button(
            top_bar, text="📥 Reload", bg="#4b5563", fg="white", activebackground="#374151",
            activeforeground="white", font=("Segoe UI", 9), relief="flat", padx=8, pady=3,
            cursor="hand2", command=lambda: self.load_from_target_file(silent=False)
        )
        self.btn_reload.pack(side=tk.RIGHT, padx=4)

        # Main Body: Canvas (Left) + Inspector Sidebar (Right)
        body = tk.Frame(self.root, bg=self.bg_main)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Canvas Frame with scrollbars
        canvas_frame = tk.Frame(body, bg="#121214")
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 4), pady=8)

        self.v_scrollbar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        self.h_scrollbar = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)

        self.canvas = tk.Canvas(
            canvas_frame, bg="#121214", highlightthickness=0,
            xscrollcommand=self.h_scrollbar.set, yscrollcommand=self.v_scrollbar.set
        )
        self.v_scrollbar.config(command=self.canvas.yview)
        self.h_scrollbar.config(command=self.canvas.xview)

        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Sidebar Inspector
        self._build_sidebar(body)

        # Status Bar
        self.status_bar = tk.Frame(self.root, bg="#18181b", height=24)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.lbl_status = tk.Label(
            self.status_bar, text="Ready. Take a screenshot or open an image to calibrate.",
            bg="#18181b", fg=self.fg_dim, font=("Segoe UI", 9), anchor="w", padx=10
        )
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_cursor_info = tk.Label(
            self.status_bar, text="X: -- | Y: -- | RGB: --",
            bg="#18181b", fg=self.accent, font=("Consolas", 9), anchor="e", padx=10
        )
        self.lbl_cursor_info.pack(side=tk.RIGHT)

    def _build_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=self.bg_panel, width=410, padx=12, pady=8)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 8), pady=8)
        sidebar.pack_propagate(False)

        # Target file header
        file_box = tk.LabelFrame(sidebar, text="Target Script & Configuration", bg=self.bg_panel, fg=self.accent, font=("Segoe UI", 9, "bold"), padx=8, pady=4)
        file_box.pack(fill=tk.X, pady=(0, 6))

        lbl_path = tk.Label(file_box, text=f"📄 {self.target_file.name}", bg=self.bg_panel, fg=self.fg_main, font=("Segoe UI", 9, "bold"), anchor="w")
        lbl_path.pack(fill=tk.X)
        lbl_full = tk.Label(file_box, text=str(self.target_file), bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 8), anchor="w")
        lbl_full.pack(fill=tk.X)

        row_fb = tk.Frame(file_box, bg=self.bg_panel)
        row_fb.pack(fill=tk.X, pady=(4, 2))
        btn_open_backups = tk.Button(
            row_fb, text="📁 Backups Folder", bg="#3f3f46", fg="white",
            font=("Segoe UI", 8), relief="flat", padx=6, pady=1, cursor="hand2", command=self.open_backups_folder
        )
        btn_open_backups.pack(side=tk.LEFT)

        # Presets Section
        presets_frame = tk.LabelFrame(sidebar, text="Skin / Keybind Presets", bg=self.bg_panel, fg=self.accent, font=("Segoe UI", 9, "bold"), padx=8, pady=6)
        presets_frame.pack(fill=tk.X, pady=(0, 6))

        row_p1 = tk.Frame(presets_frame, bg=self.bg_panel)
        row_p1.pack(fill=tk.X, pady=2)

        self.cb_presets = ttk.Combobox(row_p1, state="readonly", values=self._get_preset_list(), width=28)
        self.cb_presets.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        presets_list = self._get_preset_list()
        if presets_list:
            self.cb_presets.set(presets_list[0])

        btn_p_refresh = tk.Button(row_p1, text="🔄", bg="#3f3f46", fg="white", relief="flat", padx=4, pady=1, command=self._refresh_presets_list)
        btn_p_refresh.pack(side=tk.LEFT)

        row_p2 = tk.Frame(presets_frame, bg=self.bg_panel)
        row_p2.pack(fill=tk.X, pady=(4, 2))

        btn_p_load = tk.Button(
            row_p2, text="📂 Load Preset", bg="#0284c7", fg="white", activebackground="#0369a1",
            font=("Segoe UI", 8, "bold"), relief="flat", padx=8, pady=2, cursor="hand2", command=self.load_selected_preset
        )
        btn_p_load.pack(side=tk.LEFT, padx=(0, 4))

        btn_p_save = tk.Button(
            row_p2, text="💾 Save As...", bg="#16a34a", fg="white", activebackground="#15803d",
            font=("Segoe UI", 8, "bold"), relief="flat", padx=8, pady=2, cursor="hand2", command=self.save_new_preset
        )
        btn_p_save.pack(side=tk.LEFT, padx=4)

        btn_p_open = tk.Button(
            row_p2, text="📁 Presets Folder", bg="#3f3f46", fg="white",
            font=("Segoe UI", 8), relief="flat", padx=6, pady=2, cursor="hand2", command=self.open_presets_folder
        )
        btn_p_open.pack(side=tk.RIGHT)

        # 1. Bounding Box Inspector Frame
        bbox_frame = tk.LabelFrame(sidebar, text="Bounding Box (BBOX)", bg=self.bg_panel, fg=self.accent, font=("Segoe UI", 9, "bold"), padx=8, pady=6)
        bbox_frame.pack(fill=tk.X, pady=(0, 6))

        grid = tk.Frame(bbox_frame, bg=self.bg_panel)
        grid.pack(fill=tk.X)

        tk.Label(grid, text="Left (X1):", bg=self.bg_panel, fg=self.fg_dim).grid(row=0, column=0, sticky="w", pady=2)
        self.var_left = tk.IntVar(value=self.bbox_left)
        self.spin_left = tk.Spinbox(grid, from_=0, to=9999, textvariable=self.var_left, width=7, command=self._on_bbox_input_changed, bg=self.bg_input, fg=self.fg_main, relief="flat")
        self.spin_left.grid(row=0, column=1, sticky="w", padx=4, pady=2)
        self.spin_left.bind("<KeyRelease>", lambda e: self._on_bbox_input_changed())

        tk.Label(grid, text="Top (Y1):", bg=self.bg_panel, fg=self.fg_dim).grid(row=0, column=2, sticky="w", pady=2)
        self.var_top = tk.IntVar(value=self.bbox_top)
        self.spin_top = tk.Spinbox(grid, from_=0, to=9999, textvariable=self.var_top, width=7, command=self._on_bbox_input_changed, bg=self.bg_input, fg=self.fg_main, relief="flat")
        self.spin_top.grid(row=0, column=3, sticky="w", padx=4, pady=2)
        self.spin_top.bind("<KeyRelease>", lambda e: self._on_bbox_input_changed())

        tk.Label(grid, text="Right (X2):", bg=self.bg_panel, fg=self.fg_dim).grid(row=1, column=0, sticky="w", pady=2)
        self.var_right = tk.IntVar(value=self.bbox_right)
        self.spin_right = tk.Spinbox(grid, from_=0, to=9999, textvariable=self.var_right, width=7, command=self._on_bbox_input_changed, bg=self.bg_input, fg=self.fg_main, relief="flat")
        self.spin_right.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        self.spin_right.bind("<KeyRelease>", lambda e: self._on_bbox_input_changed())

        tk.Label(grid, text="Bottom (Y2):", bg=self.bg_panel, fg=self.fg_dim).grid(row=1, column=2, sticky="w", pady=2)
        self.var_bottom = tk.IntVar(value=self.bbox_bottom)
        self.spin_bottom = tk.Spinbox(grid, from_=0, to=9999, textvariable=self.var_bottom, width=7, command=self._on_bbox_input_changed, bg=self.bg_input, fg=self.fg_main, relief="flat")
        self.spin_bottom.grid(row=1, column=3, sticky="w", padx=4, pady=2)
        self.spin_bottom.bind("<KeyRelease>", lambda e: self._on_bbox_input_changed())

        # Dimensions & Snap helper
        dim_frame = tk.Frame(bbox_frame, bg=self.bg_panel)
        dim_frame.pack(fill=tk.X, pady=(4, 2))

        self.lbl_bbox_dims = tk.Label(dim_frame, text=f"Width: {self.bbox_right - self.bbox_left} px | Height: {self.bbox_bottom - self.bbox_top} px", bg=self.bg_panel, fg=self.fg_main, font=("Consolas", 9))
        self.lbl_bbox_dims.pack(side=tk.LEFT)

        btn_snap_1px = tk.Button(
            dim_frame, text="Snap 1px Height", bg="#3f3f46", fg="white", font=("Segoe UI", 8),
            relief="flat", padx=6, pady=1, command=self.snap_bbox_1px
        )
        btn_snap_1px.pack(side=tk.RIGHT)

        # Judgement line inside BBox
        jl_frame = tk.Frame(bbox_frame, bg=self.bg_panel)
        jl_frame.pack(fill=tk.X, pady=(4, 0))
        tk.Label(jl_frame, text="JUDGEMENENT_LINE (rel Y):", bg=self.bg_panel, fg=self.fg_dim).pack(side=tk.LEFT)
        self.var_jl = tk.IntVar(value=self.judgement_line)
        self.spin_jl = tk.Spinbox(jl_frame, from_=0, to=999, textvariable=self.var_jl, width=5, command=self._on_jl_input_changed, bg=self.bg_input, fg=self.fg_main, relief="flat")
        self.spin_jl.pack(side=tk.LEFT, padx=6)
        self.spin_jl.bind("<KeyRelease>", lambda e: self._on_jl_input_changed())

        # Offset Y (Move BBox up/down relative to current position)
        offset_frame = tk.Frame(bbox_frame, bg=self.bg_panel)
        offset_frame.pack(fill=tk.X, pady=(4, 2))

        tk.Label(offset_frame, text="Offset Y (±px):", bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 8)).pack(side=tk.LEFT)
        self.var_offset_y = tk.IntVar(value=5)
        self.spin_offset_y = tk.Spinbox(offset_frame, from_=-9999, to=9999, textvariable=self.var_offset_y, width=5, bg=self.bg_input, fg=self.fg_main, relief="flat")
        self.spin_offset_y.pack(side=tk.LEFT, padx=(3, 3))

        btn_up = tk.Button(offset_frame, text="▲ Up", bg="#3f3f46", fg="white", font=("Segoe UI", 8, "bold"), relief="flat", padx=5, pady=1, command=lambda: self.shift_bbox_y(-abs(self.var_offset_y.get() or 1)))
        btn_up.pack(side=tk.LEFT, padx=1)

        btn_down = tk.Button(offset_frame, text="▼ Down", bg="#3f3f46", fg="white", font=("Segoe UI", 8, "bold"), relief="flat", padx=5, pady=1, command=lambda: self.shift_bbox_y(abs(self.var_offset_y.get() or 1)))
        btn_down.pack(side=tk.LEFT, padx=1)

        btn_apply_offset = tk.Button(offset_frame, text="Shift", bg=self.accent, fg="black", font=("Segoe UI", 8, "bold"), relief="flat", padx=5, pady=1, command=self.apply_offset_y)
        btn_apply_offset.pack(side=tk.LEFT, padx=1)

        # 2. Timing & Input Delay Frame
        delay_frame = tk.LabelFrame(sidebar, text="Timing & Delay Settings", bg=self.bg_panel, fg=self.accent, font=("Segoe UI", 9, "bold"), padx=8, pady=6)
        delay_frame.pack(fill=tk.X, pady=(0, 6))

        row_d1 = tk.Frame(delay_frame, bg=self.bg_panel)
        row_d1.pack(fill=tk.X, pady=(0, 2))

        tk.Label(row_d1, text="Input Delay:", bg=self.bg_panel, fg=self.fg_main, font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=(0, 4))

        self.spin_delay_ms = tk.Spinbox(
            row_d1, from_=0, to=5000, textvariable=self.var_delay_ms, width=5,
            bg=self.bg_input, fg=self.accent, font=("Consolas", 9, "bold"), justify="center", relief="flat",
            command=self._on_delay_input_changed
        )
        self.spin_delay_ms.pack(side=tk.LEFT, padx=2)
        self.spin_delay_ms.bind("<KeyRelease>", lambda e: self._on_delay_input_changed())

        tk.Label(row_d1, text="ms", bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(2, 6))

        for d_val in (0, 5, 10, 20, 50):
            btn_d = tk.Button(
                row_d1, text=f"{d_val}", bg="#3f3f46", fg="white", font=("Segoe UI", 7, "bold"),
                relief="flat", padx=3, pady=1, command=lambda dv=d_val: self.set_input_delay(dv)
            )
            btn_d.pack(side=tk.LEFT, padx=1)


        lbl_delay_desc = tk.Label(
            delay_frame, text="Input Delay: Delays key presses & releases by X ms for timing offset.",
            bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 7), justify="left", anchor="w"
        )
        lbl_delay_desc.pack(fill=tk.X, pady=(2, 0))

        # Skill Level row (random input variance from -X to +X ms)
        row_s1 = tk.Frame(delay_frame, bg=self.bg_panel)
        row_s1.pack(fill=tk.X, pady=(4, 2))

        tk.Label(row_s1, text="Skill Level:", bg=self.bg_panel, fg=self.fg_main, font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=(0, 4))

        self.spin_skill_level = tk.Spinbox(
            row_s1, from_=0, to=500, textvariable=self.var_skill_level, width=5,
            bg=self.bg_input, fg="#a78bfa", font=("Consolas", 9, "bold"), justify="center", relief="flat",
            command=self._on_skill_level_changed
        )
        self.spin_skill_level.pack(side=tk.LEFT, padx=2)
        self.spin_skill_level.bind("<KeyRelease>", lambda e: self._on_skill_level_changed())

        tk.Label(row_s1, text="±ms", bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(2, 6))

        for s_val, s_lbl in ((0, "Off (0)"), (5, "Pro (5)"), (12, "Mid (12)"), (20, "Low (20)")):
            btn_s = tk.Button(
                row_s1, text=s_lbl, bg="#3f3f46", fg="white", font=("Segoe UI", 7, "bold"),
                relief="flat", padx=3, pady=1, command=lambda sv=s_val: self.set_skill_level(sv)
            )
            btn_s.pack(side=tk.LEFT, padx=1)


        lbl_skill_desc = tk.Label(
            delay_frame, text="Skill Level: Adds random input variance from -X to +X ms (humanization).",
            bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 7), justify="left", anchor="w"
        )
        lbl_skill_desc.pack(fill=tk.X, pady=(1, 0))

        # 2b. Skill Simulation Frame (Misread, Stamina, Strain)
        sim_frame = tk.LabelFrame(sidebar, text="Skill Simulation (Misread, Stamina, Strain)", bg=self.bg_panel, fg=self.accent, font=("Segoe UI", 9, "bold"), padx=8, pady=6)
        sim_frame.pack(fill=tk.X, pady=(0, 6))

        def _make_spin(parent, var, lo, hi, width, color, increment=1.0):
            kwargs = dict(
                from_=lo, to=hi, increment=increment, textvariable=var, width=width,
                bg=self.bg_input, fg=color, font=("Consolas", 9, "bold"), justify="center", relief="flat",
                command=self._on_extras_changed
            )
            sp = tk.Spinbox(parent, **kwargs)
            sp.bind("<KeyRelease>", lambda e: self._on_extras_changed())
            return sp

        def _lbl(parent, text, bold=False, dim=True, padx=(2, 4)):
            tk.Label(
                parent, text=text, bg=self.bg_panel, fg=self.fg_dim if dim else self.fg_main,
                font=("Segoe UI", 8, "bold") if bold else ("Segoe UI", 8)
            ).pack(side=tk.LEFT, padx=padx)

        row_m = tk.Frame(sim_frame, bg=self.bg_panel)
        row_m.pack(fill=tk.X, pady=(0, 2))
        _lbl(row_m, "Misread:", bold=True, dim=False, padx=(0, 4))
        self.spin_misread_chance = _make_spin(row_m, self.var_misread_chance, 0.0, 100.0, 5, "#fb7185", increment=0.5)
        self.spin_misread_chance.pack(side=tk.LEFT, padx=2)
        _lbl(row_m, "% chance, ignore lane for")
        self.spin_misread_ms = _make_spin(row_m, self.var_misread_ms, 0.0, 5000.0, 5, "#fb7185", increment=10.0)
        self.spin_misread_ms.pack(side=tk.LEFT, padx=2)
        _lbl(row_m, "ms")

        tk.Label(
            sim_frame, text="Misread: X% chance per note that the lane ignores input for Y ms.",
            bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 7), justify="left", anchor="w"
        ).pack(fill=tk.X, pady=(0, 3))

        row_st = tk.Frame(sim_frame, bg=self.bg_panel)
        row_st.pack(fill=tk.X, pady=(0, 2))
        _lbl(row_st, "Stamina:", bold=True, dim=False, padx=(0, 4))
        self.spin_stamina_max = _make_spin(row_st, self.var_stamina_max, 0.0, 9999.0, 5, "#34d399", increment=1.0)
        self.spin_stamina_max.pack(side=tk.LEFT, padx=2)
        _lbl(row_st, "max clicks, +")
        self.spin_stamina_regen = _make_spin(row_st, self.var_stamina_regen, 0.0, 999.0, 5, "#34d399", increment=0.1)
        self.spin_stamina_regen.pack(side=tk.LEFT, padx=2)
        _lbl(row_st, "per 20ms")

        tk.Label(
            sim_frame, text="Stamina: each click costs 1; ignores inputs while empty (0 max = off).",
            bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 7), justify="left", anchor="w"
        ).pack(fill=tk.X, pady=(0, 3))

        # Strain row
        row_str1 = tk.Frame(sim_frame, bg=self.bg_panel)
        row_str1.pack(fill=tk.X, pady=(0, 2))
        _lbl(row_str1, "Strain:", bold=True, dim=False, padx=(0, 4))
        _lbl(row_str1, "Every")
        self.spin_strain_step = _make_spin(row_str1, self.var_strain_step_pct, 0.0, 100.0, 4, "#f59e0b", increment=0.5)
        self.spin_strain_step.pack(side=tk.LEFT, padx=2)
        _lbl(row_str1, "% stamina lost:")

        row_str2 = tk.Frame(sim_frame, bg=self.bg_panel)
        row_str2.pack(fill=tk.X, pady=(0, 2))
        _lbl(row_str2, "+Misread:")
        self.spin_strain_misread = _make_spin(row_str2, self.var_strain_misread_pct, 0.0, 100.0, 4, "#fb7185", increment=0.5)
        self.spin_strain_misread.pack(side=tk.LEFT, padx=1)
        _lbl(row_str2, "%")

        _lbl(row_str2, "+Delay:")
        self.spin_strain_skill = _make_spin(row_str2, self.var_strain_skill_ms, 0.0, 500.0, 4, "#a78bfa", increment=0.5)
        self.spin_strain_skill.pack(side=tk.LEFT, padx=1)
        _lbl(row_str2, "ms")

        _lbl(row_str2, "-Regen:")
        self.spin_strain_regen = _make_spin(row_str2, self.var_strain_regen_pct, 0.0, 100.0, 4, "#ef4444", increment=0.5)
        self.spin_strain_regen.pack(side=tk.LEFT, padx=1)
        _lbl(row_str2, "%")

        tk.Label(
            sim_frame, text="Strain: Every X% stamina lost, adds +y% misread, +z ms jitter, -Z% regen.",
            bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 7), justify="left", anchor="w"
        ).pack(fill=tk.X, pady=(0, 0))

        # 3. Lanes & Keybinds Inspector Frame (Dynamic 1 to 20 Keys)
        lane_frame = tk.LabelFrame(sidebar, text="Lanes & Keybinds", bg=self.bg_panel, fg=self.accent, font=("Segoe UI", 9, "bold"), padx=8, pady=6)
        lane_frame.pack(fill=tk.X, pady=(0, 6))

        # Dynamic Key count selector row
        kc_row = tk.Frame(lane_frame, bg=self.bg_panel)
        kc_row.pack(fill=tk.X, pady=(0, 4))

        tk.Label(kc_row, text="Keys (1-20):", bg=self.bg_panel, fg=self.fg_main, font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=(0, 4))

        self.var_key_count = tk.IntVar(value=self.key_count)
        self.spin_key_count = tk.Spinbox(
            kc_row, from_=1, to=20, textvariable=self.var_key_count, width=3,
            bg=self.bg_input, fg=self.accent, font=("Consolas", 9, "bold"), justify="center", relief="flat",
            command=self._on_key_count_spin_changed
        )
        self.spin_key_count.pack(side=tk.LEFT, padx=2)
        self.spin_key_count.bind("<KeyRelease>", lambda e: self._on_key_count_spin_changed())

        # Quick mode buttons
        for k_val in (4, 7, 8, 10):
            btn_k = tk.Button(
                kc_row, text=f"{k_val}K", bg="#3f3f46", fg="white", font=("Segoe UI", 7, "bold"),
                relief="flat", padx=3, pady=1, command=lambda kv=k_val: self.set_key_count(kv)
            )
            btn_k.pack(side=tk.LEFT, padx=1)

        btn_auto_space = tk.Button(
            kc_row, text="↔ Auto-Space", bg="#0284c7", fg="white", font=("Segoe UI", 7, "bold"),
            relief="flat", padx=4, pady=1, command=self.auto_space_lanes
        )
        btn_auto_space.pack(side=tk.RIGHT, padx=1)

        # Quick Keybind presets row
        self.quick_key_box = tk.Frame(lane_frame, bg=self.bg_panel)
        self.quick_key_box.pack(fill=tk.X, pady=(0, 4))

        # Scrollable container for lane rows (smoothly handles 1 to 20 keys)
        scroll_outer = tk.Frame(lane_frame, bg=self.bg_panel)
        scroll_outer.pack(fill=tk.BOTH, expand=True, pady=2)

        self.lane_canvas = tk.Canvas(scroll_outer, bg=self.bg_panel, height=170, highlightthickness=0)
        self.lane_scrollbar = tk.Scrollbar(scroll_outer, orient=tk.VERTICAL, command=self.lane_canvas.yview)
        self.lane_canvas.configure(yscrollcommand=self.lane_scrollbar.set)

        self.lane_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.lane_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.lane_rows_frame = tk.Frame(self.lane_canvas, bg=self.bg_panel)
        self.lane_canvas_window = self.lane_canvas.create_window((0, 0), window=self.lane_rows_frame, anchor="nw")

        self.lane_rows_frame.bind("<Configure>", lambda e: self.lane_canvas.configure(scrollregion=self.lane_canvas.bbox("all")))
        self.lane_canvas.bind("<Configure>", lambda e: self.lane_canvas.itemconfig(self.lane_canvas_window, width=e.width))

        self.lane_widgets = []
        self.lane_vars_rel = []
        self.lane_vars_abs = []
        self.lane_vars_key = []
        self.lane_pick_buttons = []

        self._build_lane_rows()
        self._update_quick_key_presets_ui()

    def _build_lane_rows(self):
        if not hasattr(self, "lane_rows_frame"):
            return
        for widget in self.lane_rows_frame.winfo_children():
            widget.destroy()

        self.lane_widgets = []
        self.lane_vars_rel = []
        self.lane_vars_abs = []
        self.lane_vars_key = []
        self.lane_pick_buttons = []

        for i in range(self.key_count):
            lf = tk.Frame(self.lane_rows_frame, bg="#1f1f23", padx=5, pady=2, relief="flat")
            lf.pack(fill=tk.X, pady=1)

            color = get_lane_color(i)
            color_tag = tk.Label(lf, text=f" L{i+1} ", bg=color, fg="black", font=("Segoe UI", 7, "bold"), width=4)
            color_tag.pack(side=tk.LEFT, padx=(0, 3))

            # Keybind entry box
            tk.Label(lf, text="Key:", bg="#1f1f23", fg=self.fg_dim, font=("Segoe UI", 7)).pack(side=tk.LEFT, padx=(0, 1))
            v_key = tk.StringVar(value=self.lane_keys[i])
            self.lane_vars_key.append(v_key)
            entry_key = tk.Entry(lf, textvariable=v_key, width=4, bg=self.bg_input, fg=self.accent, font=("Consolas", 8, "bold"), justify="center", relief="flat")
            entry_key.pack(side=tk.LEFT, padx=(0, 3))
            entry_key.bind("<KeyRelease>", lambda e, idx=i: self._on_key_entry_changed(idx))

            # Relative X Entry
            tk.Label(lf, text="Rel:", bg="#1f1f23", fg=self.fg_dim, font=("Segoe UI", 7)).pack(side=tk.LEFT, padx=(1, 1))
            v_rel = tk.IntVar(value=self.lane_rel_x[i])
            self.lane_vars_rel.append(v_rel)
            spin_rel = tk.Spinbox(lf, from_=-9999, to=9999, textvariable=v_rel, width=5, bg=self.bg_input, fg=self.fg_main, relief="flat", command=lambda idx=i: self._on_lane_spin_changed(idx))
            spin_rel.pack(side=tk.LEFT, padx=1)
            spin_rel.bind("<KeyRelease>", lambda e, idx=i: self._on_lane_spin_changed(idx))

            # Screen X label
            v_abs = tk.StringVar(value=f"(X:{self.bbox_left + self.lane_rel_x[i]})")
            self.lane_vars_abs.append(v_abs)
            lbl_abs = tk.Label(lf, textvariable=v_abs, bg="#1f1f23", fg=self.fg_dim, font=("Consolas", 7), width=8)
            lbl_abs.pack(side=tk.LEFT, padx=1)

            # Nudge buttons
            btn_minus = tk.Button(lf, text="◀", bg="#3f3f46", fg="white", relief="flat", padx=2, pady=0, font=("Segoe UI", 7), command=lambda idx=i: self.nudge_lane(idx, -1))
            btn_minus.pack(side=tk.LEFT, padx=1)
            btn_plus = tk.Button(lf, text="▶", bg="#3f3f46", fg="white", relief="flat", padx=2, pady=0, font=("Segoe UI", 7), command=lambda idx=i: self.nudge_lane(idx, 1))
            btn_plus.pack(side=tk.LEFT, padx=1)

            # Select button for click placement
            btn_pick = tk.Button(
                lf, text="Pick", bg="#3f3f46", fg="white", relief="flat", padx=3, pady=0, font=("Segoe UI", 7),
                command=lambda idx=i: self.select_lane_for_click(idx)
            )
            btn_pick.pack(side=tk.RIGHT, padx=1)
            self.lane_pick_buttons.append(btn_pick)

            self.lane_widgets.append(lf)

        self._update_lane_pick_buttons()
        self._update_quick_key_presets_ui()

    def _update_quick_key_presets_ui(self):
        if not hasattr(self, "quick_key_box"):
            return
        for widget in self.quick_key_box.winfo_children():
            widget.destroy()

        tk.Label(self.quick_key_box, text="Key Sets:", bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 4))

        count = self.key_count
        if count == 4:
            presets = [
                ("QW[]", ["q", "w", "[", "]"]),
                ("DFJK", ["d", "f", "j", "k"]),
                ("ASKL", ["a", "s", "k", "l"]),
                ("ZX./", ["z", "x", ".", "/"]),
            ]
        elif count == 5:
            presets = [
                ("DF Sp JK", ["d", "f", "space", "j", "k"]),
                ("AS Sp KL", ["a", "s", "space", "k", "l"]),
            ]
        elif count == 6:
            presets = [
                ("SDF JKL", ["s", "d", "f", "j", "k", "l"]),
                ("ASD JKL", ["a", "s", "d", "j", "k", "l"]),
                ("QWE IOP", ["q", "w", "e", "i", "o", "p"]),
            ]
        elif count == 7:
            presets = [
                ("SDF Sp JKL", ["s", "d", "f", "space", "j", "k", "l"]),
                ("ASD Sp JKL", ["a", "s", "d", "space", "j", "k", "l"]),
            ]
        elif count == 8:
            presets = [
                ("ASDF JKL;", ["a", "s", "d", "f", "j", "k", "l", ";"]),
                ("ASDF HJKL", ["a", "s", "d", "f", "h", "j", "k", "l"]),
            ]
        elif count == 9:
            presets = [
                ("ASDF Sp JKL;", ["a", "s", "d", "f", "space", "j", "k", "l", ";"]),
            ]
        elif count == 10:
            presets = [
                ("ASDFG HJKL;", ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";"]),
                ("QWER V NUIOP", ["q", "w", "e", "r", "v", "n", "u", "i", "o", "p"]),
            ]
        else:
            default_layout = DEFAULT_KEY_LAYOUTS.get(count, ALL_20_KEYS[:count])
            name = f"Default {count}K"
            presets = [(name, default_layout)]

        for name, keys in presets:
            btn_q = tk.Button(
                self.quick_key_box, text=name, bg="#3f3f46", fg="white", font=("Consolas", 7),
                relief="flat", padx=3, pady=1, command=lambda k_list=keys: self.apply_key_preset(k_list)
            )
            btn_q.pack(side=tk.LEFT, padx=1)

    def _on_key_count_spin_changed(self):
        try:
            val = self.var_key_count.get()
            if 1 <= val <= 20 and val != self.key_count:
                self.set_key_count(val)
        except Exception:
            pass

    def set_key_count(self, new_count: int, rel_x_list=None, keys_list=None):
        new_count = max(1, min(20, int(new_count)))
        old_count = self.key_count
        self.key_count = new_count
        if hasattr(self, "var_key_count"):
            self.var_key_count.set(new_count)

        w = max(1, self.bbox_right - self.bbox_left)

        if rel_x_list is not None and len(rel_x_list) >= new_count:
            self.lane_rel_x = [int(x) for x in rel_x_list[:new_count]]
        else:
            if new_count > len(self.lane_rel_x):
                for i in range(len(self.lane_rel_x), new_count):
                    default_rel = int((w / new_count) * (i + 0.5))
                    self.lane_rel_x.append(default_rel)
            elif new_count < len(self.lane_rel_x):
                self.lane_rel_x = self.lane_rel_x[:new_count]

        if keys_list is not None and len(keys_list) >= new_count:
            self.lane_keys = [str(k).lower().strip() for k in keys_list[:new_count]]
        else:
            if new_count in DEFAULT_KEY_LAYOUTS and (old_count != new_count or len(self.lane_keys) != new_count):
                layout = DEFAULT_KEY_LAYOUTS[new_count]
                updated_keys = list(self.lane_keys[:new_count])
                while len(updated_keys) < new_count:
                    idx = len(updated_keys)
                    if idx < len(layout):
                        updated_keys.append(layout[idx])
                    elif idx < len(ALL_20_KEYS):
                        updated_keys.append(ALL_20_KEYS[idx])
                    else:
                        updated_keys.append(f"k{idx+1}")
                self.lane_keys = updated_keys[:new_count]
            else:
                while len(self.lane_keys) < new_count:
                    idx = len(self.lane_keys)
                    if idx < len(ALL_20_KEYS):
                        self.lane_keys.append(ALL_20_KEYS[idx])
                    else:
                        self.lane_keys.append(f"k{idx+1}")
                self.lane_keys = self.lane_keys[:new_count]

        if self.selected_lane_idx >= new_count:
            self.selected_lane_idx = max(0, new_count - 1)

        if hasattr(self, "lane_rows_frame"):
            self._build_lane_rows()
        if hasattr(self, "canvas"):
            self.redraw_canvas()
        if hasattr(self, "strip_preview_frame"):
            self.update_live_preview()
        if hasattr(self, "lbl_status"):
            self.lbl_status.config(text=f"Switched to {new_count}-key mode.")

    def auto_space_lanes(self):
        """Evenly spaces all lanes across the bounding box width."""
        w = max(1, self.bbox_right - self.bbox_left)
        count = self.key_count
        for i in range(count):
            rel_x = int((w / count) * (i + 0.5))
            self.lane_rel_x[i] = rel_x
            if i < len(self.lane_vars_rel):
                self.lane_vars_rel[i].set(rel_x)
                self.lane_vars_abs[i].set(f"(X:{self.bbox_left + rel_x})")
        self.redraw_canvas()
        self.update_live_preview()
        self.lbl_status.config(text=f"Auto-spaced {count} lanes across {w}px width.")

        # 3. Live Strip & Detection Preview
        preview_frame = tk.LabelFrame(sidebar, text="Live Detection Preview (at Judgement Line)", bg=self.bg_panel, fg=self.accent, font=("Segoe UI", 9, "bold"), padx=8, pady=4)
        preview_frame.pack(fill=tk.X, pady=(0, 6))

        self.canvas_strip = tk.Canvas(preview_frame, bg="#09090b", height=36, highlightthickness=1, highlightbackground="#3f3f46")
        self.canvas_strip.pack(fill=tk.X, pady=(0, 2))

        self.lbl_detection_status = tk.Label(
            preview_frame, text="Lane Brightness (sum(RGB)/3 > 30):\nL1: -- | L2: -- | L3: -- | L4: --",
            bg=self.bg_panel, fg=self.fg_dim, font=("Consolas", 8), justify="left"
        )
        self.lbl_detection_status.pack(anchor="w")

        # 4. Pixel Loupe / Magnifier
        loupe_frame = tk.LabelFrame(sidebar, text="Pixel Magnifier (Cursor Inspection)", bg=self.bg_panel, fg=self.accent, font=("Segoe UI", 9, "bold"), padx=8, pady=4)
        loupe_frame.pack(fill=tk.BOTH, expand=True)

        loupe_box = tk.Frame(loupe_frame, bg=self.bg_panel)
        loupe_box.pack(fill=tk.BOTH, expand=True)

        self.canvas_loupe = tk.Canvas(loupe_box, bg="#09090b", width=110, height=110, highlightthickness=1, highlightbackground="#3f3f46")
        self.canvas_loupe.pack(side=tk.LEFT, padx=(0, 8), pady=2)

        self.lbl_loupe_info = tk.Label(
            loupe_box, text="Hover canvas to inspect\npixel colors & crosshair.\n\nKeybinds & BBOX can\nbe saved to presets!",
            bg=self.bg_panel, fg=self.fg_dim, font=("Segoe UI", 8), justify="left"
        )
        self.lbl_loupe_info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _bind_events(self):
        # Canvas mouse events
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Motion>", self._on_mouse_move)

        # Pan support with Middle click
        self.canvas.bind("<ButtonPress-2>", self._on_pan_start)
        self.canvas.bind("<B2-Motion>", self._on_pan_move)

        # Zoom with mouse wheel
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)

        # Hotkeys
        self.root.bind("<Key-b>", lambda e: self.set_mode("box"))
        self.root.bind("<Key-B>", lambda e: self.set_mode("box"))
        self.root.bind("<Key-l>", lambda e: self.set_mode("lane"))
        self.root.bind("<Key-L>", lambda e: self.set_mode("lane"))
        self.root.bind("<Key-c>", lambda e: self.capture_screen_now())
        self.root.bind("<Key-C>", lambda e: self.capture_screen_now())
        self.root.bind("<Key-s>", lambda e: self.save_to_target_file())
        self.root.bind("<Key-S>", lambda e: self.save_to_target_file())

        for k in range(1, 10):
            self.root.bind(f"<Key-{k}>", lambda e, idx=k-1: self.select_lane_for_click(idx) if idx < self.key_count else None)
        self.root.bind("<Key-0>", lambda e: self.select_lane_for_click(9) if self.key_count >= 10 else None)

    def _try_load_initial_image(self):
        script_dir = ROOT_DIR
        candidates = [
            self.screenshot_path,
            script_dir / "Screenshot.png",
            script_dir / "Screenshot.bmp",
            Path.cwd() / "Screenshot.png",
            script_dir.parent / "Screenshot.png",
            script_dir / "Pre Vibecoded" / "Screenshot.png",
            script_dir.parent / "Pre Vibecoded" / "Screenshot.png",
        ]
        for p in candidates:
            if p and p.exists():
                try:
                    img = Image.open(str(p))
                    self.set_image(img, source_name=p.name)
                    self.lbl_status.config(text=f"Loaded reference screenshot: {p.name} ({img.width}x{img.height})")
                    return
                except Exception:
                    pass

        # Draw placeholder instructions banner on canvas
        self.canvas.delete("all")
        self.canvas.create_text(
            400, 250,
            text="🎮 Mania Player Calibration Harness\n\n"
                 "1. Press [📸 Capture Now] or [⏱️ In 2s] to grab your osu!mania screen\n"
                 "   OR click [📂 Load Screenshot] to open an existing screenshot.\n\n"
                 "2. Use [🔲 Box Mode] to drag a rectangle over the judgement line.\n"
                 "3. Select Key Count (1 to 20 keys) & use [🎯 Lane Mode] to click lane targets.\n"
                 "4. Edit Keybinds (custom or quick sets) and save/load Presets.\n"
                 "5. Click [💾 Save to maniaplayer.py] or [⚡ Apply to Player] to update the bot!\n\n"
                 f"Current values loaded:\n"
                 f"  BBOX: ({self.bbox_left}, {self.bbox_top}, {self.bbox_right}, {self.bbox_bottom})\n"
                 f"  LANES ({self.key_count}K): {self.lane_rel_x} | KEYS: {self.lane_keys}",
            fill="#a1a1aa", font=("Segoe UI", 12), justify="center"
        )

    # -------------------------------------------------------------
    # Presets Management
    # -------------------------------------------------------------
    def _get_preset_list(self):
        if not self.presets_dir.exists():
            return []
        items = []
        for p in sorted(self.presets_dir.glob("*.json")):
            items.append(p.stem)
        return items

    def _refresh_presets_list(self, select_name=None):
        vals = self._get_preset_list()
        self.cb_presets["values"] = vals
        if select_name and select_name in vals:
            self.cb_presets.set(select_name)
        elif vals and not self.cb_presets.get():
            self.cb_presets.set(vals[0])

    def load_selected_preset(self, silent: bool = False):
        preset_name = self.cb_presets.get().strip()
        if not preset_name:
            if not silent:
                messagebox.showwarning("No Preset", "Please select a preset from the dropdown.")
            return

        preset_file = self.presets_dir / f"{preset_name}.json"
        if not preset_file.exists():
            preset_file = self.presets_dir / preset_name
        if not preset_file.exists():
            if not silent:
                messagebox.showerror("Not Found", f"Preset file not found: {preset_file.name}")
            return

        try:
            data = json.loads(preset_file.read_text(encoding="utf-8"))
            raw_bbox = data.get("bbox", [])
            if len(raw_bbox) == 4:
                self.bbox_left, self.bbox_top, self.bbox_right, self.bbox_bottom = [int(v) for v in raw_bbox]
            self.judgement_line = int(data.get("judgement_line", 0))

            lanes = data.get("lanes", [])
            if lanes:
                new_count = min(20, max(1, len(lanes)))
                rx_list = []
                k_list = []
                for l_data in lanes[:new_count]:
                    if "rel_x" in l_data:
                        rx_list.append(int(l_data["rel_x"]))
                    elif "x" in l_data:
                        rx_list.append(int(l_data["x"]))
                    else:
                        rx_list.append(0)
                    k_list.append(str(l_data.get("key", "q")).strip().lower())
                self.set_key_count(new_count, rel_x_list=rx_list, keys_list=k_list)

            # Load preset input delay & skill level if specified
            delay_val = int(data.get("input_delay_ms", data.get("delay_ms", 0)))
            self.set_input_delay(delay_val)
            skill_val = int(data.get("skill_level", data.get("skill_level_ms", data.get("input_variance_ms", 0))))
            self.set_skill_level(skill_val)
            self.set_skill_extras(
                data.get("misread_chance", 0), data.get("misread_ms", 0),
                data.get("stamina_max", 0), data.get("stamina_regen", 0.0),
                data.get("strain_step_pct", 0), data.get("strain_misread_pct", 0),
                data.get("strain_skill_ms", 0), data.get("strain_regen_pct", 0)
            )

            self._sync_bbox_to_inputs()
            self.var_jl.set(self.judgement_line)
            self.redraw_canvas()
            self.update_live_preview()
            self.lbl_status.config(text=f"Loaded preset: {preset_name} ({self.key_count} Keys | Delay: {self.input_delay_ms}ms | Skill: ±{self.skill_level}ms)")
            if not silent:
                messagebox.showinfo("Preset Loaded", f"Successfully loaded preset:\n{preset_name} ({self.key_count} Keys)\n\nClick [💾 Save to maniaplayer.py] or [⚡ Apply to Player] to activate it.")
        except Exception as e:
            if not silent:
                messagebox.showerror("Error", f"Failed to load preset:\n{e}")

    def save_new_preset(self):
        try:
            self.root.attributes("-topmost", False)
        except Exception:
            pass

        name = simpledialog.askstring(
            "Save Preset",
            f"Enter a name for this {self.key_count}-key preset (e.g. Skin_{self.key_count}K):",
            parent=self.root
        )

        if hasattr(self, "stay_on_top") and self.stay_on_top.get():
            try:
                self.root.attributes("-topmost", True)
            except Exception:
                pass

        if not name or not name.strip():
            return

        clean_name = name.strip()
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', clean_name)
        if not safe_name.endswith(".json"):
            file_name = f"{safe_name}.json"
            base_name = safe_name
        else:
            file_name = safe_name
            base_name = safe_name[:-5]

        out_path = self.presets_dir / file_name
        data = {
            "preset_name": clean_name,
            "key_count": self.key_count,
            "bbox": [self.bbox_left, self.bbox_top, self.bbox_right, self.bbox_bottom],
            "judgement_line": self.judgement_line,
            "input_delay_ms": self.input_delay_ms,
            "delay_ms": self.input_delay_ms,
            "skill_level": self.skill_level,
            "skill_level_ms": self.skill_level,
            **self._extras_dict(),
            "global_threshold": 30,
            "lanes": [
                {
                    "name": f"Lane {i+1}",
                    "rel_x": self.lane_rel_x[i],
                    "key": self.lane_keys[i],
                    "threshold": 30
                }
                for i in range(self.key_count)
            ]
        }

        try:
            out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            self._refresh_presets_list(select_name=base_name)
            self.lbl_status.config(text=f"Preset saved: {file_name}")
            messagebox.showinfo("Preset Saved", f"Successfully saved {self.key_count}-key preset to:\n{out_path.name}")
        except Exception as e:
            messagebox.showerror("Save Failed", f"Could not save preset:\n{e}")

    def open_presets_folder(self):
        try:
            os.startfile(str(self.presets_dir))
        except Exception as e:
            messagebox.showerror("Error", f"Could not open presets folder:\n{e}")

    def open_backups_folder(self):
        try:
            self.backups_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(self.backups_dir))
        except Exception as e:
            messagebox.showerror("Error", f"Could not open backups folder:\n{e}")

    # -------------------------------------------------------------
    # Keybind Mutation Logic
    # -------------------------------------------------------------
    def _on_key_entry_changed(self, lane_idx: int):
        if lane_idx < len(self.lane_vars_key):
            val = self.lane_vars_key[lane_idx].get().strip().lower()
            if val:
                self.lane_keys[lane_idx] = val
                self.redraw_canvas()
                self.update_live_preview()

    def apply_key_preset(self, keys: list):
        for i in range(min(self.key_count, len(keys))):
            self.lane_keys[i] = str(keys[i]).lower()
            if i < len(self.lane_vars_key):
                self.lane_vars_key[i].set(self.lane_keys[i])
        self.redraw_canvas()
        self.update_live_preview()
        self.lbl_status.config(text=f"Applied keybinds: {self.lane_keys[:self.key_count]}")

    # -------------------------------------------------------------
    # Screen Capture Logic (Disappears window, captures, reappears)
    # -------------------------------------------------------------
    def capture_screen_now(self):
        """Temporarily hides the harness window, captures the screen, and restores the window."""
        self.root.withdraw()
        self.root.update()
        threading.Thread(target=self._capture_worker, args=(0.25,), daemon=True).start()

    def capture_screen_delayed(self, delay_seconds: float):
        """Hides the harness window during countdown, captures the screen, and restores the window."""
        self.root.withdraw()
        self.root.update()

        def run_countdown():
            time.sleep(delay_seconds)
            self._capture_worker(0.0)

        threading.Thread(target=run_countdown, daemon=True).start()

    def _capture_worker(self, prep_delay: float):
        if prep_delay > 0:
            time.sleep(prep_delay)

        captured_img = None
        error_msg = None

        if HAS_PIL:
            try:
                captured_img = ImageGrab.grab(all_screens=True)
            except Exception as e1:
                try:
                    captured_img = ImageGrab.grab()
                except Exception as e2:
                    error_msg = f"PIL grab failed: {e2}"

        if captured_img is None and HAS_MSS:
            try:
                with mss.mss() as sct:
                    mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    shot = sct.grab(mon)
                    captured_img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            except Exception as e:
                error_msg = f"MSS grab failed: {e}"

        def finish():
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            if hasattr(self, "stay_on_top") and self.stay_on_top.get():
                try:
                    self.root.attributes("-topmost", True)
                except Exception:
                    pass

            if captured_img is not None:
                self.set_image(captured_img, source_name="Screen Capture")
                self.lbl_status.config(text=f"Screen captured successfully ({captured_img.width}x{captured_img.height})")
                try:
                    save_path = self.screenshot_path if self.screenshot_path else DEFAULT_SCREENSHOT
                    captured_img.save(str(save_path))
                except Exception:
                    pass
            else:
                messagebox.showerror(
                    "Capture Failed",
                    f"Could not capture screen automatically ({error_msg}).\n\n"
                    "Tip: You can use [📂 Load Screenshot] to open an existing screenshot file!"
                )

        self.root.after(10, finish)

    def browse_and_load_image(self):
        try:
            self.root.attributes("-topmost", False)
        except Exception:
            pass

        file_path = filedialog.askopenfilename(
            title="Open Screenshot",
            initialdir=str(ROOT_DIR),
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")]
        )

        if hasattr(self, "stay_on_top") and self.stay_on_top.get():
            try:
                self.root.attributes("-topmost", True)
            except Exception:
                pass

        if file_path:
            try:
                img = Image.open(file_path)
                self.set_image(img, source_name=Path(file_path).name)
                self.lbl_status.config(text=f"Loaded image: {Path(file_path).name} ({img.width}x{img.height})")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load image:\n{e}")

    def set_image(self, img: Image.Image, source_name: str = ""):
        self.current_image = img.convert("RGB")
        self.zoom_factor = 1.0
        self.lbl_zoom.config(text="100%")
        self.redraw_canvas()
        self.update_live_preview()

    # -------------------------------------------------------------
    # Zoom & Viewport Management
    # -------------------------------------------------------------
    def zoom_in(self):
        if self.current_image is None:
            return
        if self.zoom_factor < 4.0:
            self.zoom_factor = round(self.zoom_factor + 0.25, 2)
            self.lbl_zoom.config(text=f"{int(self.zoom_factor * 100)}%")
            self.redraw_canvas()

    def zoom_out(self):
        if self.current_image is None:
            return
        if self.zoom_factor > 0.25:
            self.zoom_factor = round(self.zoom_factor - 0.25, 2)
            self.lbl_zoom.config(text=f"{int(self.zoom_factor * 100)}%")
            self.redraw_canvas()

    def zoom_fit(self):
        if self.current_image is None:
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw > 50 and ch > 50:
            scale_x = cw / self.current_image.width
            scale_y = ch / self.current_image.height
            self.zoom_factor = round(min(scale_x, scale_y) * 0.95, 2)
            if self.zoom_factor <= 0:
                self.zoom_factor = 1.0
            self.lbl_zoom.config(text=f"{int(self.zoom_factor * 100)}%")
            self.redraw_canvas()

    def _on_mouse_wheel(self, event):
        if self.current_image is None:
            return
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def _on_pan_start(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def _on_pan_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    # -------------------------------------------------------------
    # Canvas Coordinate Conversions
    # -------------------------------------------------------------
    def canvas_to_img_coords(self, cx: float, cy: float):
        canvas_x = self.canvas.canvasx(cx)
        canvas_y = self.canvas.canvasy(cy)
        img_x = int(canvas_x / self.zoom_factor)
        img_y = int(canvas_y / self.zoom_factor)
        return img_x, img_y

    def img_to_canvas_coords(self, ix: float, iy: float):
        return ix * self.zoom_factor, iy * self.zoom_factor

    # -------------------------------------------------------------
    # Redrawing & Rendering
    # -------------------------------------------------------------
    def redraw_canvas(self):
        self.canvas.delete("all")
        if self.current_image is None:
            return

        w = max(1, int(self.current_image.width * self.zoom_factor))
        h = max(1, int(self.current_image.height * self.zoom_factor))

        if self.zoom_factor == 1.0 or (w == self.current_image.width and h == self.current_image.height):
            scaled = self.current_image
        else:
            scaled = self.current_image.resize((w, h), Image.Resampling.NEAREST if self.zoom_factor > 1.0 else Image.Resampling.BILINEAR)

        self.tk_image = ImageTk.PhotoImage(scaled)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image, tags="background_img")
        self.canvas.config(scrollregion=(0, 0, w + 100, h + 100))

        self._render_bbox_overlay()
        self._render_lanes_overlay()

    def _render_bbox_overlay(self):
        x1, y1 = self.img_to_canvas_coords(self.bbox_left, self.bbox_top)
        x2, y2 = self.img_to_canvas_coords(self.bbox_right, self.bbox_bottom)

        height_px = abs(self.bbox_bottom - self.bbox_top)
        vis_y2 = y2
        if height_px <= 1:
            vis_y2 = y1 + max(3, 4 * self.zoom_factor)

        # Outer highlight box
        self.canvas.create_rectangle(
            x1, y1, x2, vis_y2,
            outline="#ef4444", width=2, dash=(4, 2), tags="bbox_shape"
        )
        self.canvas.create_rectangle(
            x1, y1, x2, vis_y2,
            outline="#fca5a5", width=1, tags="bbox_shape"
        )

        # BBox label banner
        self.canvas.create_text(
            x1 + 4, y1 - 10,
            text=f"BBOX [{self.bbox_left}, {self.bbox_top}, {self.bbox_right}, {self.bbox_bottom}] ({self.bbox_right - self.bbox_left}x{height_px}px)",
            anchor="w", fill="#f87171", font=("Consolas", 9, "bold"), tags="bbox_shape"
        )

        if height_px > 1:
            jl_y = self.bbox_top + self.judgement_line
            _, c_jl_y = self.img_to_canvas_coords(0, jl_y)
            self.canvas.create_line(
                x1, c_jl_y, x2, c_jl_y,
                fill="#ec4899", width=2, tags="bbox_shape"
            )
            self.canvas.create_text(
                x2 + 4, c_jl_y,
                text=f"Judgement Y+{self.judgement_line}",
                anchor="w", fill="#ec4899", font=("Consolas", 8), tags="bbox_shape"
            )

        # Resize handles on corners
        handle_sz = 4
        handles = [
            (x1, y1, "nw"), (x2, y1, "ne"),
            (x1, vis_y2, "sw"), (x2, vis_y2, "se")
        ]
        for hx, hy, tag in handles:
            self.canvas.create_rectangle(
                hx - handle_sz, hy - handle_sz, hx + handle_sz, hy + handle_sz,
                fill="#ef4444", outline="white", tags=("bbox_handle", tag)
            )

    def _render_lanes_overlay(self):
        canvas_h = self.canvas.winfo_height()
        if self.current_image:
            _, max_h = self.img_to_canvas_coords(0, self.current_image.height)
            canvas_h = max(canvas_h, max_h)

        bbox_y1_c, _ = self.img_to_canvas_coords(0, self.bbox_top)
        bbox_y2_c, _ = self.img_to_canvas_coords(0, self.bbox_bottom)
        height_px = abs(self.bbox_bottom - self.bbox_top)
        vis_y2 = bbox_y2_c
        if height_px <= 1:
            vis_y2 = bbox_y1_c + max(3, 4 * self.zoom_factor)

        for i in range(self.key_count):
            rel_x = self.lane_rel_x[i]
            abs_x = self.bbox_left + rel_x
            c_x, _ = self.img_to_canvas_coords(abs_x, 0)
            color = get_lane_color(i)
            key_name = self.lane_keys[i].upper()

            self.canvas.create_line(
                c_x, max(0, bbox_y1_c - 60), c_x, min(canvas_h, vis_y2 + 60),
                fill=color, width=2 if self.key_count <= 8 else 1, tags=(f"lane_line_{i}", "lane_marker")
            )

            marker_y = bbox_y1_c + (self.judgement_line * self.zoom_factor)
            r = 5 if self.key_count <= 8 else 3
            self.canvas.create_oval(
                c_x - r, marker_y - r, c_x + r, marker_y + r,
                fill=color, outline="white", width=1, tags=(f"lane_point_{i}", "lane_marker")
            )

            y_offset = -16 if (i % 2 == 0 or self.key_count <= 6) else -28
            label_text = f"L{i+1}:[{key_name}]" if self.key_count > 6 else f"L{i+1}: [{key_name}] (+{rel_x})"
            self.canvas.create_text(
                c_x, max(12, bbox_y1_c + y_offset),
                text=label_text,
                fill=color, font=("Consolas", 8 if self.key_count <= 8 else 7, "bold"), tags=(f"lane_text_{i}", "lane_marker")
            )

    # -------------------------------------------------------------
    # Mouse & Drag Interaction
    # -------------------------------------------------------------
    def _on_mouse_down(self, event):
        img_x, img_y = self.canvas_to_img_coords(event.x, event.y)
        self.drag_start_x = img_x
        self.drag_start_y = img_y

        if self.current_mode == "lane":
            self.set_lane_position_from_screen_x(self.selected_lane_idx, img_x)
            if self.selected_lane_idx < self.key_count - 1:
                self.selected_lane_idx += 1
            else:
                self.set_mode("box")
            self._update_lane_pick_buttons()
            return

        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(cx - 6, cy - 6, cx + 6, cy + 6)

        for item in items:
            tags = self.canvas.gettags(item)
            if "bbox_handle" in tags:
                for t in ("nw", "ne", "sw", "se"):
                    if t in tags:
                        self.is_resizing_box = True
                        self.active_handle = t
                        return

        x1 = min(self.bbox_left, self.bbox_right)
        x2 = max(self.bbox_left, self.bbox_right)
        y1 = min(self.bbox_top, self.bbox_bottom)
        y2 = max(self.bbox_top, self.bbox_bottom)
        if y2 - y1 <= 2:
            y2 = y1 + 10

        if x1 <= img_x <= x2 and y1 - 10 <= img_y <= y2 + 10:
            self.is_moving_box = True
            return

        self.is_dragging_box = True
        self.bbox_left = img_x
        self.bbox_top = img_y
        self.bbox_right = img_x + 1
        self.bbox_bottom = img_y + 1
        self._sync_bbox_to_inputs()
        self.redraw_canvas()

    def _on_mouse_drag(self, event):
        img_x, img_y = self.canvas_to_img_coords(event.x, event.y)

        if self.is_dragging_box:
            self.bbox_right = max(self.bbox_left + 1, img_x)
            self.bbox_bottom = max(self.bbox_top + 1, img_y)
            self._sync_bbox_to_inputs()
            self.redraw_canvas()
            self.update_live_preview()

        elif self.is_resizing_box:
            if self.active_handle == "nw":
                self.bbox_left = min(self.bbox_right - 1, img_x)
                self.bbox_top = min(self.bbox_bottom - 1, img_y)
            elif self.active_handle == "ne":
                self.bbox_right = max(self.bbox_left + 1, img_x)
                self.bbox_top = min(self.bbox_bottom - 1, img_y)
            elif self.active_handle == "sw":
                self.bbox_left = min(self.bbox_right - 1, img_x)
                self.bbox_bottom = max(self.bbox_top + 1, img_y)
            elif self.active_handle == "se":
                self.bbox_right = max(self.bbox_left + 1, img_x)
                self.bbox_bottom = max(self.bbox_top + 1, img_y)

            self._sync_bbox_to_inputs()
            self.redraw_canvas()
            self.update_live_preview()

        elif self.is_moving_box:
            dx = img_x - self.drag_start_x
            dy = img_y - self.drag_start_y
            self.drag_start_x = img_x
            self.drag_start_y = img_y

            self.bbox_left += dx
            self.bbox_right += dx
            self.bbox_top += dy
            self.bbox_bottom += dy

            self._sync_bbox_to_inputs()
            self.redraw_canvas()
            self.update_live_preview()

    def _on_mouse_up(self, event):
        self.is_dragging_box = False
        self.is_resizing_box = False
        self.is_moving_box = False
        self.active_handle = None

        if self.bbox_left > self.bbox_right:
            self.bbox_left, self.bbox_right = self.bbox_right, self.bbox_left
        if self.bbox_top > self.bbox_bottom:
            self.bbox_top, self.bbox_bottom = self.bbox_bottom, self.bbox_top

        self._sync_bbox_to_inputs()
        self.redraw_canvas()
        self.update_live_preview()

    def _on_mouse_move(self, event):
        img_x, img_y = self.canvas_to_img_coords(event.x, event.y)
        rgb_str = "--"
        brightness = 0

        if self.current_image and 0 <= img_x < self.current_image.width and 0 <= img_y < self.current_image.height:
            try:
                rgb = self.current_image.getpixel((img_x, img_y))
                rgb_str = f"({rgb[0]}, {rgb[1]}, {rgb[2]})"
                brightness = int(sum(rgb[:3]) / 3)
            except Exception:
                pass

        self.lbl_cursor_info.config(text=f"X: {img_x} | Y: {img_y} | RGB: {rgb_str} | Lum: {brightness}")
        self.update_loupe(img_x, img_y)

    def update_loupe(self, center_x: int, center_y: int):
        if self.current_image is None:
            return

        box_r = 7
        x1 = max(0, center_x - box_r)
        y1 = max(0, center_y - box_r)
        x2 = min(self.current_image.width, center_x + box_r + 1)
        y2 = min(self.current_image.height, center_y + box_r + 1)

        if x2 <= x1 or y2 <= y1:
            return

        crop = self.current_image.crop((x1, y1, x2, y2))
        loupe_w = self.canvas_loupe.winfo_width()
        loupe_h = self.canvas_loupe.winfo_height()
        if loupe_w < 20 or loupe_h < 20:
            loupe_w, loupe_h = 110, 110

        scaled = crop.resize((loupe_w, loupe_h), Image.Resampling.NEAREST)
        self._loupe_tk = ImageTk.PhotoImage(scaled)

        self.canvas_loupe.delete("all")
        self.canvas_loupe.create_image(0, 0, anchor="nw", image=self._loupe_tk)

        mid_x = loupe_w // 2
        mid_y = loupe_h // 2
        self.canvas_loupe.create_line(mid_x, 0, mid_x, loupe_h, fill="#ef4444", width=1)
        self.canvas_loupe.create_line(0, mid_y, loupe_w, mid_y, fill="#ef4444", width=1)

    def update_live_preview(self):
        if self.current_image is None:
            return

        x1 = min(self.bbox_left, self.bbox_right)
        x2 = max(self.bbox_left, self.bbox_right)
        y1 = min(self.bbox_top, self.bbox_bottom)
        y2 = max(self.bbox_top, self.bbox_bottom)

        w = x2 - x1
        h = max(1, y2 - y1)
        if w <= 0 or h <= 0:
            return

        cx1 = max(0, min(self.current_image.width - 1, x1))
        cy1 = max(0, min(self.current_image.height - 1, y1))
        cx2 = max(0, min(self.current_image.width, x2))
        cy2 = max(0, min(self.current_image.height, y2))

        if cx2 <= cx1 or cy2 <= cy1:
            return

        try:
            strip_img = self.current_image.crop((cx1, cy1, cx2, cy2))
            cw = self.canvas_strip.winfo_width()
            ch = self.canvas_strip.winfo_height()
            if cw < 30 or ch < 10:
                cw, ch = 340, 36

            scaled_strip = strip_img.resize((cw, ch), Image.Resampling.NEAREST)
            self._strip_tk = ImageTk.PhotoImage(scaled_strip)
            self.canvas_strip.create_image(0, 0, anchor="nw", image=self._strip_tk)

            detection_texts = []
            scale_x = cw / w
            px = strip_img.load()
            jl_y = max(0, min(self.judgement_line, strip_img.height - 1))

            for i in range(self.key_count):
                rx = self.lane_rel_x[i]
                c_marker_x = rx * scale_x
                color = get_lane_color(i)
                key_name = self.lane_keys[i].upper()

                self.canvas_strip.create_line(c_marker_x, 0, c_marker_x, ch, fill=color, width=2 if self.key_count <= 8 else 1)
                if self.key_count <= 10 or i % 2 == 0:
                    self.canvas_strip.create_text(c_marker_x + 2, 8, text=f"{key_name}", fill="white", font=("Segoe UI", 7, "bold"))

                if 0 <= rx < strip_img.width:
                    rgb = px[rx, jl_y]
                    b = int(sum(rgb[:3]) / 3)
                    status_flag = f"HIT" if b > 30 else "OFF"
                    detection_texts.append(f"L{i+1}:{b}({status_flag})")
                else:
                    detection_texts.append(f"L{i+1}:OUT")

            chunks = [detection_texts[j:j+4] for j in range(0, len(detection_texts), 4)]
            status_str = "\n".join(" | ".join(c) for c in chunks[:3])
            if len(chunks) > 3:
                status_str += f"\n... (+{len(detection_texts) - 12} more lanes)"
            self.lbl_detection_status.config(text=f"Lane Brightness (sum(RGB)/3 > 30):\n{status_str}")
        except Exception:
            pass

    # -------------------------------------------------------------
    # Calibration Parameter Mutators
    # -------------------------------------------------------------
    def set_mode(self, mode: str):
        self.current_mode = mode
        if mode == "box":
            self.btn_mode_box.config(bg=self.accent, fg="black")
            self.btn_mode_lane.config(bg="#3f3f46", fg="white")
            self.lbl_status.config(text="Mode: Bounding Box. Click & drag on canvas to draw or adjust BBOX.")
        else:
            self.btn_mode_box.config(bg="#3f3f46", fg="white")
            self.btn_mode_lane.config(bg=self.accent, fg="black")
            self.lbl_status.config(text=f"Mode: Lane Targets. Click on canvas to place Lane {self.selected_lane_idx + 1} (key: {self.lane_keys[self.selected_lane_idx].upper()}).")
        self._update_lane_pick_buttons()
        self.redraw_canvas()

    def select_lane_for_click(self, lane_idx: int):
        self.selected_lane_idx = max(0, min(self.key_count - 1, lane_idx))
        self.set_mode("lane")
        self.lbl_status.config(text=f"Click on canvas to set Lane {self.selected_lane_idx + 1} position [key: {self.lane_keys[self.selected_lane_idx].upper()}].")

    def _update_lane_pick_buttons(self):
        for i, btn in enumerate(self.lane_pick_buttons):
            if i < self.key_count:
                if self.current_mode == "lane" and self.selected_lane_idx == i:
                    btn.config(bg=get_lane_color(i), fg="black", text="ACTIVE")
                else:
                    btn.config(bg="#3f3f46", fg="white", text="Pick")

    def set_lane_position_from_screen_x(self, lane_idx: int, screen_x: int):
        rel_x = screen_x - self.bbox_left
        self.lane_rel_x[lane_idx] = rel_x
        if lane_idx < len(self.lane_vars_rel):
            self.lane_vars_rel[lane_idx].set(rel_x)
            self.lane_vars_abs[lane_idx].set(f"(X:{screen_x})")
        self.redraw_canvas()
        self.update_live_preview()

    def nudge_lane(self, lane_idx: int, delta: int):
        self.lane_rel_x[lane_idx] += delta
        if lane_idx < len(self.lane_vars_rel):
            self.lane_vars_rel[lane_idx].set(self.lane_rel_x[lane_idx])
            self.lane_vars_abs[lane_idx].set(f"(X:{self.bbox_left + self.lane_rel_x[lane_idx]})")
        self.redraw_canvas()
        self.update_live_preview()

    def _on_lane_spin_changed(self, lane_idx: int):
        try:
            v = self.lane_vars_rel[lane_idx].get()
            self.lane_rel_x[lane_idx] = v
            self.lane_vars_abs[lane_idx].set(f"(X:{self.bbox_left + v})")
            self.redraw_canvas()
            self.update_live_preview()
        except Exception:
            pass

    def snap_bbox_1px(self):
        self.bbox_bottom = self.bbox_top + 1
        self.judgement_line = 0
        self.var_jl.set(0)
        self._sync_bbox_to_inputs()
        self.redraw_canvas()
        self.update_live_preview()
        self.lbl_status.config(text="BBOX height snapped to 1 pixel.")

    def apply_offset_y(self):
        try:
            delta = self.var_offset_y.get()
            self.shift_bbox_y(delta)
        except Exception:
            pass

    def shift_bbox_y(self, delta: int):
        if delta == 0:
            return
        h = max(1, self.bbox_bottom - self.bbox_top)
        new_top = max(0, self.bbox_top + delta)
        new_bottom = new_top + h
        self.bbox_top = new_top
        self.bbox_bottom = new_bottom
        self._sync_bbox_to_inputs()
        self.redraw_canvas()
        self.update_live_preview()
        self.lbl_status.config(text=f"BBOX shifted by {delta:+d}px Y -> Top: {self.bbox_top}, Bottom: {self.bbox_bottom}")

    def _on_bbox_input_changed(self):
        try:
            self.bbox_left = self.var_left.get()
            self.bbox_top = self.var_top.get()
            self.bbox_right = self.var_right.get()
            self.bbox_bottom = self.var_bottom.get()
            w = max(1, self.bbox_right - self.bbox_left)
            h = max(1, self.bbox_bottom - self.bbox_top)
            self.lbl_bbox_dims.config(text=f"Width: {w} px | Height: {h} px")
            for i in range(min(self.key_count, len(self.lane_vars_abs))):
                self.lane_vars_abs[i].set(f"(X:{self.bbox_left + self.lane_rel_x[i]})")
            self.redraw_canvas()
            self.update_live_preview()
        except Exception:
            pass

    def _on_jl_input_changed(self):
        try:
            self.judgement_line = self.var_jl.get()
            self.redraw_canvas()
            self.update_live_preview()
        except Exception:
            pass

    def _sync_bbox_to_inputs(self):
        self.var_left.set(self.bbox_left)
        self.var_top.set(self.bbox_top)
        self.var_right.set(self.bbox_right)
        self.var_bottom.set(self.bbox_bottom)
        if hasattr(self, "var_delay_ms"):
            self.var_delay_ms.set(self.input_delay_ms)
        if hasattr(self, "var_skill_level"):
            self.var_skill_level.set(self.skill_level)
        self._sync_extras_to_vars()
        w = max(1, self.bbox_right - self.bbox_left)
        h = max(1, self.bbox_bottom - self.bbox_top)
        self.lbl_bbox_dims.config(text=f"Width: {w} px | Height: {h} px")
        for i in range(min(self.key_count, len(self.lane_vars_abs))):
            self.lane_vars_abs[i].set(f"(X:{self.bbox_left + self.lane_rel_x[i]})")

    def _on_delay_input_changed(self):
        try:
            val = max(0, int(self.var_delay_ms.get()))
            self.input_delay_ms = val
            if hasattr(self, "lbl_status"):
                self.lbl_status.config(text=f"Input delay set to {self.input_delay_ms} ms")
        except Exception:
            pass

    def set_input_delay(self, ms: int):
        ms = max(0, int(ms))
        self.input_delay_ms = ms
        if hasattr(self, "var_delay_ms"):
            self.var_delay_ms.set(ms)
        if hasattr(self, "lbl_status"):
            self.lbl_status.config(text=f"Input delay set to {ms} ms")

    def _on_skill_level_changed(self):
        try:
            val = max(0, int(self.var_skill_level.get()))
            self.skill_level = val
            if hasattr(self, "lbl_status"):
                self.lbl_status.config(text=f"Skill Level set to ±{self.skill_level} ms variance")
        except Exception:
            pass

    def set_skill_level(self, ms: int):
        ms = max(0, int(ms))
        self.skill_level = ms
        if hasattr(self, "var_skill_level"):
            self.var_skill_level.set(ms)
        if hasattr(self, "lbl_status"):
            self.lbl_status.config(text=f"Skill Level set to ±{ms} ms variance")

    # -------------------------------------------------------------
    # Skill Simulation: Misread, Stamina & Strain (with Float/Decimal Support)
    # -------------------------------------------------------------
    @staticmethod
    def _format_num(val, precision=2) -> str:
        """Formats numbers so integers show cleanly as '10' and decimals show as '2.5' or '12.25'."""
        try:
            f = float(val)
            if f.is_integer():
                return str(int(f))
            formatted = f"{f:.{precision}f}".rstrip("0").rstrip(".")
            return formatted if formatted else "0"
        except (ValueError, TypeError):
            return "0"

    @staticmethod
    def _parse_float_field(var, lo=0.0, hi=None, default=None):
        try:
            val_str = str(var.get()).strip()
            if not val_str or val_str == ".":
                return default
            val = float(val_str)
            if lo is not None and val < lo:
                val = lo
            if hi is not None and val > hi:
                val = hi
            return val
        except (ValueError, TypeError, tk.TclError):
            return default

    def _extras_dict(self) -> dict:
        def _clean(val):
            try:
                f = float(val)
                return int(f) if f.is_integer() else round(f, 4)
            except Exception:
                return 0

        return {
            "misread_chance": _clean(self.misread_chance),
            "misread_ms": _clean(self.misread_ms),
            "stamina_max": _clean(self.stamina_max),
            "stamina_regen": _clean(self.stamina_regen),
            "strain_step_pct": _clean(self.strain_step_pct),
            "strain_misread_pct": _clean(self.strain_misread_pct),
            "strain_skill_ms": _clean(self.strain_skill_ms),
            "strain_regen_pct": _clean(self.strain_regen_pct),
        }

    def _sync_extras_to_vars(self):
        if not hasattr(self, "var_misread_chance"):
            return
        self.var_misread_chance.set(self._format_num(self.misread_chance))
        self.var_misread_ms.set(self._format_num(self.misread_ms))
        self.var_stamina_max.set(self._format_num(self.stamina_max))
        self.var_stamina_regen.set(self._format_num(self.stamina_regen, precision=3))
        if hasattr(self, "var_strain_step_pct"):
            self.var_strain_step_pct.set(self._format_num(self.strain_step_pct))
            self.var_strain_misread_pct.set(self._format_num(self.strain_misread_pct))
            self.var_strain_skill_ms.set(self._format_num(self.strain_skill_ms))
            self.var_strain_regen_pct.set(self._format_num(self.strain_regen_pct))

    def set_skill_extras(self, misread_chance=None, misread_ms=None, stamina_max=None, stamina_regen=None,
                         strain_step_pct=None, strain_misread_pct=None, strain_skill_ms=None, strain_regen_pct=None):
        try:
            if misread_chance is not None:
                self.misread_chance = min(100.0, max(0.0, float(misread_chance)))
            if misread_ms is not None:
                self.misread_ms = max(0.0, float(misread_ms))
            if stamina_max is not None:
                self.stamina_max = max(0.0, float(stamina_max))
            if stamina_regen is not None:
                self.stamina_regen = max(0.0, float(stamina_regen))
            if strain_step_pct is not None:
                self.strain_step_pct = min(100.0, max(0.0, float(strain_step_pct)))
            if strain_misread_pct is not None:
                self.strain_misread_pct = min(100.0, max(0.0, float(strain_misread_pct)))
            if strain_skill_ms is not None:
                self.strain_skill_ms = max(0.0, float(strain_skill_ms))
            if strain_regen_pct is not None:
                self.strain_regen_pct = min(100.0, max(0.0, float(strain_regen_pct)))
        except (TypeError, ValueError):
            return
        self._sync_extras_to_vars()

    def _on_extras_changed(self):
        """Reads the Misread/Stamina/Strain spinboxes, ignoring half-typed values."""
        v = self._parse_float_field(self.var_misread_chance, lo=0.0, hi=100.0)
        if v is not None:
            self.misread_chance = v
        v = self._parse_float_field(self.var_misread_ms, lo=0.0, hi=60000.0)
        if v is not None:
            self.misread_ms = v
        v = self._parse_float_field(self.var_stamina_max, lo=0.0, hi=99999.0)
        if v is not None:
            self.stamina_max = v
        v = self._parse_float_field(self.var_stamina_regen, lo=0.0, hi=99999.0)
        if v is not None:
            self.stamina_regen = v
        v = self._parse_float_field(self.var_strain_step_pct, lo=0.0, hi=100.0)
        if v is not None:
            self.strain_step_pct = v
        v = self._parse_float_field(self.var_strain_misread_pct, lo=0.0, hi=100.0)
        if v is not None:
            self.strain_misread_pct = v
        v = self._parse_float_field(self.var_strain_skill_ms, lo=0.0, hi=5000.0)
        if v is not None:
            self.strain_skill_ms = v
        v = self._parse_float_field(self.var_strain_regen_pct, lo=0.0, hi=100.0)
        if v is not None:
            self.strain_regen_pct = v

        if hasattr(self, "lbl_status"):
            mis = f"Misread {self._format_num(self.misread_chance)}% / {self._format_num(self.misread_ms)}ms" if self.misread_chance > 0 else "Misread off"
            sta = f"Stamina {self._format_num(self.stamina_max)} (+{self._format_num(self.stamina_regen, 3)}/20ms)" if self.stamina_max > 0 else "Stamina off"
            strn = f"Strain {self._format_num(self.strain_step_pct)}% (+{self._format_num(self.strain_misread_pct)}%, +{self._format_num(self.strain_skill_ms)}ms, -{self._format_num(self.strain_regen_pct)}%)" if self.strain_step_pct > 0 else "Strain off"
            self.lbl_status.config(text=f"{mis} | {sta} | {strn}")

    # -------------------------------------------------------------
    # Live Updates to Mania Player
    # -------------------------------------------------------------
    def apply_live_to_player(self):
        """Immediately applies the current calibration parameters to the running Mania Player and memory."""
        bbox = (self.bbox_left, self.bbox_top, self.bbox_right, self.bbox_bottom)
        jl = self.judgement_line
        lanes = list(self.lane_rel_x[:self.key_count])
        keys = list(self.lane_keys[:self.key_count])

        # 1. Update in sys.modules if loaded
        for mod_name in ("raw_maniaplayer", "maniaplayer"):
            if mod_name in sys.modules:
                mod = sys.modules[mod_name]
                try:
                    mod.BBOX = bbox
                    mod.JUDGEMENENT_LINE = jl
                    mod.LANES = lanes
                    mod.KEYS = keys
                    mod.INPUT_DELAY_MS = self.input_delay_ms
                    mod.DELAY_MS = self.input_delay_ms
                    mod.SKILL_LEVEL = self.skill_level
                    mod.SKILL_LEVEL_MS = self.skill_level
                    mod.MISREAD_CHANCE = self.misread_chance
                    mod.MISREAD_MS = self.misread_ms
                    mod.STAMINA_MAX = self.stamina_max
                    mod.STAMINA_REGEN = self.stamina_regen
                    mod.STRAIN_STEP_PCT = self.strain_step_pct
                    mod.STRAIN_MISREAD_PCT = self.strain_misread_pct
                    mod.STRAIN_SKILL_MS = self.strain_skill_ms
                    mod.STRAIN_REGEN_PCT = self.strain_regen_pct
                    for i in range(min(4, len(lanes))):
                        setattr(mod, f"LANE{i+1}", lanes[i])
                        setattr(mod, f"KEY{i+1}", keys[i])
                except Exception:
                    pass

        # 2. Invoke callback to GUI
        if self.on_save_callback:
            try:
                self.on_save_callback(bbox=bbox, judgement_line=jl, lanes=lanes, keys=keys, delay_ms=self.input_delay_ms, skill_level=self.skill_level, skill_extras=self._extras_dict())
            except Exception as e:
                print(f"[Callback Warning] {e}")

        keys_str = "/".join(keys).upper()
        self.lbl_status.config(text=f"⚡ Live update applied! {self.key_count} Keys: {keys_str} | Delay: {self.input_delay_ms}ms | Skill: ±{self.skill_level}ms")

    # -------------------------------------------------------------
    # Target File Read & Save Logic
    # -------------------------------------------------------------
    def load_from_target_file(self, silent: bool = False):
        loaded = False
        loaded_count = 0
        loaded_lanes = []
        loaded_keys = []

        if self.target_file.exists():
            try:
                content = self.target_file.read_text(encoding="utf-8")

                # Parse BBOX
                m_bbox = re.search(r"^BBOX\s*=\s*\(([\d\s,]+)\)", content, re.MULTILINE)
                if m_bbox:
                    coords = [int(x.strip()) for x in m_bbox.group(1).split(",") if x.strip()]
                    if len(coords) == 4:
                        self.bbox_left, self.bbox_top, self.bbox_right, self.bbox_bottom = coords
                        loaded = True

                # Parse JUDGEMENENT_LINE
                m_jl = re.search(r"^JUDGEMENENT_LINE\s*=\s*(\d+)", content, re.MULTILINE)
                if m_jl:
                    self.judgement_line = int(m_jl.group(1))

                # Parse INPUT_DELAY_MS or INPUT_DELAY or DELAY_MS
                m_del = re.search(r"^(?:INPUT_DELAY_MS|INPUT_DELAY|DELAY_MS)\s*=\s*(\d+)", content, re.MULTILINE)
                if m_del:
                    self.set_input_delay(int(m_del.group(1)))

                # Parse SKILL_LEVEL or SKILL_LEVEL_MS or INPUT_VARIANCE_MS
                m_skill = re.search(r"^(?:SKILL_LEVEL|SKILL_LEVEL_MS|INPUT_VARIANCE_MS)\s*=\s*(\d+)", content, re.MULTILINE)
                if m_skill:
                    self.set_skill_level(int(m_skill.group(1)))

                # Parse Misread & Stamina & Strain constants
                m_mc = re.search(r"^MISREAD_CHANCE\s*=\s*(\d+(?:\.\d+)?)", content, re.MULTILINE)
                m_mm = re.search(r"^MISREAD_MS\s*=\s*(\d+(?:\.\d+)?)", content, re.MULTILINE)
                m_sm = re.search(r"^STAMINA_MAX\s*=\s*(\d+(?:\.\d+)?)", content, re.MULTILINE)
                m_sr = re.search(r"^STAMINA_REGEN\s*=\s*(\d+(?:\.\d+)?)", content, re.MULTILINE)
                m_ss = re.search(r"^STRAIN_STEP_PCT\s*=\s*(\d+(?:\.\d+)?)", content, re.MULTILINE)
                m_smis = re.search(r"^STRAIN_MISREAD_PCT\s*=\s*(\d+(?:\.\d+)?)", content, re.MULTILINE)
                m_sskill = re.search(r"^STRAIN_SKILL_MS\s*=\s*(\d+(?:\.\d+)?)", content, re.MULTILINE)
                m_sreg = re.search(r"^STRAIN_REGEN_PCT\s*=\s*(\d+(?:\.\d+)?)", content, re.MULTILINE)
                if m_mc or m_mm or m_sm or m_sr or m_ss or m_smis or m_sskill or m_sreg:
                    self.set_skill_extras(
                        misread_chance=m_mc.group(1) if m_mc else self.misread_chance,
                        misread_ms=m_mm.group(1) if m_mm else self.misread_ms,
                        stamina_max=m_sm.group(1) if m_sm else self.stamina_max,
                        stamina_regen=m_sr.group(1) if m_sr else self.stamina_regen,
                        strain_step_pct=m_ss.group(1) if m_ss else self.strain_step_pct,
                        strain_misread_pct=m_smis.group(1) if m_smis else self.strain_misread_pct,
                        strain_skill_ms=m_sskill.group(1) if m_sskill else self.strain_skill_ms,
                        strain_regen_pct=m_sreg.group(1) if m_sreg else self.strain_regen_pct,
                    )

                # Parse dynamic LANES = [...]
                m_lanes = re.search(r"^LANES\s*=\s*\[([\d\s,]+)\]", content, re.MULTILINE)
                if m_lanes:
                    l_vals = [int(x.strip()) for x in m_lanes.group(1).split(",") if x.strip()]
                    if l_vals:
                        loaded_lanes = l_vals
                        loaded_count = len(l_vals)

                # Parse dynamic KEYS = [...] (robust to closing bracket key ']')
                m_keys = re.search(r"^KEYS\s*=\s*([^\r\n#]+)", content, re.MULTILINE)
                if m_keys:
                    raw_keys = m_keys.group(1).strip()
                    try:
                        parsed = ast.literal_eval(raw_keys)
                        if isinstance(parsed, (list, tuple)):
                            k_vals = [str(k).strip().lower() for k in parsed if str(k).strip()]
                            if k_vals:
                                loaded_keys = k_vals
                    except Exception:
                        try:
                            parsed = json.loads(raw_keys)
                            if isinstance(parsed, list):
                                k_vals = [str(k).strip().lower() for k in parsed if str(k).strip()]
                                if k_vals:
                                    loaded_keys = k_vals
                        except Exception:
                            tokens = re.findall(r"""['"]([^'"]+)['"]|([^,\[\]\s]+)""", raw_keys)
                            k_vals = [re.sub(r"""['"\s]""", "", (t[0] or t[1])).lower() for t in tokens if (t[0] or t[1]).strip()]
                            if k_vals:
                                loaded_keys = k_vals

                # If dynamic arrays weren't found, check LANE1..LANE20
                if not loaded_lanes:
                    for i in range(1, 21):
                        m_l = re.search(rf"^LANE{i}\s*=\s*(\d+)", content, re.MULTILINE)
                        m_k = re.search(rf"^KEY{i}\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE)
                        if m_l:
                            loaded_lanes.append(int(m_l.group(1)))
                            loaded_keys.append(m_k.group(1).strip().lower() if m_k else f"k{i}")
                        else:
                            break
                    if loaded_lanes:
                        loaded_count = len(loaded_lanes)

            except Exception as e:
                if not silent:
                    messagebox.showerror("Read Error", f"Failed to parse target file:\n{e}")

        # Fallback to reading config_file (mania_config.json)
        if self.config_file and self.config_file.exists():
            try:
                cfg = json.loads(self.config_file.read_text(encoding="utf-8"))
                if not loaded:
                    raw_bbox = cfg.get("bbox", [])
                    if len(raw_bbox) == 4:
                        self.bbox_left, self.bbox_top, self.bbox_right, self.bbox_bottom = raw_bbox
                        loaded = True
                    self.judgement_line = int(cfg.get("judgement_line", 0))

                lanes = cfg.get("lanes", [])
                if lanes:
                    cfg_count = min(20, max(1, len(lanes)))
                    cfg_rel = [int(l.get("x", l.get("rel_x", 0))) for l in lanes[:cfg_count]]
                    cfg_k = [str(l.get("key", "q")).strip().lower() for l in lanes[:cfg_count]]
                    if not loaded_lanes or cfg_count > loaded_count:
                        loaded_lanes = cfg_rel
                        loaded_keys = cfg_k
                        loaded_count = cfg_count

                if "input_delay_ms" in cfg or "delay_ms" in cfg:
                    cfg_delay = int(cfg.get("input_delay_ms", cfg.get("delay_ms", 0)))
                    self.set_input_delay(cfg_delay)

                if "skill_level" in cfg or "skill_level_ms" in cfg or "input_variance_ms" in cfg:
                    cfg_skill = int(cfg.get("skill_level", cfg.get("skill_level_ms", cfg.get("input_variance_ms", 0))))
                    self.set_skill_level(cfg_skill)

                if any(k in cfg for k in ("misread_chance", "misread_ms", "stamina_max", "stamina_regen", "strain_step_pct", "strain_misread_pct", "strain_skill_ms", "strain_regen_pct")):
                    self.set_skill_extras(
                        misread_chance=cfg.get("misread_chance", self.misread_chance),
                        misread_ms=cfg.get("misread_ms", self.misread_ms),
                        stamina_max=cfg.get("stamina_max", self.stamina_max),
                        stamina_regen=cfg.get("stamina_regen", self.stamina_regen),
                        strain_step_pct=cfg.get("strain_step_pct", self.strain_step_pct),
                        strain_misread_pct=cfg.get("strain_misread_pct", self.strain_misread_pct),
                        strain_skill_ms=cfg.get("strain_skill_ms", self.strain_skill_ms),
                        strain_regen_pct=cfg.get("strain_regen_pct", self.strain_regen_pct),
                    )
            except Exception:
                pass

        if loaded_count > 0:
            self.set_key_count(loaded_count, rel_x_list=loaded_lanes, keys_list=loaded_keys)
        else:
            self.set_key_count(4, rel_x_list=[39, 215, 353, 502], keys_list=["q", "w", "[", "]"])

        if hasattr(self, "var_left"):
            self._sync_bbox_to_inputs()
            self.var_jl.set(self.judgement_line)
            self.redraw_canvas()
            self.update_live_preview()

        if not silent:
            messagebox.showinfo(
                "Loaded Successfully",
                f"Loaded from {self.target_file.name}:\n"
                f"BBOX: ({self.bbox_left}, {self.bbox_top}, {self.bbox_right}, {self.bbox_bottom})\n"
                f"Judgement Line: {self.judgement_line}\n"
                f"Keys ({self.key_count}): {self.lane_keys[:self.key_count]}\n"
                f"Lanes: {self.lane_rel_x[:self.key_count]}"
            )

    def save_to_target_file(self):
        """Creates a timestamped backup and updates BBOX, JUDGEMENENT_LINE, LANES, and KEYS in target file and configs."""
        if not self.target_file.exists():
            messagebox.showerror("Error", f"Target file does not exist:\n{self.target_file}")
            return

        confirm = messagebox.askyesno(
            "Confirm Save",
            f"Update {self.target_file.name} with:\n\n"
            f"BBOX = ({self.bbox_left}, {self.bbox_top}, {self.bbox_right}, {self.bbox_bottom})\n"
            f"JUDGEMENENT_LINE = {self.judgement_line}\n"
            f"INPUT_DELAY_MS = {self.input_delay_ms} ms\n"
            f"SKILL_LEVEL = {self.skill_level} ms (±{self.skill_level} ms variance)\n"
            f"MISREAD = {self._format_num(self.misread_chance)}% chance, ignore lane {self._format_num(self.misread_ms)} ms\n"
            f"STAMINA = {self._format_num(self.stamina_max)} max clicks, +{self._format_num(self.stamina_regen, precision=3)} per 20 ms\n"
            f"STRAIN = Every {self._format_num(self.strain_step_pct)}% lost: +{self._format_num(self.strain_misread_pct)}% misread, +{self._format_num(self.strain_skill_ms)}ms jitter, -{self._format_num(self.strain_regen_pct)}% regen\n"
            f"LANES ({self.key_count}K) = {self.lane_rel_x[:self.key_count]}\n"
            f"KEYS = {self.lane_keys[:self.key_count]}\n\n"
            f"A backup will be created in '{self.backups_dir.name}/'. Proceed?"
        )
        if not confirm:
            return

        try:
            # 1. Create backup in dedicated backups folder
            self.backups_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{self.target_file.name}.bak_{timestamp}"
            backup_path = self.backups_dir / backup_name
            shutil.copy2(self.target_file, backup_path)

            # 2. Update lines cleanly in content
            content = self.target_file.read_text(encoding="utf-8")

            if re.search(r"^JUDGEMENENT_LINE\s*=", content, re.MULTILINE):
                content = re.sub(
                    r"^(JUDGEMENENT_LINE\s*=\s*).*$",
                    rf"\g<1>{self.judgement_line}",
                    content, flags=re.MULTILINE
                )
            else:
                content = f"JUDGEMENENT_LINE = {self.judgement_line}\n" + content

            if re.search(r"^INPUT_DELAY_MS\s*=", content, re.MULTILINE):
                content = re.sub(
                    r"^(INPUT_DELAY_MS\s*=\s*).*$",
                    rf"\g<1>{self.input_delay_ms}",
                    content, flags=re.MULTILINE
                )
            else:
                content = f"INPUT_DELAY_MS = {self.input_delay_ms}\n" + content

            if re.search(r"^DELAY_MS\s*=", content, re.MULTILINE):
                content = re.sub(
                    r"^(DELAY_MS\s*=\s*).*$",
                    rf"\g<1>{self.input_delay_ms}",
                    content, flags=re.MULTILINE
                )

            if re.search(r"^SKILL_LEVEL\s*=", content, re.MULTILINE):
                content = re.sub(
                    r"^(SKILL_LEVEL\s*=\s*).*$",
                    rf"\g<1>{self.skill_level}",
                    content, flags=re.MULTILINE
                )
            else:
                content = f"SKILL_LEVEL = {self.skill_level}\n" + content

            for const_name, const_val in (
                ("MISREAD_CHANCE", self._format_num(self.misread_chance)),
                ("MISREAD_MS", self._format_num(self.misread_ms)),
                ("STAMINA_MAX", self._format_num(self.stamina_max)),
                ("STAMINA_REGEN", self._format_num(self.stamina_regen, precision=3)),
                ("STRAIN_STEP_PCT", self._format_num(self.strain_step_pct)),
                ("STRAIN_MISREAD_PCT", self._format_num(self.strain_misread_pct)),
                ("STRAIN_SKILL_MS", self._format_num(self.strain_skill_ms)),
                ("STRAIN_REGEN_PCT", self._format_num(self.strain_regen_pct)),
            ):
                if re.search(rf"^{const_name}\s*=", content, re.MULTILINE):
                    content = re.sub(
                        rf"^({const_name}\s*=\s*).*$",
                        rf"\g<1>{const_val}",
                        content, flags=re.MULTILINE
                    )
                else:
                    content = f"{const_name} = {const_val}\n" + content

            # Update or insert dynamic LANES and KEYS lists
            lanes_repr = str(self.lane_rel_x[:self.key_count])
            keys_repr = json.dumps(self.lane_keys[:self.key_count])

            if re.search(r"^LANES\s*=", content, re.MULTILINE):
                content = re.sub(r"^(LANES\s*=\s*).*$", rf"\g<1>{lanes_repr}", content, flags=re.MULTILINE)
            else:
                content = f"LANES = {lanes_repr}\n" + content

            if re.search(r"^KEYS\s*=", content, re.MULTILINE):
                content = re.sub(r"^(KEYS\s*=\s*).*$", rf"\g<1>{keys_repr}", content, flags=re.MULTILINE)
            else:
                content = f"KEYS = {keys_repr}\n" + content

            # Also maintain LANE1..LANE4 & KEY1..KEY4 for backward compatibility
            for i in range(min(4, self.key_count)):
                if re.search(rf"^LANE{i+1}\s*=", content, re.MULTILINE):
                    content = re.sub(
                        rf"^(LANE{i+1}\s*=\s*).*$",
                        rf"\g<1>{self.lane_rel_x[i]}",
                        content, flags=re.MULTILINE
                    )
                else:
                    content = f"LANE{i+1} = {self.lane_rel_x[i]}\n" + content

                if re.search(rf"^KEY{i+1}\s*=", content, re.MULTILINE):
                    content = re.sub(
                        rf"^(KEY{i+1}\s*=\s*).*$",
                        rf'\g<1>"{self.lane_keys[i]}"',
                        content, flags=re.MULTILINE
                    )
                else:
                    content = f'KEY{i+1} = "{self.lane_keys[i]}"\n' + content

            if re.search(r"^BBOX\s*=", content, re.MULTILINE):
                content = re.sub(
                    r"^(BBOX\s*=\s*).*$",
                    rf"\g<1>({self.bbox_left}, {self.bbox_top}, {self.bbox_right}, {self.bbox_bottom})",
                    content, flags=re.MULTILINE
                )
            else:
                content = f"BBOX = ({self.bbox_left}, {self.bbox_top}, {self.bbox_right}, {self.bbox_bottom})\n" + content

            # Also update DEFAULT_CONFIG bbox inside target python file if present
            content = re.sub(
                r'("bbox":\s*\[)\s*\d+,\s*\d+,\s*\d+,\s*\d+(\s*\])',
                rf'\g<1>{self.bbox_left}, {self.bbox_top}, {self.bbox_right}, {self.bbox_bottom}\2',
                content
            )

            self.target_file.write_text(content, encoding="utf-8")

            # 3. Also update mania_config.json if it exists
            if self.config_file.exists():
                try:
                    cfg = json.loads(self.config_file.read_text(encoding="utf-8"))
                    cfg["bbox"] = [self.bbox_left, self.bbox_top, self.bbox_right, self.bbox_bottom]
                    cfg["judgement_line"] = self.judgement_line
                    cfg["input_delay_ms"] = self.input_delay_ms
                    cfg["delay_ms"] = self.input_delay_ms
                    cfg["skill_level"] = self.skill_level
                    cfg["skill_level_ms"] = self.skill_level
                    cfg.update(self._extras_dict())
                    cfg["key_count"] = self.key_count
                    cfg["lanes"] = [
                        {
                            "name": f"Lane {i+1}",
                            "x": self.lane_rel_x[i],
                            "key": self.lane_keys[i],
                            "threshold": 30
                        }
                        for i in range(self.key_count)
                    ]
                    self.config_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
                except Exception:
                    pass

            # 4. Also update settings.json if it exists in the same folder
            settings_path = self.target_file.parent / "settings.json"
            if settings_path.exists():
                try:
                    s_data = json.loads(settings_path.read_text(encoding="utf-8"))
                    s_data["bbox"] = [self.bbox_left, self.bbox_top, self.bbox_right, self.bbox_bottom]
                    s_data["judgement_line"] = self.judgement_line
                    s_data["input_delay_ms"] = self.input_delay_ms
                    s_data["delay_ms"] = self.input_delay_ms
                    s_data["skill_level"] = self.skill_level
                    s_data["skill_level_ms"] = self.skill_level
                    s_data.update(self._extras_dict())
                    s_data["lanes"] = [
                        {
                            "name": f"Lane {i+1}",
                            "x": self.lane_rel_x[i],
                            "key": self.lane_keys[i],
                            "threshold": 30
                        }
                        for i in range(self.key_count)
                    ]
                    settings_path.write_text(json.dumps(s_data, indent=2), encoding="utf-8")
                except Exception:
                    pass

            # 5. Apply live updates to running Mania Player
            self.apply_live_to_player()

            messagebox.showinfo(
                "Saved Successfully",
                f"Successfully updated {self.target_file.name} and Mania Player ({self.key_count} Keys)!\n\n"
                f"Backup saved to:\n{self.backups_dir.name}/{backup_path.name}"
            )
            self.lbl_status.config(text=f"Saved updated calibration to {self.target_file.name}")
        except Exception as e:
            messagebox.showerror("Save Failed", f"Failed to save to {self.target_file.name}:\n{e}")

    def copy_python_code(self):
        snippet = (
            f"# Calibrated coordinates & keybinds for Mania Player ({self.key_count} Keys)\n"
            f"JUDGEMENENT_LINE = {self.judgement_line}\n"
            f"INPUT_DELAY_MS = {self.input_delay_ms}\n"
            f"SKILL_LEVEL = {self.skill_level}\n"
            f"MISREAD_CHANCE = {self._format_num(self.misread_chance)}\n"
            f"MISREAD_MS = {self._format_num(self.misread_ms)}\n"
            f"STAMINA_MAX = {self._format_num(self.stamina_max)}\n"
            f"STAMINA_REGEN = {self._format_num(self.stamina_regen, precision=3)}\n"
            f"STRAIN_STEP_PCT = {self._format_num(self.strain_step_pct)}\n"
            f"STRAIN_MISREAD_PCT = {self._format_num(self.strain_misread_pct)}\n"
            f"STRAIN_SKILL_MS = {self._format_num(self.strain_skill_ms)}\n"
            f"STRAIN_REGEN_PCT = {self._format_num(self.strain_regen_pct)}\n"
            f"LANES = {self.lane_rel_x[:self.key_count]}\n"
            f"KEYS = {self.lane_keys[:self.key_count]}\n"
            f"BBOX = ({self.bbox_left}, {self.bbox_top}, {self.bbox_right}, {self.bbox_bottom})\n"
        )
        for i in range(min(4, self.key_count)):
            snippet += f"LANE{i+1} = {self.lane_rel_x[i]}\n"
            snippet += f'KEY{i+1} = "{self.lane_keys[i]}"\n'
        self.root.clipboard_clear()
        self.root.clipboard_append(snippet)
        self.lbl_status.config(text="Calibration code snippet copied to clipboard!")
        messagebox.showinfo("Copied", f"Code copied to clipboard:\n\n{snippet}")


def main():
    root = tk.Tk()
    app = ManiaHarnessApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
