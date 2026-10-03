"""
Mania Player - Python Engine
Supports high-speed screen capture (MSS / PIL), keyboard automation (pynput),
and live coordinate configuration.
"""

import os
import sys
import time
import json
import collections
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

# Enable 1ms timer precision on Windows
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

FOLDER_PATH = Path(__file__).resolve().parent
FOLDERPATH = FOLDER_PATH
CONFIG_PATH = FOLDER_PATH / "mania_config.json"
SCREENSHOT_PATH = FOLDER_PATH / "Screenshot.png"
SCREENPATH = SCREENSHOT_PATH

# Ensure required runtime folders exist
(FOLDER_PATH / "presets").mkdir(parents=True, exist_ok=True)
(FOLDER_PATH / "backups").mkdir(parents=True, exist_ok=True)
(Path.cwd() / "presets").mkdir(parents=True, exist_ok=True)
(Path.cwd() / "backups").mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------
# Calibrated coordinates (synced with mania_config.json & GUI)
# -------------------------------------------------------------
JUDGEMENENT_LINE = 0
INPUT_DELAY_MS = 0
DELAY_MS = 0
LANE1 = 68
LANE2 = 204
LANE3 = 341
LANE4 = 477
LANES = [68, 204, 341, 477]
BBOX = (680, 982, 1226, 983)
KEY1 = "q"
KEY2 = "w"
KEY3 = "["
KEY4 = "]"
KEYS = ["q", "w", "[", "]"]

p_status = True
is_running = False

# Default preset configuration
DEFAULT_CONFIG = {
    "preset_name": "WhiteCat Skin 23 Speed (Default)",
    "bbox": [680, 982, 1226, 983],
    "judgement_line": 0,
    "input_delay_ms": 0,
    "delay_ms": 0,
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
    global BBOX, JUDGEMENENT_LINE, LANE1, LANE2, LANE3, LANE4, KEY1, KEY2, KEY3, KEY4, LANES, KEYS, INPUT_DELAY_MS, DELAY_MS
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
    INPUT_DELAY_MS = int(config.get("input_delay_ms", config.get("delay_ms", 0)))
    DELAY_MS = INPUT_DELAY_MS
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
            "input_delay_ms": config.get("input_delay_ms", INPUT_DELAY_MS),
            "delay_ms": config.get("delay_ms", INPUT_DELAY_MS),
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
        num_lanes = len(self.lanes)
        lane_byte_offsets = []
        thresh_sums = []
        keys = []
        for lane in self.lanes:
            x_clamped = min(max(0, int(lane.get("x", 0))), self.width - 1)
            lane_byte_offsets.append(y_off + (x_clamped * 4))
            th = float(lane.get("threshold", self.global_threshold))
            thresh_sums.append(th * 3.0)
            keys.append(lane["parsed_key"])

        lane_byte_offsets = tuple(lane_byte_offsets)
        thresh_sums = tuple(thresh_sums)
        keys = tuple(keys)
        pressed_states = [False] * num_lanes

        delayed_events = collections.deque()
        delay_sec = max(0.0, float(self.config.get("input_delay_ms", self.config.get("delay_ms", INPUT_DELAY_MS))) / 1000.0)

        while self.p_status and not self.return_to_menu:
            if not self.is_running:
                if delayed_events:
                    delayed_events.clear()
                time.sleep(0.01)
                continue

            # Process due delayed events before screen grab
            if delay_sec > 0 and delayed_events:
                t_now = time.perf_counter()
                while delayed_events and delayed_events[0][0] <= t_now:
                    _, act, k = delayed_events.popleft()
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

            shot = self.sct.grab(self.mss_monitor)
            raw = shot.raw
            t_now = time.perf_counter()

            # Process due delayed events immediately after grab
            if delay_sec > 0 and delayed_events:
                while delayed_events and delayed_events[0][0] <= t_now:
                    _, act, k = delayed_events.popleft()
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

            for idx in range(num_lanes):
                off = lane_byte_offsets[idx]
                hit = (raw[off] + raw[off + 1] + raw[off + 2]) > thresh_sums[idx]
                k = keys[idx]

                if hit:
                    if not pressed_states[idx]:
                        pressed_states[idx] = True
                        self.pressed_state[k] = True
                        if delay_sec > 0:
                            delayed_events.append((t_now + delay_sec, 1, k))
                        else:
                            try:
                                self.keyboard.press(k)
                            except Exception:
                                pass
                else:
                    if pressed_states[idx]:
                        pressed_states[idx] = False
                        self.pressed_state[k] = False
                        if delay_sec > 0:
                            delayed_events.append((t_now + delay_sec, 0, k))
                        else:
                            try:
                                self.keyboard.release(k)
                            except Exception:
                                pass

            if show_fps:
                loop_count += 1
                now = time.time()
                elapsed = now - last_time
                if elapsed >= fps_interval:
                    fps = round(loop_count / elapsed, 1)
                    del_info = f" | Delay: {int(delay_sec*1000)}ms" if delay_sec > 0 else ""
                    print(f"\r[Engine Status] Running (MSS Engine) - {fps} FPS{del_info}  ", end="", flush=True)
                    loop_count = 0
                    last_time = now

        delayed_events.clear()

    def run_pil_loop(self):
        show_fps = self.config.get("show_fps", True)
        fps_interval = float(self.config.get("fps_report_interval", 2.0))
        loop_count = 0
        last_time = time.time()

        num_lanes = len(self.lanes)
        lane_xs = []
        thresh_sums = []
        keys = []
        for lane in self.lanes:
            lane_xs.append(min(max(0, int(lane.get("x", 0))), self.width - 1))
            th = float(lane.get("threshold", self.global_threshold))
            thresh_sums.append(th * 3.0)
            keys.append(lane["parsed_key"])

        lane_xs = tuple(lane_xs)
        thresh_sums = tuple(thresh_sums)
        keys = tuple(keys)
        pressed_states = [False] * num_lanes

        delayed_events = collections.deque()
        delay_sec = max(0.0, float(self.config.get("input_delay_ms", self.config.get("delay_ms", INPUT_DELAY_MS))) / 1000.0)

        while self.p_status and not self.return_to_menu:
            if not self.is_running:
                if delayed_events:
                    delayed_events.clear()
                time.sleep(0.01)
                continue

            try:
                t_now = time.perf_counter()
                if delay_sec > 0 and delayed_events:
                    while delayed_events and delayed_events[0][0] <= t_now:
                        _, act, k = delayed_events.popleft()
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

                img = ImageGrab.grab(bbox=self.bbox)
                px = img.load()
                t_now = time.perf_counter()

                for idx in range(num_lanes):
                    x = lane_xs[idx]
                    rgb = px[x, self.judgement_line]
                    hit = (rgb[0] + rgb[1] + rgb[2]) > thresh_sums[idx]
                    k = keys[idx]

                    if hit:
                        if not pressed_states[idx]:
                            pressed_states[idx] = True
                            self.pressed_state[k] = True
                            if delay_sec > 0:
                                delayed_events.append((t_now + delay_sec, 1, k))
                            else:
                                try:
                                    self.keyboard.press(k)
                                except Exception:
                                    pass
                    else:
                        if pressed_states[idx]:
                            pressed_states[idx] = False
                            self.pressed_state[k] = False
                            if delay_sec > 0:
                                delayed_events.append((t_now + delay_sec, 0, k))
                            else:
                                try:
                                    self.keyboard.release(k)
                                except Exception:
                                    pass

                if show_fps:
                    loop_count += 1
                    now = time.time()
                    elapsed = now - last_time
                    if elapsed >= fps_interval:
                        fps = round(loop_count / elapsed, 1)
                        del_info = f" | Delay: {int(delay_sec*1000)}ms" if delay_sec > 0 else ""
                        print(f"\r[Engine Status] Running (PIL Engine) - {fps} FPS{del_info}  ", end="", flush=True)
                        loop_count = 0
                        last_time = now

            except Exception:
                time.sleep(0.005)

        delayed_events.clear()

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
        pk = parse_key(k)
        if sum(px[lx, JUDGEMENENT_LINE][:3]) > 90:
            try:
                keyboard.press(pk)
            except Exception:
                pass
        else:
            try:
                keyboard.release(pk)
            except Exception:
                pass


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
