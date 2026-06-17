# Stream Mute Feature Design

**Date:** 2026-06-17  
**Status:** Approved

## Overview

Add an always-visible mute button to each audio stream item displayed in the four sink panels (Game / Media / Chat / Aux). Clicking the button mutes or unmutes that specific PipeWire sink input via `pactl`.

## Data Layer

### Parsing mute state

`get_sink_inputs()` is extended to parse the `Mute:` line from `pactl list sink-inputs` output. Each stream dict gains a `'muted': bool` field (`True` when muted, `False` when unmuted or absent).

### Toggling mute

A new `toggle_stream_mute(stream_index: str)` method on `MainWindow` calls:

```
pactl set-sink-input-mute <stream_index> toggle
```

After the call it immediately invokes `refresh_devices_and_sinks(force=True)` so the icon updates without waiting for the 2-second timer.

### Change detection

The snapshot tuple in `conditional_refresh()` includes `s.get('muted')` in the sink-inputs element. This ensures any external mute change (e.g. via another tool) is detected and causes a UI redraw within 2 seconds.

No persistence is required — PipeWire holds mute state natively across SoundSwitch restarts.

## UI Layer

### MuteButton class

A `QPushButton` subclass that:

- Is 28×28 px with no border/background (transparent, dark-theme-compatible).
- Draws a 16×16 speaker icon in `paintEvent` using QPainter — consistent with the app's existing programmatic icon style.
  - **Unmuted:** light-coloured speaker body + cone + two small sound-wave arcs.
  - **Muted:** same speaker body + cone, with a red diagonal cross overlaid and no sound waves.
- Accepts a `muted: bool` property and a `stream_index: str` to identify which stream to toggle.

### Sink panel item layout

In `refresh_devices_and_sinks()`, the sink panel loop (lines 1913–1953 in `SoundSwitch.py`) changes from plain `addItem` to `setItemWidget`. The per-item widget uses a `QHBoxLayout`:

```
[ VBoxLayout(main_label, sub_label)  <stretch>  MuteButton ]
```

- The `QListWidgetItem` size hint is set to ~52 px height to fit two text lines plus comfortable button sizing.
- The existing `RoundedBoxDelegate` is **not** used for these items; text rendering moves into `QLabel` widgets inside the item widget.
- Background alternation (`#232629` / `#2d2f31`) is applied to the container widget's stylesheet.

## Components

| Component | File | Change |
|---|---|---|
| `get_sink_inputs()` | `SoundSwitch.py` | Parse `Mute:` field; add `muted` key to stream dicts |
| `conditional_refresh()` snapshot | `SoundSwitch.py` | Add `s.get('muted')` to sink-inputs tuple |
| `toggle_stream_mute()` | `SoundSwitch.py` | New method; pactl call + force refresh |
| `MuteButton` | `SoundSwitch.py` | New class; drawn speaker icon, click → toggle |
| `refresh_devices_and_sinks()` sink loop | `SoundSwitch.py` | Switch to `setItemWidget` with inline mute button |

## Out of Scope

- Mute state in the left-hand "Application Streams" panel (unrouted streams) — not requested.
- Persisting mute state in `routing_state.json` — PipeWire already owns this.
- Volume slider or other per-stream controls.
