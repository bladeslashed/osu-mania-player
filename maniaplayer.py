"""
Mania Player - Python Engine
Supports high-speed screen capture (MSS / PIL), keyboard automation (pynput),
and live coordinate configuration.
"""

import os
import sys
import time
import json
import random
import heapq
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
INPUT_DELAY_MS = 290
DELAY_MS = 290
SKILL_LEVEL = 10
SKILL_LEVEL_MS = 0
MISREAD_CHANCE = 0
MISREAD_MS = 0.4
STAMINA_MAX = 100.5
STAMINA_REGEN = 0.4
STRAIN_STEP_PCT = 1.5
STRAIN_MISREAD_PCT = 0.2
STRAIN_SKILL_MS = 0.5
STRAIN_REGEN_PCT = 0.5
LANE1 = 53
LANE2 = 160
LANE3 = 267
LANE4 = 374
LANES = [53, 160, 267, 374]
BBOX = (746, 392, 1174, 393)
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
    "bbox": [746, 392, 1174, 393],
    "judgement_line": 0,
    "input_delay_ms": 0,
    "delay_ms": 0,
    "skill_level": 0,
    "skill_level_ms": 0,
    "misread_chance": 0,
    "misread_ms": 0,
    "stamina_max": 0,
    "stamina_regen": 0.0,
    "strain_step_pct": 0,
    "strain_misread_pct": 0,
    "strain_skill_ms": 0,
    "strain_regen_pct": 0,
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
    global BBOX, JUDGEMENENT_LINE, LANE1, LANE2, LANE3, LANE4, KEY1, KEY2, KEY3, KEY4, LANES, KEYS, INPUT_DELAY_MS, DELAY_MS, SKILL_LEVEL, SKILL_LEVEL_MS
    global MISREAD_CHANCE, MISREAD_MS, STAMINA_MAX, STAMINA_REGEN
    global STRAIN_STEP_PCT, STRAIN_MISREAD_PCT, STRAIN_SKILL_MS, STRAIN_REGEN_PCT
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
    SKILL_LEVEL = int(config.get("skill_level", config.get("skill_level_ms", config.get("input_variance_ms", 0))))
    SKILL_LEVEL_MS = SKILL_LEVEL
    MISREAD_CHANCE = min(100.0, max(0.0, float(config.get("misread_chance", 0))))
    MISREAD_MS = max(0.0, float(config.get("misread_ms", 0)))
    STAMINA_MAX = max(0.0, float(config.get("stamina_max", 0)))
    STAMINA_REGEN = max(0.0, float(config.get("stamina_regen", 0.0)))
    STRAIN_STEP_PCT = max(0.0, float(config.get("strain_step_pct", 0)))
    STRAIN_MISREAD_PCT = max(0.0, float(config.get("strain_misread_pct", 0)))
    STRAIN_SKILL_MS = max(0.0, float(config.get("strain_skill_ms", 0)))
    STRAIN_REGEN_PCT = max(0.0, float(config.get("strain_regen_pct", 0)))
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
            "skill_level": config.get("skill_level", SKILL_LEVEL),
            "skill_level_ms": config.get("skill_level_ms", SKILL_LEVEL),
            "misread_chance": config.get("misread_chance", MISREAD_CHANCE),
            "misread_ms": config.get("misread_ms", MISREAD_MS),
            "stamina_max": config.get("stamina_max", STAMINA_MAX),
            "stamina_regen": config.get("stamina_regen", STAMINA_REGEN),
            "strain_step_pct": config.get("strain_step_pct", STRAIN_STEP_PCT),
            "strain_misread_pct": config.get("strain_misread_pct", STRAIN_MISREAD_PCT),
            "strain_skill_ms": config.get("strain_skill_ms", STRAIN_SKILL_MS),
            "strain_regen_pct": config.get("strain_regen_pct", STRAIN_REGEN_PCT),
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


class SkillSimulator:
    """Human-like skill limits applied on top of note detection.

    - Misread: each note press has a `misread_chance`% chance of being ignored; the
      affected lane then ignores all inputs for `misread_ms` milliseconds.
    - Stamina: a pool of `stamina_max` clicks. Every click costs 1; the pool regenerates
      `stamina_regen` per 20 ms (continuously). Inputs are ignored while stamina < 1.
    - Strain: every `strain_step_pct`% stamina lost, misread chance increases by `strain_misread_pct`%,
      skill level delay increases by `strain_skill_ms` ms, and stamina gain decreases by `strain_regen_pct`%.
      These adjustments are additive.
    """
    __slots__ = (
        "num_lanes", "misread_chance", "misread_sec", "stamina_max", "base_regen_per_sec",
        "stamina", "last_t", "blocked_until",
        "strain_step_pct", "strain_misread_pct", "strain_skill_ms", "strain_regen_pct",
        "base_skill_level", "curr_misread_chance", "curr_skill_level", "curr_regen_per_20ms"
    )

    def __init__(self, num_lanes, misread_chance=0, misread_ms=0, stamina_max=0, stamina_regen=0.0,
                 strain_step_pct=0, strain_misread_pct=0, strain_skill_ms=0, strain_regen_pct=0,
                 base_skill_level=0):
        self.num_lanes = num_lanes
        self.misread_chance = max(0.0, min(100.0, float(misread_chance)))
        self.misread_sec = max(0.0, float(misread_ms)) / 1000.0
        self.stamina_max = max(0.0, float(stamina_max))
        self.base_regen_per_sec = max(0.0, float(stamina_regen)) * 50.0  # per 20 ms -> per second
        self.strain_step_pct = max(0.0, float(strain_step_pct))
        self.strain_misread_pct = max(0.0, float(strain_misread_pct))
        self.strain_skill_ms = max(0.0, float(strain_skill_ms))
        self.strain_regen_pct = max(0.0, float(strain_regen_pct))
        self.base_skill_level = max(0.0, float(base_skill_level))

        self.stamina = float(self.stamina_max)
        self.last_t = time.perf_counter()
        self.blocked_until = [0.0] * num_lanes

        self.curr_misread_chance = self.misread_chance
        self.curr_skill_level = self.base_skill_level
        self.curr_regen_per_20ms = float(stamina_regen)

    @property
    def enabled(self):
        return self.misread_chance > 0 or self.stamina_max > 0

    def update(self, t_now):
        """Updates stamina regeneration and calculates current strain effects."""
        if self.stamina_max > 0:
            dt = t_now - self.last_t
            if dt > 0:
                lost_pct = max(0.0, (1.0 - (self.stamina / self.stamina_max)) * 100.0)
                steps = int(lost_pct / self.strain_step_pct) if self.strain_step_pct > 0 else 0
                regen_factor = max(0.0, 1.0 - (steps * (self.strain_regen_pct / 100.0)))
                eff_regen_sec = self.base_regen_per_sec * regen_factor
                self.stamina = min(float(self.stamina_max), self.stamina + dt * eff_regen_sec)
                self.last_t = t_now

            lost_pct = max(0.0, (1.0 - (self.stamina / self.stamina_max)) * 100.0)
            steps = int(lost_pct / self.strain_step_pct) if self.strain_step_pct > 0 else 0
            self.curr_misread_chance = min(100.0, max(0.0, self.misread_chance + (steps * self.strain_misread_pct)))
            self.curr_skill_level = max(0.0, self.base_skill_level + (steps * self.strain_skill_ms))
            self.curr_regen_per_20ms = (self.base_regen_per_sec / 50.0) * max(0.0, 1.0 - (steps * (self.strain_regen_pct / 100.0)))
        else:
            self.curr_misread_chance = self.misread_chance
            self.curr_skill_level = self.base_skill_level
            self.curr_regen_per_20ms = 0.0

    def allow_press(self, lane_idx, t_now):
        """Returns True if the note press on this lane should be performed."""
        self.update(t_now)

        if self.curr_misread_chance > 0:
            if t_now < self.blocked_until[lane_idx]:
                return False
            if random.random() * 100.0 < self.curr_misread_chance:
                self.blocked_until[lane_idx] = t_now + self.misread_sec
                return False

        if self.stamina_max > 0:
            if self.stamina < 1.0:
                return False
            self.stamina -= 1.0
            # Recalculate strain after consuming click
            lost_pct = max(0.0, (1.0 - (self.stamina / self.stamina_max)) * 100.0)
            steps = int(lost_pct / self.strain_step_pct) if self.strain_step_pct > 0 else 0
            self.curr_misread_chance = min(100.0, max(0.0, self.misread_chance + (steps * self.strain_misread_pct)))
            self.curr_skill_level = max(0.0, self.base_skill_level + (steps * self.strain_skill_ms))
            self.curr_regen_per_20ms = (self.base_regen_per_sec / 50.0) * max(0.0, 1.0 - (steps * (self.strain_regen_pct / 100.0)))

        return True

    def get_live_stats(self, t_now=None):
        if t_now is None:
            t_now = time.perf_counter()
        self.update(t_now)
        lost_pct = max(0.0, (1.0 - (self.stamina / self.stamina_max)) * 100.0) if self.stamina_max > 0 else 0.0
        steps = int(lost_pct / self.strain_step_pct) if (self.stamina_max > 0 and self.strain_step_pct > 0) else 0
        return {
            "stamina": self.stamina,
            "stamina_max": self.stamina_max,
            "stamina_pct": (self.stamina / self.stamina_max * 100.0) if self.stamina_max > 0 else 100.0,
            "stamina_lost_pct": lost_pct,
            "strain_steps": steps,
            "misread_chance": self.curr_misread_chance,
            "base_misread_chance": self.misread_chance,
            "regen_per_20ms": self.curr_regen_per_20ms,
            "base_regen_per_20ms": self.base_regen_per_sec / 50.0,
            "skill_level": self.curr_skill_level,
            "base_skill_level": self.base_skill_level,
        }


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

    def _make_skill_sim(self, num_lanes):
        """Builds a SkillSimulator from config (falls back to module globals); None if all features off."""
        cfg = self.config
        base_sk = int(cfg.get("skill_level", cfg.get("skill_level_ms", cfg.get("input_variance_ms", SKILL_LEVEL))))
        sim = SkillSimulator(
            num_lanes,
            misread_chance=cfg.get("misread_chance", MISREAD_CHANCE),
            misread_ms=cfg.get("misread_ms", MISREAD_MS),
            stamina_max=cfg.get("stamina_max", STAMINA_MAX),
            stamina_regen=cfg.get("stamina_regen", STAMINA_REGEN),
            strain_step_pct=cfg.get("strain_step_pct", STRAIN_STEP_PCT),
            strain_misread_pct=cfg.get("strain_misread_pct", STRAIN_MISREAD_PCT),
            strain_skill_ms=cfg.get("strain_skill_ms", STRAIN_SKILL_MS),
            strain_regen_pct=cfg.get("strain_regen_pct", STRAIN_REGEN_PCT),
            base_skill_level=base_sk,
        )
        return sim if sim.enabled else None

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

        # Pre-pack lane records: (offset, threshold_sum, parsed_key, lane_idx)
        # Highly optimized for 7K-20K: eliminates per-frame tuple indexing and dict lookups
        lane_records = []
        for idx, lane in enumerate(self.lanes):
            x_clamped = min(max(0, int(lane.get("x", 0))), self.width - 1)
            byte_off = y_off + (x_clamped * 4)
            th = float(lane.get("threshold", self.global_threshold))
            lane_records.append((byte_off, th * 3.0, lane["parsed_key"], idx))

        lane_records = tuple(lane_records)
        pressed_states = [False] * num_lanes
        lane_hold_offsets = [0.0] * num_lanes

        delayed_events = [] # Binary min-heap: (due_time, seq, action, key, lane_idx)
        event_seq = 0
        delay_sec = max(0.0, float(self.config.get("input_delay_ms", self.config.get("delay_ms", INPUT_DELAY_MS))) / 1000.0)
        skill_level = int(self.config.get("skill_level", self.config.get("skill_level_ms", self.config.get("input_variance_ms", SKILL_LEVEL))))
        has_delay_or_skill = (delay_sec > 0 or skill_level > 0)
        skill_sim = self._make_skill_sim(num_lanes)
        lane_skipped = [False] * num_lanes

        while self.p_status and not self.return_to_menu:
            if not self.is_running:
                if delayed_events:
                    delayed_events.clear()
                time.sleep(0.01)
                continue

            # Process due delayed events in exact chronological order before screen grab
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

            shot = self.sct.grab(self.mss_monitor)
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

            for off, th_sum, k, idx in lane_records:
                hit = (raw[off] + raw[off + 1] + raw[off + 2]) > th_sum

                if hit:
                    if not pressed_states[idx]:
                        pressed_states[idx] = True
                        if skill_sim is not None and not skill_sim.allow_press(idx, t_now):
                            lane_skipped[idx] = True
                            continue
                        lane_skipped[idx] = False
                        self.pressed_state[k] = True
                        if has_delay_or_skill:
                            eff_skill = skill_sim.curr_skill_level if skill_sim is not None else skill_level
                            var_sec = (random.uniform(-eff_skill, eff_skill) / 1000.0) if eff_skill > 0 else 0.0
                            eff_delay = max(0.0, delay_sec + var_sec)
                            lane_hold_offsets[idx] = eff_delay
                            if eff_delay > 0:
                                event_seq += 1
                                heapq.heappush(delayed_events, (t_now + eff_delay, event_seq, 1, k, idx))
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
                    if pressed_states[idx]:
                        pressed_states[idx] = False
                        if lane_skipped[idx]:
                            lane_skipped[idx] = False
                            continue
                        self.pressed_state[k] = False
                        if has_delay_or_skill:
                            hold_offset = lane_hold_offsets[idx]
                            if hold_offset > 0:
                                event_seq += 1
                                heapq.heappush(delayed_events, (t_now + hold_offset, event_seq, 0, k, idx))
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

            if show_fps:
                loop_count += 1
                now = time.time()
                elapsed = now - last_time
                if elapsed >= fps_interval:
                    fps = round(loop_count / elapsed, 1)
                    del_info = f" | Delay: {int(delay_sec*1000)}ms" if delay_sec > 0 else ""
                    skill_info = f" | Skill: ±{skill_level}ms" if skill_level > 0 else ""
                    print(f"\r[Engine Status] Running (MSS Engine) - {fps} FPS{del_info}{skill_info}  ", end="", flush=True)
                    loop_count = 0
                    last_time = now

        delayed_events.clear()

    def run_pil_loop(self):
        show_fps = self.config.get("show_fps", True)
        fps_interval = float(self.config.get("fps_report_interval", 2.0))
        loop_count = 0
        last_time = time.time()

        num_lanes = len(self.lanes)
        lane_records = []
        for idx, lane in enumerate(self.lanes):
            x_clamped = min(max(0, int(lane.get("x", 0))), self.width - 1)
            th = float(lane.get("threshold", self.global_threshold))
            lane_records.append((x_clamped, th * 3.0, lane["parsed_key"], idx))

        lane_records = tuple(lane_records)
        pressed_states = [False] * num_lanes
        lane_hold_offsets = [0.0] * num_lanes

        delayed_events = [] # Binary min-heap: (due_time, seq, action, key, lane_idx)
        event_seq = 0
        delay_sec = max(0.0, float(self.config.get("input_delay_ms", self.config.get("delay_ms", INPUT_DELAY_MS))) / 1000.0)
        skill_level = int(self.config.get("skill_level", self.config.get("skill_level_ms", self.config.get("input_variance_ms", SKILL_LEVEL))))
        has_delay_or_skill = (delay_sec > 0 or skill_level > 0)
        skill_sim = self._make_skill_sim(num_lanes)
        lane_skipped = [False] * num_lanes

        while self.p_status and not self.return_to_menu:
            if not self.is_running:
                if delayed_events:
                    delayed_events.clear()
                time.sleep(0.01)
                continue

            try:
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

                img = ImageGrab.grab(bbox=self.bbox)
                px = img.load()
                t_now = time.perf_counter()

                for x, th_sum, k, idx in lane_records:
                    rgb = px[x, self.judgement_line]
                    hit = (rgb[0] + rgb[1] + rgb[2]) > th_sum

                    if hit:
                        if not pressed_states[idx]:
                            pressed_states[idx] = True
                            if skill_sim is not None and not skill_sim.allow_press(idx, t_now):
                                lane_skipped[idx] = True
                                continue
                            lane_skipped[idx] = False
                            self.pressed_state[k] = True
                            if has_delay_or_skill:
                                eff_skill = skill_sim.curr_skill_level if skill_sim is not None else skill_level
                                var_sec = (random.uniform(-eff_skill, eff_skill) / 1000.0) if eff_skill > 0 else 0.0
                                eff_delay = max(0.0, delay_sec + var_sec)
                                lane_hold_offsets[idx] = eff_delay
                                if eff_delay > 0:
                                    event_seq += 1
                                    heapq.heappush(delayed_events, (t_now + eff_delay, event_seq, 1, k, idx))
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
                        if pressed_states[idx]:
                            pressed_states[idx] = False
                            if lane_skipped[idx]:
                                lane_skipped[idx] = False
                                continue
                            self.pressed_state[k] = False
                            if has_delay_or_skill:
                                hold_offset = lane_hold_offsets[idx]
                                if hold_offset > 0:
                                    event_seq += 1
                                    heapq.heappush(delayed_events, (t_now + hold_offset, event_seq, 0, k, idx))
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

                if show_fps:
                    loop_count += 1
                    now = time.time()
                    elapsed = now - last_time
                    if elapsed >= fps_interval:
                        fps = round(loop_count / elapsed, 1)
                        del_info = f" | Delay: {int(delay_sec*1000)}ms" if delay_sec > 0 else ""
                        skill_info = f" | Skill: ±{skill_level}ms" if skill_level > 0 else ""
                        print(f"\r[Engine Status] Running (PIL Engine) - {fps} FPS{del_info}{skill_info}  ", end="", flush=True)
                        loop_count = 0
                        last_time = now

            except Exception:
                time.sleep(0.005)

        delayed_events.clear()

    def run(self):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleTitleW("Osu!Mania Player v1.3.0")
            except Exception:
                pass
        self.init_capture()
        self.start_listener()
        print("\n=======================================================")
        print("  Osu!Mania Player v1.3.0 Activated!")
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
