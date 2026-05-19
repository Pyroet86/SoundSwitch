# Inline "Set as Default" Button for Output Devices

**Date:** 2026-05-19
**Status:** Approved

## Summary

Replace the standalone "Set as Default Output" button below the output devices list with a per-item inline button that appears only on non-default output devices. Remove the popup confirmation dialog.

## Changes

### Removals

- Remove `self.set_default_btn` (`QPushButton("Set as Default Output")`) from the outputs panel layout (currently lines 1043–1045 in `SoundSwitch.py`).
- Remove `self.outputs_delegate` assignment on `outputs_list` — the `RoundedBoxDelegate` is no longer set on the outputs list. The delegate class itself remains for other lists.
- Remove both `QMessageBox` calls from `set_default_sink()`:
  - The "No Selection" warning (no longer needed — sink name is passed directly).
  - The "Default Sink" confirmation popup (action executes silently).

### `set_default_sink()` refactor

Change signature from `set_default_sink(self)` to `set_default_sink(self, sink_name: str)`. Remove all list-selection reading. Logic stays the same: `run_pactl(['set-default-sink', sink_name])`, update `state['default_sink']`, call `setup_custom_sink_loopbacks()`, call `refresh_devices_and_sinks(force=True)`.

### Per-item output widget

In `refresh_ui()`, the outputs list rebuild replaces `QListWidgetItem` text-only items with widget-backed items:

For each non-hidden, non-rnnoise sink:

1. Create a `QListWidgetItem` with `setSizeHint(QSize(width, 40))`.
2. Create a `QWidget` with a `QHBoxLayout` (contents margins 8px left/right, 0 top/bottom; no spacing between children beyond that).
3. **Left:** `QLabel` with the sink name.
   - Default sink: bold, colour `#00bfff`.
   - Non-default: normal weight, colour `#f0f0f0`.
4. **Right:** `QPushButton("Set as default")` — added only for non-default sinks.
   - Connected to `lambda: self.set_default_sink(name)` where `name` is the sink name captured at build time.
   - Styled: small flat button, dark background, `#00bfff` border, white text.
5. Widget background via QSS: alternating `#232629` / `#2d2f31`. Default sink gets a left border accent `3px solid #00bfff`.
6. Call `outputs_list.setItemWidget(item, widget)`.

`outputs_list` has no item delegate set (remove the `setItemDelegate` call for it).

## Constraints

- The sink name captured in each button's lambda must be the internal PipeWire sink name, not the display label.
- The refresh cycle clears and rebuilds the list every tick (same as today), so widgets are recreated on each refresh — no stale state.
- `set_default_sink()` call sites: currently only `set_default_btn.clicked` — after refactor, only the per-item button lambdas call it.
