# Design: Full-Window Splitter UI

**Date:** 2026-04-21
**Branch:** feature/splitter-ui

## Summary

Replace the fixed `QHBoxLayout` / `QVBoxLayout` structure in `init_ui` with nested `QSplitter` widgets so every panel in the application is individually resizable by the user. Persist window geometry and all splitter states in `routing_state.json` so the layout is restored on next startup.

## Layout Structure

`init_ui` builds one root `QSplitter(Horizontal)` as the central widget's direct child. It holds three `QWidget` children:

### Left widget
Contains a `QSplitter(Vertical)` with two panes:
- **Top pane** — "Application Streams" label + `DraggableListWidget` (devices_list) + Refresh button
- **Bottom pane** — "Auto-Routing Rules" label + rules list + rule input controls

### Center widget
Contains a `QSplitter(Vertical)` with four panes, one per custom sink (Game / Media / Chat / Aux). Each pane is a `QWidget` holding the sink label and its `SinkDropListWidget`. Fixed heights on sink lists are removed; a minimum height of 80 px is set so a pane can never collapse completely.

### Right widget
The existing `QSplitter(Vertical)` (Output Devices / Input Devices) is unchanged internally. It is plugged into the root horizontal splitter instead of the old `addWidget` call.

### Handle styling
All splitters share consistent handle styling:
```python
'QSplitter::handle { background: #444; }'
```
Vertical handles use `height: 4px`; the horizontal handle uses `width: 4px`.

## Layout Persistence

### Saved state shape (inside `routing_state.json`)
```json
"layout": {
  "window":          { "x": 100, "y": 80, "width": 1200, "height": 700 },
  "splitter_main":   [350, 450, 280],
  "splitter_left":   [300, 250],
  "splitter_center": [120, 120, 120, 120],
  "splitter_right":  [300, 300]
}
```

- `splitter_main` — pixel widths of left / center / right columns
- `splitter_left` — pixel heights of streams pane / rules pane
- `splitter_center` — pixel heights of Game / Media / Chat / Aux panes
- `splitter_right` — pixel heights of outputs pane / inputs pane

### Save
`real_close()` calls `splitter.sizes()` on each of the four splitters and `self.geometry()` for the window, then writes the result into `self.state['layout']` before calling `save_state()`.

### Restore
After `init_ui` builds the layout, it reads `self.state.get('layout', {})` and calls `setSizes()` on each splitter. Window geometry is restored in `MainWindow.__init__` via `setGeometry()` after `init_ui` returns. If `"layout"` is absent (first run or old state file), the following defaults are applied:
- Window: `1000 × 600`, centered by Qt
- `splitter_main`: proportional `[2, 3, 2]` of window width
- `splitter_left`, `splitter_center`, `splitter_right`: equal distribution

### Instance attributes
Four splitter references are stored on `self` for easy access:
- `self._splitter_main`
- `self._splitter_left`
- `self._splitter_center`
- `self._splitter_right`

## What Does Not Change

- All widget contents (lists, buttons, labels, delegates, context menus) are unchanged.
- `refresh_devices_and_sinks`, `conditional_refresh`, and all audio logic are untouched.
- The right panel splitter internal structure is untouched; only its placement in the outer layout changes.
- No new dependencies are introduced.
