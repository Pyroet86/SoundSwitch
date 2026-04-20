# Input Devices Panel — Design Spec

**Date:** 2026-04-20
**Branch:** feature/input-devices-panel

## Overview

Add an Input Devices section to the right panel of SoundSwitch, listing available hardware microphones. This is the first phase of microphone support; actions on a selected mic will be designed in a follow-up iteration.

## Layout

The right panel changes from a plain `QVBoxLayout` to a `QSplitter(Qt.Vertical)` containing two child widgets:

- **Top — Output Devices** (unchanged content: label + `outputs_list` + "Set as Default Output" button)
- **Bottom — Input Devices** (new: label + read-only `inputs_list`)

Default split is 50/50 (equal `setSizes`). The user can drag the divider at runtime. No split position is persisted.

## Data — `get_input_sources()`

A new method replaces the existing stub `get_sources()`:

- Calls `pactl list sources` (long-form output)
- Parses each source block for `Name:` and `device.description` property
- **Filters out** any source whose `Name:` ends with `.monitor`
- Returns `list[dict]` with keys `name` (raw PipeWire name) and `description` (friendly label, falls back to `name` if not present)

## UI — Input Devices list

- Widget: plain `QListWidget` named `self.inputs_list`; read-only (no drag, no drop)
- Item delegate: `RoundedBoxDelegate()` — same style as the outputs list
- Display text: `description` field from `get_input_sources()`
- Item `UserRole` data: raw `name` (stored for future use)
- Empty state: single disabled placeholder item `(No microphones found)`

## Refresh

`refresh_devices_and_sinks()` gains a call to repopulate `self.inputs_list` via `get_input_sources()`. The existing 2-second `QTimer` drives this automatically — no additional timer needed.

## Out of Scope

- Selecting a microphone and doing anything with it (future phase)
- Persisting the splitter position
- Volume display or control for input sources
