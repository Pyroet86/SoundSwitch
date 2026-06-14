# Create Rule Context Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Also required before any code change:** Invoke the `feature-branch-workflow` skill (per CLAUDE.md).

**Goal:** Add a "Create Rule" right-click action to the Application Streams list that opens the Manage Auto-Routing Rules dialog pre-filled with the stream's app name and "Game" as the default sink.

**Architecture:** Four targeted edits to `SoundSwitch.py` only — store app name on stream list items at population time; add optional pre-fill parameters to `RulesDialog`; add a helper method on `MainWindow`; refactor the existing context menu handler to always show and include "Create Rule". No new files.

**Tech Stack:** Python 3, PyQt5. No test suite — verification is manual by running the app (`source .venv/bin/activate && python3 SoundSwitch.py`).

---

## File Map

| File | Change |
|---|---|
| `SoundSwitch.py:1661–1676` | Store `app_name` in `Qt.UserRole + 2` on each stream item |
| `SoundSwitch.py:553–562` | Add `prefill_app_name=None` param to `RulesDialog.__init__` |
| `SoundSwitch.py:617` | Apply pre-fill after `_init_ui()` in `RulesDialog.__init__` |
| `SoundSwitch.py:1946–1952` | Add `open_rules_dialog_for_app` method on `MainWindow` |
| `SoundSwitch.py:1571–1580` | Refactor `show_stream_context_menu` to always show menu with "Create Rule" |

---

### Task 1: Store app name on each stream list item

**Files:**
- Modify: `SoundSwitch.py:1661–1676`

This enables the context menu to read the app name without re-querying PipeWire.

- [ ] **Step 1: Locate the item-population block in `refresh_devices_and_sinks`**

Find the loop that populates `devices_list` starting around line 1661:

```python
for i, stream in enumerate([s for s in sink_inputs
                             if s['index'] not in self.hidden_streams
                             and not s.get('sink_name', '').startswith('rnnoise_')]):
    main_label = f"{stream.get('app_name', 'Unknown App')} (#{stream['index']}) - {stream.get('sink_name', 'Unknown')}"
    sub_label = stream.get('media_name', '')
    item = QListWidgetItem()
    item.setData(Qt.DisplayRole, main_label)
    item.setData(Qt.UserRole + 1, {'main': main_label, 'sub': sub_label})
    item.setData(Qt.ItemDataRole.UserRole, stream['index'])
    item.setToolTip(...)
```

- [ ] **Step 2: Add `UserRole + 2` data after the existing `setData` calls**

Add one line immediately after `item.setData(Qt.ItemDataRole.UserRole, stream['index'])`:

```python
    item.setData(Qt.UserRole + 2, stream.get('app_name', ''))
```

The block should now read:

```python
    item = QListWidgetItem()
    item.setData(Qt.DisplayRole, main_label)
    item.setData(Qt.UserRole + 1, {'main': main_label, 'sub': sub_label})
    item.setData(Qt.ItemDataRole.UserRole, stream['index'])
    item.setData(Qt.UserRole + 2, stream.get('app_name', ''))
    item.setToolTip(f"App: {stream.get('app_name', 'Unknown App')}\nSink: {stream.get('sink_name', 'Unknown')}\nMedia: {stream.get('media_name', '')}")
```

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: store app name on stream list items for context menu"
```

---

### Task 2: Add pre-fill support to `RulesDialog`

**Files:**
- Modify: `SoundSwitch.py:553–562` (constructor signature)
- Modify: `SoundSwitch.py:617` (end of `__init__`, after `_init_ui()`)

- [ ] **Step 1: Update the constructor signature**

Find line 554:

```python
    def __init__(self, state, save_state_cb, refresh_rules_cb, parent=None):
```

Replace with:

```python
    def __init__(self, state, save_state_cb, refresh_rules_cb, prefill_app_name=None, parent=None):
```

Also store the parameter on the instance before `_init_ui()` is called:

```python
    def __init__(self, state, save_state_cb, refresh_rules_cb, prefill_app_name=None, parent=None):
        super().__init__(parent)
        self.state = state
        self._save_state_cb = save_state_cb
        self._refresh_rules_cb = refresh_rules_cb
        self.setWindowTitle('Manage Auto-Routing Rules')
        self.setModal(True)
        self.setMinimumWidth(500)
        self._init_ui()
        if prefill_app_name:
            self._new_rule()
            self._app_input.setText(prefill_app_name)
            self._sink_combo.setCurrentIndex(0)  # CUSTOM_SINKS[0] == 'Game'
```

The `_new_rule()` call is required: it clears any current list selection and puts the dialog in "new rule" mode. Without it the dialog would be in an ambiguous edit state. `_init_ui()` already calls `_refresh_list()` at the end, so the rules list is populated before pre-fill runs.

- [ ] **Step 2: Verify `CUSTOM_SINKS[0]` is 'Game'**

Check line 29:

```python
CUSTOM_SINKS = ['Game', 'Media', 'Chat', 'Aux']
```

Index 0 is 'Game'. No change needed here — just confirm.

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add prefill_app_name param to RulesDialog"
```

---

### Task 3: Add `open_rules_dialog_for_app` helper on `MainWindow`

**Files:**
- Modify: `SoundSwitch.py` — add method after `open_rules_dialog` (~line 1952)

- [ ] **Step 1: Locate `open_rules_dialog`**

Find the existing method (~line 1946):

```python
    def open_rules_dialog(self):
        RulesDialog(
            self.state,
            self.save_state,
            lambda: self.refresh_devices_and_sinks(force=True),
            parent=self,
        ).exec_()
```

- [ ] **Step 2: Add `open_rules_dialog_for_app` immediately after it**

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

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add open_rules_dialog_for_app helper on MainWindow"
```

---

### Task 4: Refactor `show_stream_context_menu` to always show "Create Rule"

**Files:**
- Modify: `SoundSwitch.py:1571–1580`

- [ ] **Step 1: Locate `show_stream_context_menu`**

Find the current implementation (~line 1571):

```python
    def show_stream_context_menu(self, pos):
        item = self.devices_list.itemAt(pos)
        if not item:
            return
        stream_index = item.data(Qt.ItemDataRole.UserRole)
        if stream_index in self.state.get('manual_overrides', {}):
            menu = QMenu(self)
            action = menu.addAction('Reset to Default Behaviour')
            action.triggered.connect(lambda: self.reset_manual_override(stream_index))
            menu.exec_(self.devices_list.viewport().mapToGlobal(pos))
```

- [ ] **Step 2: Replace it with the new implementation**

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

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add Create Rule context menu action on application streams"
```

---

### Task 5: Manual end-to-end verification

**Files:** None — verification only.

- [ ] **Step 1: Start the application**

```bash
source .venv/bin/activate
python3 SoundSwitch.py
```

Expected: app launches, "Application Streams" panel visible on the left.

- [ ] **Step 2: Verify "Create Rule" appears on any stream**

Right-click any item in the "Application Streams" list.

Expected: context menu with "Create Rule" as the only item (if no manual override on that stream).

- [ ] **Step 3: Verify "Create Rule" pre-fills correctly**

Click "Create Rule" on a stream (e.g., Firefox).

Expected:
- The Manage Auto-Routing Rules dialog opens.
- The App name field contains "Firefox" (or whatever app you right-clicked).
- The Route to dropdown shows "Game".
- No rule is selected in the rules list (dialog is in new-rule mode).

- [ ] **Step 4: Verify Save works**

Click Save in the pre-filled dialog.

Expected:
- The new rule appears in the rules list in the dialog.
- The rules panel in the main window updates to show the new rule.
- Closing the dialog and re-opening "Manage Rules…" shows the saved rule.

- [ ] **Step 5: Verify duplicate detection still works**

Right-click the same app and choose "Create Rule" again.

Expected: clicking Save shows "A rule for '...' already exists." warning.

- [ ] **Step 6: Verify "Reset to Default Behaviour" still works**

Drag a stream to a different sink (creating a manual override), then right-click it.

Expected: context menu shows both "Create Rule" and "Reset to Default Behaviour".

- [ ] **Step 7: Verify closing without saving does nothing**

Right-click any stream → "Create Rule" → close the dialog with the X or press Escape.

Expected: no new rule is created.
