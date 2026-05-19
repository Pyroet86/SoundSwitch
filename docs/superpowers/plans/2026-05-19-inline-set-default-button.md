# Inline "Set as Default" Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the standalone "Set as Default Output" button with a per-item inline button that appears only on non-default output device list items, and remove all popup dialogs from the set-default flow.

**Architecture:** Three independent edits to `SoundSwitch.py`: (1) refactor `set_default_sink()` to accept a sink name argument and remove both QMessageBox calls; (2) strip the standalone button and delegate wiring from `__init__`; (3) replace the text-only item loop in `refresh_ui()` with a widget-per-item loop using `setItemWidget()`.

**Tech Stack:** Python 3, PyQt5

---

### Task 1: Refactor `set_default_sink()` — new signature, no popups

**Files:**
- Modify: `SoundSwitch.py:1200-1210`

- [ ] **Step 1: Replace the method body**

In `SoundSwitch.py`, replace lines 1200–1210:

```python
    def set_default_sink(self):
        selected = self.outputs_list.currentItem()
        if not selected:
            QMessageBox.warning(self, 'No Selection', 'Please select a sink to set as default.')
            return
        sink_name = selected.text().replace(' (default)', '').strip()
        self.run_pactl(['set-default-sink', sink_name])
        self.state['default_sink'] = sink_name
        self.setup_custom_sink_loopbacks(sink_name)
        self.refresh_devices_and_sinks(force=True)
        QMessageBox.information(self, 'Default Sink', f'Set {sink_name} as the default output device and routed custom sinks to it.')
```

with:

```python
    def set_default_sink(self, sink_name: str):
        self.run_pactl(['set-default-sink', sink_name])
        self.state['default_sink'] = sink_name
        self.setup_custom_sink_loopbacks(sink_name)
        self.refresh_devices_and_sinks(force=True)
```

- [ ] **Step 2: Launch app and verify the old standalone button still triggers the method**

```bash
source .venv/bin/activate && python3 SoundSwitch.py
```

Click "Set as Default Output" — it will now crash with a TypeError (missing `sink_name` argument). This is expected and confirms the old call site needs removing in Task 2. Close the app.

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "refactor: set_default_sink accepts sink_name arg, remove QMessageBox popups"
```

---

### Task 2: Remove standalone button and delegate wiring from `__init__`

**Files:**
- Modify: `SoundSwitch.py:1039-1045`

- [ ] **Step 1: Remove the delegate wiring (lines 1039–1040)**

In `SoundSwitch.py`, remove these two lines from `__init__`:

```python
        self.outputs_delegate = RoundedBoxDelegate(highlight_selected=True, default_sink_name=self.get_default_sink_name())
        self.outputs_list.setItemDelegate(self.outputs_delegate)
```

- [ ] **Step 2: Remove the standalone button (lines 1043–1045)**

In `SoundSwitch.py`, remove these three lines from `__init__`:

```python
        self.set_default_btn = QPushButton('Set as Default Output')
        self.set_default_btn.clicked.connect(self.set_default_sink)
        outputs_panel.addWidget(self.set_default_btn)
```

- [ ] **Step 3: Remove the stale delegate update in `refresh_ui()` (lines 1543–1544)**

In `SoundSwitch.py`, remove these two lines from `refresh_ui()`:

```python
        if hasattr(self, 'outputs_delegate'):
            self.outputs_delegate.default_sink_name = self.get_default_sink_name()
```

- [ ] **Step 4: Launch app and verify**

```bash
source .venv/bin/activate && python3 SoundSwitch.py
```

Expected:
- No "Set as Default Output" button visible below the outputs list.
- Output device items render with the default PyQt5 list styling (plain text, no rounded boxes — the delegate is gone).
- App does not crash on startup.

Close the app.

- [ ] **Step 5: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: remove standalone set-default button and outputs list delegate"
```

---

### Task 3: Replace text-only items with per-item widget items in `refresh_ui()`

**Files:**
- Modify: `SoundSwitch.py:1542-1560`

- [ ] **Step 1: Replace the outputs list rebuild loop**

In `SoundSwitch.py`, replace lines 1542–1560:

```python
        # Outputs panel: show all sinks (hardware and custom), highlight default, skip hidden sinks
        for i, sink in enumerate([s for s in sinks if s['name'] not in self.hidden_sinks and not s['name'].startswith('rnnoise_')]):
            name = sink['name']
            label = f"{name}"
            if name == self.get_default_sink_name():
                label += " (default)"
            item = QListWidgetItem(label)
            if name == self.get_default_sink_name():
                item.setFont(QFont('', 10, QFont.Bold))
                item.setForeground(QBrush(QColor('#00bfff')))
            item.setToolTip(f"Sink: {name}")
            # Dark alternating row colors
            if i % 2 == 0:
                item.setBackground(QBrush(QColor('#232629')))
            else:
                item.setBackground(QBrush(QColor('#2d2f31')))
            self.outputs_list.addItem(item)
```

with:

```python
        # Outputs panel: per-item widget with inline set-default button for non-default sinks
        default_sink = self.get_default_sink_name()
        visible_sinks = [s for s in sinks if s['name'] not in self.hidden_sinks and not s['name'].startswith('rnnoise_')]
        for i, sink in enumerate(visible_sinks):
            name = sink['name']
            is_default = (name == default_sink)
            bg = '#232629' if i % 2 == 0 else '#2d2f31'

            item = QListWidgetItem()
            item.setSizeHint(QtCore.QSize(0, 40))
            item.setToolTip(f"Sink: {name}")

            widget = QWidget()
            widget.setStyleSheet(f'background: {bg};')

            row = QHBoxLayout(widget)
            row.setContentsMargins(8, 0, 8, 0)
            row.setSpacing(8)

            lbl = QLabel(name)
            lbl.setStyleSheet(
                'color: #00bfff; font-weight: bold; background: transparent;'
                if is_default else
                'color: #f0f0f0; background: transparent;'
            )
            row.addWidget(lbl)
            row.addStretch()

            if not is_default:
                btn = QPushButton('Set as default')
                btn.setStyleSheet(
                    'QPushButton { background: #1e2a3a; color: #f0f0f0;'
                    ' border: 1px solid #00bfff; border-radius: 4px;'
                    ' padding: 2px 8px; font-size: 9pt; }'
                    'QPushButton:hover { background: #003366; }'
                    'QPushButton:pressed { background: #00bfff; color: #000; }'
                )
                btn.clicked.connect(lambda checked, n=name: self.set_default_sink(n))
                row.addWidget(btn)

            self.outputs_list.addItem(item)
            self.outputs_list.setItemWidget(item, widget)
```

- [ ] **Step 2: Launch app and verify**

```bash
source .venv/bin/activate && python3 SoundSwitch.py
```

Expected:
- Each output device row shows the sink name on the left.
- Non-default sinks show a small "Set as default" button on the right.
- The current default sink shows its name in bold cyan with no button.
- Clicking "Set as default" on any non-default sink switches the default immediately (no popup), the list refreshes within 2 seconds, and the clicked item loses its button while the old default gains one.
- No crashes or visual artifacts.

Close the app.

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: inline set-default button per output device list item"
```
