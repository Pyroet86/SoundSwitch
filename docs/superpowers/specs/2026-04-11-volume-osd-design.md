# Volume OSD Design

**Date:** 2026-04-11  
**Branch:** feature/global-keybindings  
**Status:** Approved

## Overview

Add a non-focus-stealing on-screen display (OSD) that appears whenever a global keyboard shortcut changes a virtual sink's volume. The OSD shows the sink name and new volume percentage, fades out after a configurable duration, and is positioned in one of six screen locations.

## Architecture

All implementation lives in `SoundSwitch.py`. Two new classes are added (`VolumeOSD`, `OSDSettingsDialog`), one new method (`get_sink_volume`), and minor updates to `set_sink_volume`, `MainWindow.__init__`, and the tray menu.

## Components

### `VolumeOSD(QWidget)`

A singleton widget constructed once in `MainWindow.__init__` and reused for every volume change event.

**Window flags:**
```python
Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
```
- `Qt.Tool` — no taskbar entry
- `Qt.FramelessWindowHint` — no title bar
- `Qt.WindowStaysOnTopHint` — always on top (visible over full-screen games/video)
- `Qt.WindowDoesNotAcceptFocus` — OS never transfers focus to this window

**Content:** A single `QLabel` displaying `"<SinkName>: <volume>%"`. Styled to match the app's dark theme:
- Background: `#1e1e2e`
- Text: white, 14px, bold
- Padding: 12px 20px
- Border-radius: 8px
- Minimum width: 180px

**Fade-out mechanism:**
- A `QTimer` fires after `osd_duration` seconds to start the fade animation
- A `QPropertyAnimation` on `windowOpacity` transitions from `1.0` → `0.0` over 400ms
- Calling `show_volume()` while already visible cancels the pending timer and restarts cleanly (no double-fades or stale timers)
- `finished` signal of the animation calls `hide()`

**Public interface:**
```python
def show_volume(self, sink_name: str, volume: int, position: str, duration: int) -> None
```

### Positioning

Positions are calculated at show-time using `QApplication.primaryScreen().geometry()`. A fixed 20px margin is applied from the screen edge.

| Position key    | x                              | y                            |
|-----------------|-------------------------------|------------------------------|
| `top-left`      | `margin`                      | `margin`                     |
| `top-center`    | `(screen_w - osd_w) / 2`     | `margin`                     |
| `top-right`     | `screen_w - osd_w - margin`   | `margin`                     |
| `bottom-left`   | `margin`                      | `screen_h - osd_h - margin`  |
| `bottom-center` | `(screen_w - osd_w) / 2`     | `screen_h - osd_h - margin`  |
| `bottom-right`  | `screen_w - osd_w - margin`   | `screen_h - osd_h - margin`  |

`move()` is called before `show()` to prevent flickering in the wrong position.

### `get_sink_volume(sink_name: str) -> int | None`

New method on `MainWindow`. Runs `pactl get-sink-volume <sink_name>` and parses the first `XX%` from the output. Returns an `int` (0–100) or `None` on parse failure. Does not raise.

### `set_sink_volume` update

After `pactl set-sink-volume` fires, calls `get_sink_volume()` and if successful passes the result to `self._osd.show_volume()`. If `get_sink_volume` returns `None`, the OSD is silently skipped.

### `OSDSettingsDialog(QDialog)`

A modal dialog with two controls:

| Control | Widget | Range / Options | Default |
|---------|--------|-----------------|---------|
| Position | `QComboBox` | Top Left, Top Center, Top Right, Bottom Left, Bottom Center, Bottom Right | Bottom Right |
| Display duration | `QSpinBox` | 1–5 s | 3 s |

On apply, writes to `MainWindow.state`:
- `osd_position`: one of `"top-left"`, `"top-center"`, `"top-right"`, `"bottom-left"`, `"bottom-center"`, `"bottom-right"`
- `osd_duration`: integer 1–5

State is then saved to `routing_state.json`. `VolumeOSD` reads these values from `state` at show-time, so changes take effect immediately.

## State Persistence

Two new keys in `routing_state.json`:

```json
{
  "osd_position": "bottom-right",
  "osd_duration": 3
}
```

Defaults are applied in `MainWindow._load_state()` alongside the existing `volume_step` and `shortcut_version` defaults.

## Tray Menu

A new **"OSD Settings…"** entry is added to the system tray context menu, adjacent to the existing **"Hotkey Settings…"** entry. Clicking it opens `OSDSettingsDialog`.

## Error Handling

- If `get_sink_volume` fails to parse output, the OSD is silently skipped — no crash, no visible error.
- If the primary screen cannot be determined, the OSD falls back to `(0, 0)` position.

## What Is Not In Scope

- Per-sink OSD customisation
- OSD on non-primary screens
- Animations other than opacity fade
- Showing OSD for drag-and-drop or non-shortcut volume changes
