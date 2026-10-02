"""
Mania Player - Python Engine
Supports high-speed screen capture (MSS / PIL), keyboard automation (pynput),
and live coordinate configuration.
"""

import os
import sys
import time
import json
import threading
from pathlib import Path
from PIL import ImageGrab
from pynput.keyboard import Key, Controller, Listener

try:
    import mss
    HAS_MSS = True
    MSS_FACTORY = getattr(mss, "MSS", getattr(mss, "mss", None))
except ImportError:
    HAS_MSS = False
    MSS_FACTORY = None

FOLDER_PATH = Path(__file__).resolve().parent
FOLDERPATH = FOLDER_PATH
CONFIG_PATH = FOLDER_PATH / "mania_config.json"
SCREENSHOT_PATH = FOLDER_PATH / "Screenshot.png"
SCREENPATH = SCREENSHOT_PATH

# -------------------------------------------------------------
# Calibrated coordinates (synced with mania_config.json & GUI)
# -------------------------------------------------------------
JUDGEMENENT_LINE = 0
LANE1 = 39
LANE2 = 411
LANE3 = 456
LANE4 = 479
LANES = [39, 411, 456, 479]
BBOX = (677, 943, 1225, 944)
KEY1 = "q"
KEY2 = "k"
KEY3 = "k"
KEY4 = "]"
KEYS = ["q", "k", "k", "]"]

p_status = True
is_running = False

# Default preset configuration
DEFAULT_CONFIG = {
    "preset_name": "WhiteCat Skin 23 Speed (Default)",
    "bbox": [677, 943, 1225, 944],
    "judgement_line": 0,
    "global_threshold": 30,
    "lanes": [
        {"name": "Lane 1", "x": 39, "key": "q", "threshold": 30},
        {"name": "Lane 2", "x": 215, "key": "w", "threshold": 30},
        {"name": "Lane 3", "x": 353, "key": "[", "threshold": 30},
        {"name": "Lane 4", "x": 502, "key": "]", "threshold": 30}
    ],
    "input_mode": "hold",
    "capture_backend": "auto",
    "show_fps": True,
    "fps_report_interval": 2.0,
    "hotkeys": {
        "start": "f",
        "stop": "s",
        "menu": "m",
        "exit": "/"
    }
}


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


def key_to_str(key_obj):
    """Returns human-readable representation of a key."""
    if isinstance(key_obj, Key):
        return key_obj.name
    return str(key_obj)


def load_config():
    """Loads configuration from mania_config.json if available, and synchronizes module globals."""
    global BBOX, JUDGEMENENT_LINE, LANE1, LANE2, LANE3, LANE4, KEY1, KEY2, KEY3, KEY4, LANES, KEYS
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            config.update(data)
        except Exception as e:
            print(f"[Config Warning] Could not load {CONFIG_PATH.name}: {e}. Using defaults.")

    raw_bbox = config.get("bbox", DEFAULT_CONFIG["bbox"])
    if len(raw_bbox) == 4:
        BBOX = tuple(int(x) for x in raw_bbox)
    JUDGEMENENT_LINE = int(config.get("judgement_line", 0))
    lanes = config.get("lanes", [])
    if lanes:
        LANES = [int(l.get("x", 0)) for l in lanes]
        KEYS = [str(l.get("key", "a")).lower() for l in lanes]
        for i, l in enumerate(lanes[:4]):
            if i == 0:
                LANE1, KEY1 = int(l.get("x", 39)), str(l.get("key", "q"))
            elif i == 1:
                LANE2, KEY2 = int(l.get("x", 215)), str(l.get("key", "w"))
            elif i == 2:
                LANE3, KEY3 = int(l.get("x", 353)), str(l.get("key", "["))
            elif i == 3:
                LANE4, KEY4 = int(l.get("x", 502)), str(l.get("key", "]"))

    return config


def save_config(config):
    """Saves configuration to mania_config.json and settings.json."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print(f"[Config] Saved settings to {CONFIG_PATH.name}")

        # Also sync settings.json if exists or alongside
        settings_path = FOLDER_PATH / "settings.json"
        s_data = {
            "bbox": config.get("bbox", list(BBOX)),
            "judgement_line": config.get("judgement_line", JUDGEMENENT_LINE),
            "global_threshold": config.get("global_threshold", 30),
            "input_mode": config.get("input_mode", "hold"),
            "lanes": config.get("lanes", [])
        }
        with open(settings_path, "w", encoding="utf-8") as sf:
            json.dump(s_data, sf, indent=2)
    except Exception as e:
        print(f"[Config Error] Failed to save configuration: {e}")


# Initialize module globals on import
load_config()


class ManiaPlayer:
    """High-efficiency osu!mania player with state transition tracking and fast capture."""

    def __init__(self, config=None):
        if config is None:
            config = load_config()
        self.config = config
        self.keyboard = Controller()
        self.is_running = False
        self.p_status = True
        self.return_to_menu = False
        self.pressed_state = {}
        self.active_backend = "pil"
        self.sct = None
        self.listener = None
        self._prepare_runtime_settings()

    def _prepare_runtime_settings(self):
        raw_bbox = self.config.get("bbox", DEFAULT_CONFIG["bbox"])
        self.bbox = tuple(int(v) for v in raw_bbox)
        self.width = max(1, self.bbox[2] - self.bbox[0])
        self.height = max(1, self.bbox[3] - self.bbox[1])
        self.mss_monitor = {
            "left": self.bbox[0],
            "top": self.bbox[1],
            "width": self.width,
            "height": self.height
        }
        self.judgement_line = min(max(0, int(self.config.get("judgement_line", 0))), self.height - 1)
        self.global_threshold = float(self.config.get("global_threshold", 30))
        self.input_mode = self.config.get("input_mode", "hold").lower()

        # Parse keys for all lanes
        self.lanes = []
        for lane in self.config.get("lanes", []):
            l = dict(lane)
            l["parsed_key"] = parse_key(l.get("key"))
            self.lanes.append(l)

    def init_capture(self):
        backend_choice = self.config.get("capture_backend", "auto").lower()
        if HAS_MSS and MSS_FACTORY and backend_choice in ("mss", "auto"):
            try:
                self.sct = MSS_FACTORY()
                self.active_backend = "mss"
                print("[Capture Engine] MSS Direct-Memory (Ultra High FPS) initialized.")
                return
            except Exception as e:
                print(f"[Capture Warning] MSS init failed ({e}). Falling back to PIL.")
        self.active_backend = "pil"
        print("[Capture Engine] PIL ImageGrab backend initialized.")

    def start_listener(self):
        self.listener = Listener(on_press=self.on_key_press)
        self.listener.daemon = True
        self.listener.start()

    def on_key_press(self, key):
        hotkeys = self.config.get("hotkeys", DEFAULT_CONFIG["hotkeys"])
        try:
            char = getattr(key, "char", None)
            if not char:
                # Also handle F1, F2, F4 keys
                if key == Key.f1:
                    if not self.is_running:
                        print("\n[>> START] Mania Player active! Tracking notes...")
                        self.is_running = True
                elif key == Key.f2:
                    if self.is_running:
                        print("\n[|| STOP] Mania Player paused.")
                        self.is_running = False
                        self.release_all_keys()
                elif key == Key.f4:
                    print("\n[XX EXIT] Exiting Mania Player...")
                    self.is_running = False
                    self.p_status = False
                    self.release_all_keys()
                return

            if char == hotkeys.get("start", "f"):
                if not self.is_running:
                    print("\n[>> START] Mania Player active! Tracking notes...")
                    self.is_running = True

            elif char == hotkeys.get("stop", "s"):
                if self.is_running:
                    print("\n[|| STOP] Mania Player paused.")
                    self.is_running = False
                    self.release_all_keys()

            elif char == hotkeys.get("menu", "m"):
                print("\n[Menu] Returning to Configuration Menu...")
                self.is_running = False
                self.release_all_keys()
                self.return_to_menu = True

            elif char == hotkeys.get("exit", "/"):
                print("\n[XX EXIT] Exiting Mania Player...")
                self.is_running = False
                self.p_status = False
                self.release_all_keys()

        except Exception as e:
            print(f"[Hotkey Warning] {e}")

    def take_screenshot(self):
        print(f"\n[Screenshot] Capturing BBOX {self.bbox}...")
        try:
            shot = ImageGrab.grab(bbox=self.bbox)
            shot.save(str(SCREENSHOT_PATH))
            print(f"[Screenshot] Successfully saved: {SCREENSHOT_PATH.name}")
        except Exception as e:
            print(f"[Screenshot Error] {e}")

    def release_all_keys(self):
        for lane in self.lanes:
            k = lane["parsed_key"]
            try:
                self.keyboard.release(k)
            except Exception:
                pass
            self.pressed_state[k] = False

    def run_mss_loop(self):
        show_fps = self.config.get("show_fps", True)
        fps_interval = float(self.config.get("fps_report_interval", 2.0))
        loop_count = 0
        last_time = time.time()

        stride = self.width * 4
        y_off = self.judgement_line * stride
        lane_byte_offsets = []
        for lane in self.lanes:
            x_clamped = min(max(0, int(lane.get("x", 0))), self.width - 1)
            lane_byte_offsets.append(y_off + (x_clamped * 4))

        while self.p_status and not self.return_to_menu:
            if not self.is_running:
                time.sleep(0.01)
                continue

            shot = self.sct.grab(self.mss_monitor)
            raw = shot.raw

            for idx, lane in enumerate(self.lanes):
                off = lane_byte_offsets[idx]
                brightness = (raw[off + 2] + raw[off + 1] + raw[off]) / 3.0
                thresh = float(lane.get("threshold", self.global_threshold))
                k = lane["parsed_key"]

                if brightness > thresh:
                    if not self.pressed_state.get(k, False):
                        self.keyboard.press(k)
                        self.pressed_state[k] = True
                else:
                    if self.pressed_state.get(k, False):
                        self.keyboard.release(k)
                        self.pressed_state[k] = False

            if show_fps:
                loop_count += 1
                now = time.time()
                elapsed = now - last_time
                if elapsed >= fps_interval:
                    fps = round(loop_count / elapsed, 1)
                    print(f"\r[Engine Status] Running (MSS Engine) - {fps} FPS  ", end="", flush=True)
                    loop_count = 0
                    last_time = now

    def run_pil_loop(self):
        show_fps = self.config.get("show_fps", True)
        fps_interval = float(self.config.get("fps_report_interval", 2.0))
        loop_count = 0
        last_time = time.time()

        while self.p_status and not self.return_to_menu:
            if not self.is_running:
                time.sleep(0.01)
                continue

            try:
                img = ImageGrab.grab(bbox=self.bbox)
                px = img.load()

                for lane in self.lanes:
                    x = min(max(0, int(lane.get("x", 0))), self.width - 1)
                    rgb = px[x, self.judgement_line]
                    brightness = sum(rgb[:3]) / 3.0
                    thresh = float(lane.get("threshold", self.global_threshold))
                    k = lane["parsed_key"]

                    if brightness > thresh:
                        if not self.pressed_state.get(k, False):
                            self.keyboard.press(k)
                            self.pressed_state[k] = True
                    else:
                        if self.pressed_state.get(k, False):
                            self.keyboard.release(k)
                            self.pressed_state[k] = False

                if show_fps:
                    loop_count += 1
                    now = time.time()
                    elapsed = now - last_time
                    if elapsed >= fps_interval:
                        fps = round(loop_count / elapsed, 1)
                        print(f"\r[Engine Status] Running (PIL Engine) - {fps} FPS  ", end="", flush=True)
                        loop_count = 0
                        last_time = now

            except Exception as e:
                time.sleep(0.005)

    def run(self):
        self.init_capture()
        self.start_listener()
        print("\n=======================================================")
        print("  Mania Player Activated!")
        print("  Hotkeys:")
        print(f"    [F1 / F] Start Tracking")
        print(f"    [F2 / S] Stop / Pause")
        print(f"    [M]      Return to Settings Menu")
        print(f"    [F4 / /] Exit Program")
        print("=======================================================\n")

        try:
            if self.active_backend == "mss" and self.sct:
                self.run_mss_loop()
            else:
                self.run_pil_loop()
        finally:
            self.release_all_keys()
            if self.listener:
                self.listener.stop()

        return self.return_to_menu


# Standalone classic functions for backward-compatibility
def click(img, keyboard):
    px = img.load()
    for lx, k in zip(LANES, KEYS):
        if sum(px[lx, JUDGEMENENT_LINE]) / 3 > 30:
            keyboard.press(k)
        else:
            keyboard.release(k)


def get_ss(keyboard):
    global is_running
    try:
        while is_running:
            check = ImageGrab.grab(bbox=BBOX)
            click(check, keyboard)
    except KeyboardInterrupt:
        sys.exit(0)


def main():
    player = ManiaPlayer()
    player.run()


if __name__ == "__main__":
    main()
