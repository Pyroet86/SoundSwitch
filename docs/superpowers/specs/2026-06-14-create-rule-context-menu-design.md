# Create Rule — Context Menu Action on Application Streams

**Date:** 2026-06-14
**Status:** Approved

## Overview

Right-clicking any item in the Application Streams list opens a context menu with a "Create Rule" action. Selecting it opens the Manage Auto-Routing Rules dialog with the app name pre-filled and "Game" pre-selected as the route-to sink. The user completes (or cancels) the rule creation themselves.

## Requirements

- Every stream item in the Application Streams list (`devices_list`) is right-clickable.
- The context menu always contains "Create Rule".
- If the stream has a manual override, the menu also contains "Reset to Default Behaviour" (existing behaviour, unchanged).
- "Create Rule" opens `RulesDialog` with the app name of the right-clicked stream pre-filled in the App name field and "Game" selected in the Route to dropdown.
- The user clicks Save or closes the dialog; no automatic saving occurs.
- Duplicate-rule validation in `RulesDialog` applies normally (existing behaviour).

## Architecture

### Approach chosen: Option A — constructor parameters on `RulesDialog`

Pre-fill logic lives inside `RulesDialog` where the widgets exist. `MainWindow` gets one focused helper method.

## Changes

### 1. Store app name on stream list items — `refresh_devices_and_sinks`

When populating `devices_list`, store the app name on each item:

```python
item.setData(Qt.UserRole + 2, stream.get('app_name', ''))
```

`Qt.UserRole` = stream index, `Qt.UserRole+1` = display dict (existing), `Qt.UserRole+2` = app name (new). No existing code reads `UserRole+2`.

### 2. Update `show_stream_context_menu` on `MainWindow`

Remove the guard that suppresses the menu when no manual override exists. Always show a menu for valid items. "Create Rule" appears first; "Reset to Default Behaviour" follows conditionally.

```python
def show_stream_context_menu(self, pos):
    item = self.devices_list.itemAt(pos)
    if not item:
        return
    stream_index = item.data(Qt.ItemDataRole.UserRole)
    app_name = item.data(Qt.UserRole + 2)
    menu = QMenu(self)
    create_action = menu.addAction('Create Rule')
    create_action.triggered.connect(lambda: self.open_rules_dialog_for_app(app_name))
    if stream_index in self.state.get('manual_overrides', {}):
        reset_action = menu.addAction('Reset to Default Behaviour')
        reset_action.triggered.connect(lambda: self.reset_manual_override(stream_index))
    menu.exec_(self.devices_list.viewport().mapToGlobal(pos))
```

### 3. New helper `open_rules_dialog_for_app` on `MainWindow`

```python
def open_rules_dialog_for_app(self, app_name):
    RulesDialog(
        self.state,
        self.save_state,
        lambda: self.refresh_devices_and_sinks(force=True),
        prefill_app_name=app_name,
        parent=self,
    ).exec_()
```

### 4. Pre-fill support in `RulesDialog`

Constructor signature:

```python
def __init__(self, state, save_state_cb, refresh_rules_cb, prefill_app_name=None, parent=None):
```

At end of `__init__`, after `_init_ui()`:

```python
if prefill_app_name:
    self._new_rule()
    self._app_input.setText(prefill_app_name)
    self._sink_combo.setCurrentIndex(0)  # 'Game' is index 0 in CUSTOM_SINKS
```

`CUSTOM_SINKS = ['Game', 'Media', 'Chat', 'Aux']` — 'Game' is index 0.

## Data flow

1. User right-clicks a stream item in `devices_list`.
2. `show_stream_context_menu` reads `stream_index` (UserRole) and `app_name` (UserRole+2) from the item.
3. Menu is shown; user selects "Create Rule".
4. `open_rules_dialog_for_app(app_name)` constructs `RulesDialog` with `prefill_app_name=app_name`.
5. `RulesDialog.__init__` calls `_init_ui()` then applies the pre-fill: sets app name text and selects "Game".
6. Dialog opens. User edits fields and clicks Save (or closes).
7. If saved, existing `_save_rule` logic persists the rule, refreshes the rules list, and triggers `refresh_devices_and_sinks`.

## Error handling

- If `app_name` is empty (edge case: item has no app name in UserRole+2), the dialog opens normally with an empty app name field — existing validation in `_save_rule` will warn the user on save attempt.
- No changes to duplicate-rule detection; it applies as before.

## Files changed

- `SoundSwitch.py` only — single-file codebase.

## Out of scope

- No changes to how "Reset to Default Behaviour" works.
- No changes to any other context menu (input devices).
- No pre-fill for sink other than 'Game' (hardcoded per requirements).
