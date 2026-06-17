# Sink Header Volume Control Design

**Date:** 2026-06-17  
**Status:** Approved  
**Depends on:** `2026-06-17-stream-volume-slider-design.md` (SnapSlider and MuteButton already implemented)

## Overview

Add an always-visible volume slider and mute button to the header row of each of the four custom sink panes (Game / Media / Chat / Aux) in the centre panel. The slider provides direct 0–150% volume control as an alternative to the existing keyboard shortcuts. The mute button mirrors the stream-item mute already implemented.

## UI Layer

### Header row layout

The current header is a single centred `QLabel` per sink. It is replaced by a `QHBoxLayout` row widget containing:

```
[ sink name label (left-aligned, bold, coloured, stretch=1) ][ SnapSlider 100px ][ MuteButton 28×28 ]
```

- **Sink name label:** same 11pt bold font and per-sink colour from `SINK_COLORS`, left-aligned (`Qt.AlignLeft | Qt.AlignVCenter`), `stretch=1`.
- **`SnapSlider`:** reused unchanged — range 0–150, snap zone 5 around 100, `%` overlay while dragging. Fixed width 100px (wider than the 80px stream-item slider since it is always visible and the header has more horizontal room). Background transparent.
- **`MuteButton`:** reused unchanged — 28×28, speaker icon, red cross when muted.

The header row widget replaces the bare `QLabel` in the existing `pane_layout` (`QVBoxLayout`) for each sink pane. No other structural changes to the pane.

### Slider styling

Same QSS as stream-item sliders: `#3a3a3a` groove (4px, rounded), `#4a9eff` handle (12px pill, `margin: -4px 0`). Background set to transparent so the pane background shows through.

## Data Layer

### Parsing sink mute state

`get_sinks()` is extended to parse the `Mute:` line from `pactl list sinks` output, adding `sink['muted']: bool` to each sink dict — same pattern as `get_sink_inputs()` already does for streams.

### Reading sink volume

The existing `get_sink_volume(sink_name) -> int | None` is used at header construction time to initialise the slider value. It calls `pactl get-sink-volume` and parses the first `%` value; already supports values above 100.

### Writing sink volume (absolute)

A new `set_sink_volume_abs(sink_name: str, percent: int)` method on `MainWindow`:

```python
def set_sink_volume_abs(self, sink_name, percent):
    self.run_pactl(['set-sink-volume', sink_name, f'{percent}%'])
    self._osd.show_volume(
        sink_name,
        percent,
        self.state.get('osd_position', 'bottom-right'),
        self.state.get('osd_duration', 3),
    )
```

The slider's `valueChanged` signal is connected to this method. The existing `set_sink_volume(name, direction)` (step-relative, used by keyboard shortcuts) is unchanged.

### Writing sink mute

A new `toggle_sink_mute(sink_name: str)` method on `MainWindow`:

```python
def toggle_sink_mute(self, sink_name):
    self.run_pactl(['set-sink-mute', sink_name, 'toggle'])
    self.refresh_devices_and_sinks(force=True)
```

### Snapshot and refresh

Sink volume and mute are **excluded** from the snapshot tuple. This prevents the slider from being torn down and rebuilt mid-drag.

After a keyboard shortcut, `set_sink_volume()` already calls `refresh_devices_and_sinks(force=True)`, which rebuilds the header widget with the updated volume — so the slider reflects shortcut-driven changes on the next force refresh.

After `toggle_sink_mute()`, the force refresh updates the `MuteButton` icon immediately.

## Components

| Component | File | Change |
|---|---|---|
| `get_sinks()` | `SoundSwitch.py` | Parse `Mute:` field; add `muted` key to sink dicts |
| `set_sink_volume_abs()` | `SoundSwitch.py` | New method; absolute pactl call + OSD |
| `toggle_sink_mute()` | `SoundSwitch.py` | New method; pactl toggle + force refresh |
| Sink pane header (init loop) | `SoundSwitch.py` | Replace `QLabel` with `QHBoxLayout` row using `SnapSlider` + `MuteButton` |

## Out of Scope

- Changing keyboard shortcut behaviour — existing step-relative shortcuts are unchanged.
- Per-sink volume persistence — PipeWire holds sink volume state natively.
- Volume slider for the hardware output sinks in the right-hand Outputs panel.
