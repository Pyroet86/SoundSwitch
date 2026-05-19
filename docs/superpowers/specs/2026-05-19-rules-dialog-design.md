# Rules Dialog Design

**Date:** 2026-05-19
**Status:** Approved

## Overview

Replace the inline rules editing controls in the main window's left panel with a read-only rules list and a single "Manage Rules…" button. All rule creation and editing moves into a dedicated `RulesDialog`.

---

## Section 1: Main UI Rules Panel

Three changes to the existing rules section in the left vertical splitter:

1. **Header alignment:** Add `setContentsMargins(0, 8, 0, 0)` to `rules_layout` so the "Auto-Routing Rules" label has a top margin matching the "Input Devices" panel. Change `margin-bottom` from `4px` to `8px` to match other headers.
2. **Header font size:** Change from `QFont('', 11, QFont.Bold)` to `QFont('', 12, QFont.Bold)`, matching "Application Streams", "Output Devices", "Input Devices", and "Audio Sinks".
3. **Controls:** Remove `rule_app_input` (QLineEdit), `rule_sink_combo` (QComboBox), `add_rule_btn`, and `remove_rule_btn`. Remove the `rule_controls` QHBoxLayout. Replace with a single `QPushButton('Manage Rules…')` below the rules list, connected to a new `open_rules_dialog()` method on `MainWindow`.

The rules list itself (`self.rules_list`) remains in the panel. It becomes purely read-only (no selection interaction needed from the main window).

---

## Section 2: `RulesDialog` Layout and Interaction

New class `RulesDialog(QDialog)`, modal, minimum width 500px, window title "Manage Auto-Routing Rules".

### Layout

```
┌─────────────────────────────────────────────────────┐
│  Rules                    │                         │
│  ┌─────────────────────┐  │  [New Rule]             │
│  │ If audio stream is  │  │                         │
│  │ Firefox route to Aux│  │  App name:              │
│  │ ...                 │  │  [________________]     │
│  │                     │  │                         │
│  │                     │  │  Route to:              │
│  │                     │  │  [Game ▾]               │
│  │                     │  │                         │
│  └─────────────────────┘  │  [Save]  [Delete]       │
│                           │                         │
├─────────────────────────────────────────────────────┤
│                                          [Close]    │
└─────────────────────────────────────────────────────┘
```

Left panel (~60% width): `QListWidget` of rules using `RuleItemDelegate`, labelled "Rules".

Right panel (~40% width): vertical form with:
- `QPushButton('New Rule')` — deselects list, clears form fields
- `QLabel('App name:')` + `QLineEdit` (placeholder: "App name e.g. Firefox")
- `QLabel('Route to:')` + `QComboBox` populated with `CUSTOM_SINKS`
- `QPushButton('Save')` — creates rule if form is in new-rule mode, updates selected rule if one is loaded
- `QPushButton('Delete')` — removes selected rule; disabled when no rule is selected
- `addStretch()` to push controls to the top

Bottom row: `QPushButton('Close')` right-aligned, calls `self.accept()`.

### Interaction Flow

- Dialog opens with existing rules displayed; form is blank (new-rule mode); Delete is disabled.
- Clicking a rule: loads `app_name` into the line edit and sets the combo to the rule's sink; enables Delete.
- "New Rule": deselects list, clears line edit, resets combo to first item, disables Delete.
- "Save": validates that app name is not empty; if a rule is selected, updates `state['rules'][row]`; otherwise appends a new entry. Calls `save_state_cb()`, `refresh_rules_cb()` (updates main window list), and the dialog's own internal `_refresh_list()` immediately.
- "Delete": removes `state['rules'][row]`, calls `save_state_cb()`, `refresh_rules_cb()`, and `_refresh_list()`, then clears the form.
- All state mutations happen immediately — no buffering.

### Constructor Signature

```python
RulesDialog(state, save_state_cb, refresh_rules_cb, parent=None)
```

`MainWindow.open_rules_dialog()` passes `self.state`, `self.save_state`, and `self.refresh_rules_list`.

---

## Section 3: `RuleItemDelegate`

New `RuleItemDelegate(QStyledItemDelegate)` used in both the main panel list and the dialog list.

Each `QListWidgetItem` stores `{'app_name': str, 'sink': str}` in `Qt.UserRole`.

The delegate's `paint()` draws four text segments in a single line using `QFontMetrics.horizontalAdvance()` to compute x-offsets:

| Segment | Weight | Color |
|---|---|---|
| `"If audio stream is "` | normal | `#f0f0f0` |
| `app_name` | bold | `#00bfff` |
| `" route to "` | normal | `#f0f0f0` |
| `sink_name` | bold | `#00bfff` |

The rounded background box style (colors, border, alternating rows) is taken from `RoundedBoxDelegate` — same `bg`/`border` logic, same `drawRoundedRect` call. `sizeHint` returns a fixed height of 36px (single-line items, no subtitle).

---

## Section 4: Data Flow

The dialog mutates `MainWindow.state['rules']` directly (passed by reference) and calls `save_state()` and `refresh_rules_list()` as callbacks on every Save and Delete. This is consistent with every other dialog in the app (`OSDSettingsDialog`, `SettingsDialog`, etc.).

`MainWindow.open_rules_dialog()`:
```python
def open_rules_dialog(self):
    RulesDialog(self.state, self.save_state, self.refresh_rules_list, parent=self).exec_()
```

No new state keys are needed. The existing `state['rules']` list format (`[{'app_name': str, 'sink': str}]`) is unchanged.

The `add_rule_from_ui()` and `remove_selected_rule()` methods on `MainWindow` become dead code once the inline controls are removed and should be deleted.

---

## Out of Scope

- Reordering rules via drag-and-drop in the dialog
- Rule conditions beyond app name (e.g. media name matching)
- Bulk import/export of rules
