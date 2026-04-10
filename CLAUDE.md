# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

SoundSwitch is a PyQt5 GUI application for Linux that routes PipeWire audio streams to virtual sinks. It creates four named virtual sinks (Game, Media, Chat, Aux) and lets users route application streams to them via drag-and-drop, with optional auto-routing rules and loopback to hardware outputs.

## Running the Application

```bash
# Activate the virtual environment first
source .venv/bin/activate

# Run normally
python3 SoundSwitch.py

# Run minimized to system tray
python3 SoundSwitch.py --minimized
```

There is no build step, test suite, or lint configuration.

## Architecture

All application logic lives in `SoundSwitch.py` (single file, ~766 lines). `testapp.py` is an identical scratch copy used during development.

**Audio backend** — all PipeWire interaction goes through `pactl` subprocess calls (`run_pactl()`). There are no direct PipeWire Python bindings in use despite the `pipewire_python` package being installed.

**Virtual sink topology:**
- Four null sinks are created on startup via `ensure_custom_sinks()` → `pactl load-module module-null-sink`
- Each virtual sink is looped back to the active hardware output via `setup_custom_sink_loopbacks()` → `pactl load-module module-loopback`
- Loopback module IDs are persisted in `routing_state.json` so they can be unloaded cleanly

**Stream routing:**
- `apply_routing_rules()` checks each active sink input against named rules and moves matching streams automatically
- Manual drag-and-drop moves call `move_sink_input()` and record the override in `state['manual_overrides']` so auto-routing does not move it back
- Internal loopback streams are filtered out of the UI

**State persistence (`routing_state.json`):**
```json
{
  "loopbacks": { "Game": { "<module_id>": { "source": "Game.monitor", "sink": "<hw_sink>" } } },
  "default_sink": "<hw_sink_name>",
  "rules": [{ "app_name": "Firefox", "sink": "Aux" }],
  "manual_overrides": { "<stream_index>": "<sink_name>" }
}
```

**UI layout** — three panels built in `MainWindow.__init__`:
- Left: active streams (`DraggableListWidget`), auto-routing rules editor
- Center: four `SinkDropListWidget` drop targets (Game / Media / Chat / Aux)
- Right: hardware outputs list, set-default button

**Refresh cycle** — a 2-second `QTimer` calls `refresh_ui()`, which snapshots current PipeWire state and only updates widgets if something changed, keeping CPU usage low.

## Key Classes

| Class | Location | Purpose |
|---|---|---|
| `MainWindow` | line 153 | Application root; owns all state and coordinates UI ↔ audio |
| `DraggableListWidget` | line 15 | Source list; emits `application/x-sink-input-index` MIME on drag |
| `SinkDropListWidget` | line 51 | Drop target; calls `move_sink_input_callback` on drop |
| `RoundedBoxDelegate` | line 86 | Custom item painter; dark theme, blue accent for default sink |
