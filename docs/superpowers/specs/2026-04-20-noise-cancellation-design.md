# Noise Cancellation — Design Spec

**Date:** 2026-04-20
**Branch:** feature/input-devices-panel (extends phase 1)

## Overview

Allow users to apply RNNoise-based noise cancellation to a selected hardware microphone. The processed audio is exposed as a new PipeWire virtual source that any application (e.g. Discord) can select as its input device. State persists across SoundSwitch restarts.

## Prerequisites

Requires the `noise-suppression-for-voice` Arch package:
```
sudo pacman -S noise-suppression-for-voice
```
This provides `/usr/lib/ladspa/librnnoise_ladspa.so`.

## Section 1 — Package Detection

On context-menu open, SoundSwitch checks for `/usr/lib/ladspa/librnnoise_ladspa.so` (file-existence check, no subprocess).

- **Present:** context menu shows active NC options (see Section 3).
- **Absent:** context menu shows a disabled "Noise Cancellation (not installed)" item. Clicking it opens an info dialog:
  > *Install noise-suppression-for-voice:*
  > `sudo pacman -S noise-suppression-for-voice`

## Section 2 — PipeWire Module Management

Noise cancellation loads three pactl modules in sequence:

### Enable

```bash
# 1. Null sink — clean output container
pactl load-module module-null-sink \
  sink_name=rnnoise_out_{safe_mic_id}

# 2. LADSPA sink — applies RNNoise processing
pactl load-module module-ladspa-sink \
  sink_name=rnnoise_ladspa_{safe_mic_id} \
  sink_master=rnnoise_out_{safe_mic_id} \
  label=noise_suppressor_mono \
  plugin=/usr/lib/ladspa/librnnoise_ladspa.so \
  control={vad_threshold}

# 3. Loopback — feeds mic into LADSPA chain
pactl load-module module-loopback \
  source={mic_name} \
  sink=rnnoise_ladspa_{safe_mic_id}
```

Signal flow: **mic → loopback → LADSPA sink (RNNoise) → null sink → `rnnoise_out_{id}.monitor`**

The resulting virtual source `rnnoise_out_{safe_mic_id}.monitor` is what other apps select.

`{safe_mic_id}` is derived from the mic's raw PipeWire name with non-alphanumeric characters replaced by underscores, truncated to keep sink names reasonable.

### Disable

Unload all three module IDs in reverse order:
```bash
pactl unload-module {loopback_id}
pactl unload-module {ladspa_sink_id}
pactl unload-module {null_sink_id}
```

### Change Settings

Unload existing three modules (disable), then reload with new parameters (enable).

### Channel Mode

- `noise_suppressor_mono` — lower CPU, sufficient for voice
- `noise_suppressor_stereo` — higher CPU, for stereo sources

## Section 3 — Context Menu

Right-click on an item in the Input Devices list:

| NC state | Package present | Menu items |
|---|---|---|
| Not active | Yes | "Enable Noise Cancellation…" |
| Active | Yes | "Noise Cancellation Settings…", "Disable Noise Cancellation" |
| Any | No | "Noise Cancellation (not installed)" (disabled) |

## Section 4 — NoiseCancelDialog (QDialog)

Opens when "Enable Noise Cancellation…" or "Noise Cancellation Settings…" is selected.

**Controls:**
- **VAD Threshold** — QSlider + QSpinBox, range 0–100, default 50. Label: *"Lower = more aggressive noise suppression"*
- **Channel Mode** — QComboBox: ["Mono", "Stereo"], default Mono
- **Virtual source name** — read-only QLineEdit showing `rnnoise_out_{safe_mic_id}.monitor` (the name to select in Discord etc.)
- **Apply** button — loads/reloads modules with current settings, saves state
- **Cancel** button — closes without changes

If NC is already active for this mic, the dialog opens pre-populated with current settings.

## Section 5 — UI Indicators

In `refresh_devices_and_sinks()`, for each mic with active noise cancellation:

1. **Parent item** — description text gets `[NC]` appended in cyan (`#00bfff`), e.g. `Webcam C270 Mono [NC]`
2. **Sub-item** — non-selectable, indented, grey italic: `  ↳ rnnoise_out_webcam_c270.monitor`

Right-clicking the parent item (when NC active) shows the Settings/Disable menu (Section 3).

## Section 6 — State Persistence

Stored in `routing_state.json` under `noise_cancel`:

```json
{
  "noise_cancel": {
    "alsa_input.usb-046d_0825-00.mono-fallback": {
      "modules": [null_sink_id, ladspa_sink_id, loopback_id],
      "settings": { "vad_threshold": 50, "channel_mode": "mono" },
      "virtual_source": "rnnoise_out_alsa_input_usb_046d_0825.monitor"
    }
  }
}
```

### Restore on Startup

`restore_routing_state()` iterates `noise_cancel` entries:
- Checks if the mic name still exists in the current source list
- If yes: re-loads the three modules, updates stored module IDs in state
- If no: removes the entry from state and saves

## Out of Scope

- Volume control for the noise-cancelled virtual source
- Supporting non-Arch Linux package managers (pacman assumed)
- Multiple simultaneous noise cancellation profiles per mic
- Automatic detection of RNNoise threshold (manual slider only)
