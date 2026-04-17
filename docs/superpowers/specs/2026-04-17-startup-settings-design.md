# Startup Settings Feature Design

**Date:** 2026-04-17

## Overview

Add an autostart-on-login feature to SoundSwitch, controlled via a new Settings dialog. The XDG autostart mechanism (`.desktop` file) is used. All autostart file I/O is isolated in a new `autostart.py` module; the Settings dialog lives in `SoundSwitch.py` alongside the existing `OSDSettingsDialog`.

## `autostart.py` Module

Located at the project root. Three public functions:

- `is_enabled() -> bool` — returns `True` if `~/.config/autostart/soundswitch.desktop` exists
- `enable(start_minimized: bool)` — writes the `.desktop` file; uses `sys.executable` for the interpreter path and resolves `SoundSwitch.py` relative to `autostart.py`'s own location; appends `--minimized` to `Exec` when `start_minimized=True`
- `disable()` — removes the `.desktop` file if it exists

The `.desktop` file format:

```ini
[Desktop Entry]
Type=Application
Name=SoundSwitch
Exec=/path/to/python /path/to/SoundSwitch.py [--minimized]
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
```

No other public API. The module has no Qt dependency.

## `SettingsDialog` Class

Added to `SoundSwitch.py` alongside `OSDSettingsDialog`. Two checkboxes:

1. **"Start SoundSwitch on login"** — toggles autostart; calls `autostart.enable()` or `autostart.disable()` immediately on state change
2. **"Start minimized to tray"** — checked by default; only enabled when autostart is on; calls `autostart.enable(start_minimized)` on state change to rewrite the `.desktop` file

On open: reads `autostart.is_enabled()` to set checkbox 1; reads whether `--minimized` is present in the existing `.desktop` `Exec` line to set checkbox 2 (defaults to checked if no file exists).

Single **Close** button. Changes apply immediately — no Apply/Cancel.

## Menu Integration

`SettingsDialog` is opened from two places:

- **Tray menu** — new "Settings..." action, inserted above the existing "OSD Settings..." entry
- **File menu** — new "Settings..." action, inserted above the existing "OSD Settings..." entry

## Data Flow

```
SettingsDialog
  ├── on autostart toggle → autostart.enable(start_minimized) / autostart.disable()
  └── on minimized toggle → autostart.enable(start_minimized=<new value>)

autostart.py
  ├── enable()  → writes ~/.config/autostart/soundswitch.desktop
  └── disable() → removes ~/.config/autostart/soundswitch.desktop
```

The `.desktop` file is the sole source of truth — no changes to `routing_state.json`.

## Files Changed

| File | Change |
|---|---|
| `autostart.py` | New file — XDG autostart logic |
| `SoundSwitch.py` | Add `import autostart`, add `SettingsDialog`, wire tray + File menu |

## Branch

`feature/startup-settings`
