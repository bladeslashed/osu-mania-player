# ManiaPlayer V1.0

A high-performance computer vision bot and calibration harness for **osu!mania** (4-key mode).

---

## 📁 Folder Structure

| File / Folder | Purpose |
|---|---|
| `mania_gui.py` | Modern Dark GUI dashboard with live lane indicators and instant start/stop |
| `mania_harness.py` | Visual Calibration Harness for tuning BBOX, judgement line, lane positions, and keybinds |
| `maniaplayer.py` | High-speed Python engine with MSS and PIL capture modes |
| `maniaplayer.exe` | Compiled standalone executable of Mania Player GUI |
| `presets/` | Directory storing custom namable JSON presets |
| `mania_config.json` | Configuration file storing active BBOX, lane coordinates, and hotkeys |
| `settings.json` | Native C engine configuration file synchronized with the harness |
| `maniaplayer.c` | Native Win32 C implementation for ultra-low latency execution |
| `build.bat` | GCC compilation script for `maniaplayer.c` |
| `run_gui.bat` | Quick launcher for the GUI dashboard |
| `run_calibrator.bat` | Quick launcher for the Calibration Harness |
| `run_player.bat` | Quick launcher for the Python engine in console mode |
| `Screenshot.png` | Reference screenshot asset for calibration |

---

## 🚀 Key Features

1. **Custom Keybinds**:
   - Change keybinds directly in the Calibrator for each lane (e.g. `Q`, `W`, `[`, `]`, `D`, `F`, `J`, `K`, `A`, `S`, `K`, `L`, etc.).
   - Quick 1-click key preset buttons: `QW[]`, `DFJK`, `ASKL`, `ZX./`.
   - Keybinds immediately update the GUI lane visualizer, live detection strip, and bot execution.

2. **Presets Manager**:
   - Dedicated `presets/` folder storing custom namable `.json` files.
   - **📂 Load Preset**: Instantly loads BBOX coordinates, judgement line, lane offsets, and keybinds from any preset.
   - **💾 Save As...**: Saves your current calibration and key setup as a custom named preset.
   - **📁 Presets Folder**: Opens the presets directory in Windows Explorer.

3. **Live Synchronization with Mania Player**:
   - Opening the Calibrator via `🎯 Open Calibrator` from the GUI (or compiled `maniaplayer.exe`) opens the true calibrator instance targeted directly at `maniaplayer.py` and `mania_config.json`.
   - Saving or applying updates in the Calibrator immediately syncs to the running player in real time.

4. **Always on Top**:
   - The Calibration Harness stays on top of osu!mania and all other windows by default.
   - Interactive `📌 Always on Top` toggle in the top control bar.

5. **Disappearing Screenshot Capture**:
   - Clicking `📸 Capture Now` or `⏱️ In 2s (Switch Window)` temporarily hides the harness window completely before grabbing the screen, then restores it on top.

6. **Global Hotkeys**:
   - `F1`: Start playing / tracking notes
   - `F2`: Stop / pause
   - `F3`: Capture screenshot
   - `F4`: Exit application
