# Volume Hotkeys Design — SoundSwitch

**Date:** 2026-04-10  
**Status:** Approved

## Overview

Add per-sink volume control (up/down) to SoundSwitch, triggered by user-configurable global keyboard shortcuts. The app runs on KDE Plasma / Wayland, so hotkeys are registered via the XDG GlobalShortcuts portal over D-Bus.

---

## Architecture

Three new pieces are added to `SoundSwitch.py`:

### 1. Volume Control Backend

A `set_sink_volume(sink_name: str, delta: int)` method on `MainWindow` that calls:

```
pactl set-sink-volume <sink_name> +N%   (or -N%)
```

Uses the existing `run_pactl()` helper. `delta` is the signed step value (e.g. `+5` or `-5`). The step size is read from `self.state['volume_step']`.

### 2. GlobalShortcutsManager

A standalone class that owns the D-Bus connection to the XDG GlobalShortcuts portal.

**Portal coordinates:**
- Bus: session bus
- Service: `org.freedesktop.portal.Desktop`
- Object path: `/org/freedesktop/portal/desktop`
- Interface: `org.freedesktop.portal.GlobalShortcuts`

**Startup sequence:**
1. Connect to session D-Bus via `PyQt5.QtDBus.QDBusConnection.sessionBus()`
2. Call `CreateSession({})` — waits for the `Response` signal on the returned request handle to get the session handle
3. Call `BindShortcuts(session_handle, shortcuts, parent_window="", options={})` — passes all 8 shortcuts as an array of `(id, {description, preferred_trigger})` structs
4. Connect to the session object's `Activated(session_handle, shortcut_id, timestamp, options)` signal
5. On `Activated`: parse `shortcut_id` (e.g. `"Game_up"`) → call `mainwindow.set_sink_volume(sink, ±step)`

**Re-registration:** when the user applies changes in the settings dialog, call `BindShortcuts` again on the existing session with the full updated shortcut list.

**Error handling:** if the portal service is unavailable or returns an error, log a warning to the status bar (`"Global hotkeys unavailable: xdg-desktop-portal-kde not running"`) and continue without hotkey functionality. The rest of the app is unaffected.

**Implementation library:** `PyQt5.QtDBus` — already available as part of the PyQt5 dependency.

### 3. HotkeySettingsDialog

A `QDialog` subclass opened from **File → Hotkey Settings…**

**Layout:**
```
[ Sink    ] [ Volume Up        ] [ Volume Down      ]
[ Game    ] [ KeyCaptureEdit   ] [ KeyCaptureEdit   ]
[ Media   ] [ KeyCaptureEdit   ] [ KeyCaptureEdit   ]
[ Chat    ] [ KeyCaptureEdit   ] [ KeyCaptureEdit   ]
[ Aux     ] [ KeyCaptureEdit   ] [ KeyCaptureEdit   ]

Volume Step: [ QSpinBox 1–100 ] %

[ Apply ]  [ Reset to Defaults ]  [ Cancel ]
```

**KeyCaptureEdit** is a `QLineEdit` subclass:
- Displays the current key sequence as a string (e.g. `"Ctrl+Alt+1"`)
- On click/focus: shows `"Press keys…"`
- Captures the next `keyPressEvent`: ignores modifier-only presses; records the full combo (modifiers + key) as a Qt key sequence string
- Pressing Escape cancels and restores the previous value

**Apply:** saves updated hotkeys and step size to `routing_state.json`, then calls `GlobalShortcutsManager.rebind(hotkeys)`.

**Reset to Defaults:** restores the default hotkey map without saving — user must still click Apply.

---

## Data Model

Two new keys in `routing_state.json`:

```json
{
  "volume_step": 5,
  "hotkeys": {
    "Game_up":    "Ctrl+Alt+1",
    "Game_down":  "Ctrl+Alt+Shift+1",
    "Media_up":   "Ctrl+Alt+2",
    "Media_down": "Ctrl+Alt+Shift+2",
    "Chat_up":    "Ctrl+Alt+3",
    "Chat_down":  "Ctrl+Alt+Shift+3",
    "Aux_up":     "Ctrl+Alt+4",
    "Aux_down":   "Ctrl+Alt+Shift+4"
  }
}
```

**Loading:** if `volume_step` or `hotkeys` are absent from the loaded state, defaults are injected in `MainWindow.__init__` — consistent with how `rules` and `manual_overrides` are already handled.

**Key string format:** Qt key sequence strings (e.g. `"Ctrl+Alt+1"`). The portal's `preferred_trigger` field accepts the same format after lowercasing (e.g. `"ctrl+alt+1"`).

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Portal unavailable | Status bar warning; hotkeys disabled; app continues normally |
| `pactl` volume command fails | Status bar error (existing `run_pactl` error path) |
| Duplicate hotkey assigned | No validation — KDE will handle conflicts at the portal level |
| Portal session lost | On next `BindShortcuts` call, recreate session automatically |

---

## Out of Scope

- Hotkey functionality when the portal is not present (no `keyboard`/evdev fallback)
- Per-stream volume control (only per-sink)
- Visual volume level display in the main UI
