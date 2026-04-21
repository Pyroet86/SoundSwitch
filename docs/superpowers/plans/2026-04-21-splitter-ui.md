# Splitter UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all fixed-proportion layouts in `init_ui` with nested `QSplitter` widgets so every panel is user-resizable, and persist window geometry plus all splitter positions in `routing_state.json`.

**Architecture:** A root `QSplitter(Horizontal)` holds three children: `_splitter_left` (vertical, streams/rules), `center_widget` wrapping `_splitter_center` (vertical, 4 sinks), and `_splitter_right` (the existing vertical splitter for outputs/inputs). Layout state is saved in `real_close()` and restored at the end of `init_ui()` and after `init_ui()` returns in `__init__`.

**Tech Stack:** PyQt5 — `QSplitter`, `QWidget`, `QVBoxLayout`. No new imports needed; `QSplitter` is already imported.

---

### Task 1: Create the feature branch

**Files:**
- No file changes — git only

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout -b feature/splitter-ui
```

Expected: `Switched to a new branch 'feature/splitter-ui'`

---

### Task 2: Rebuild the left panel as `_splitter_left`

Replace the flat `devices_panel` QVBoxLayout (which held both the streams list and the rules editor) with a `QSplitter(Vertical)` holding two separate `QWidget` panes.

**Files:**
- Modify: `SoundSwitch.py` — `init_ui()`, lines 901–948

- [ ] **Step 1: Replace the left panel block in `init_ui`**

Find this entire block in `init_ui` (from `# Devices panel` through `devices_panel.addSpacing(10)` at line ~948) and replace it with:

```python
        # Left panel: vertical splitter — streams (top) / rules (bottom)
        self._splitter_left = QSplitter(Qt.Vertical)
        self._splitter_left.setStyleSheet('QSplitter::handle { background: #444; height: 4px; }')

        streams_widget = QWidget()
        streams_layout = QVBoxLayout(streams_widget)
        streams_layout.setContentsMargins(0, 0, 0, 0)
        devices_label = QLabel('Application Streams')
        devices_label.setFont(QFont('', 12, QFont.Bold))
        devices_label.setStyleSheet('margin-bottom: 8px;')
        self.devices_list = DraggableListWidget()
        self.devices_list.setItemDelegate(RoundedBoxDelegate())
        self.devices_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.devices_list.customContextMenuRequested.connect(self.show_stream_context_menu)
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.clicked.connect(lambda: self.refresh_devices_and_sinks(force=True))
        streams_layout.addWidget(devices_label)
        streams_layout.addWidget(self.devices_list)
        streams_layout.addWidget(self.refresh_btn)

        rules_widget = QWidget()
        rules_layout = QVBoxLayout(rules_widget)
        rules_layout.setContentsMargins(0, 0, 0, 0)
        rules_label = QLabel('Auto-Routing Rules')
        rules_label.setFont(QFont('', 11, QFont.Bold))
        rules_label.setStyleSheet('margin-bottom: 4px;')
        self.rules_list = QListWidget()
        self.rules_list.setAlternatingRowColors(True)
        self.rules_list.setSelectionMode(QListWidget.SingleSelection)
        self.rules_list.setStyleSheet('QListWidget { padding: 4px; }')
        rule_controls = QHBoxLayout()
        self.rule_app_input = QLineEdit()
        self.rule_app_input.setPlaceholderText('App name (e.g. Firefox)')
        self.rule_sink_combo = QComboBox()
        self.rule_sink_combo.addItems(CUSTOM_SINKS)
        self.add_rule_btn = QPushButton('Add Rule')
        self.add_rule_btn.clicked.connect(self.add_rule_from_ui)
        self.remove_rule_btn = QPushButton('Remove Selected')
        self.remove_rule_btn.clicked.connect(self.remove_selected_rule)
        rule_controls.addWidget(self.rule_app_input)
        rule_controls.addWidget(self.rule_sink_combo)
        rule_controls.addWidget(self.add_rule_btn)
        rule_controls.addWidget(self.remove_rule_btn)
        rules_layout.addWidget(rules_label)
        rules_layout.addWidget(self.rules_list)
        rules_layout.addLayout(rule_controls)

        self._splitter_left.addWidget(streams_widget)
        self._splitter_left.addWidget(rules_widget)
```

- [ ] **Step 2: Commit**

```bash
git add SoundSwitch.py
git commit -m "refactor: convert left panel to vertical QSplitter"
```

---

### Task 3: Rebuild the center panel as `center_widget` + `_splitter_center`

Replace the flat `sinks_panel` QVBoxLayout with a `QWidget` (holding the "Audio Sinks" heading label) wrapping a `QSplitter(Vertical)` with one pane per sink. Remove the fixed-height constraints; add a minimum height of 80 px per pane.

**Files:**
- Modify: `SoundSwitch.py` — `init_ui()`, lines 950–979

- [ ] **Step 1: Replace the center panel block in `init_ui`**

Find the block from `# Sinks panel (now stacked vertically)` through `sinks_panel.addSpacing(0)` and replace it with:

```python
        # Center panel: heading + vertical splitter for 4 sinks
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        sinks_label = QLabel('Audio Sinks')
        sinks_label.setFont(QFont('', 12, QFont.Bold))
        sinks_label.setStyleSheet('margin-bottom: 4px;')
        center_layout.addWidget(sinks_label)

        self._splitter_center = QSplitter(Qt.Vertical)
        self._splitter_center.setStyleSheet('QSplitter::handle { background: #444; height: 4px; }')
        self.sink_lists = {}
        for sink in CUSTOM_SINKS:
            pane = QWidget()
            pane_layout = QVBoxLayout(pane)
            pane_layout.setSpacing(0)
            pane_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(sink)
            label.setAlignment(Qt.AlignCenter)
            label.setFont(QFont('', 11, QFont.Bold))
            label.setStyleSheet('margin: 0px; padding: 0px;')
            pane_layout.addWidget(label)
            sink_list = SinkDropListWidget(sink, self.move_sink_input)
            sink_list.setItemDelegate(RoundedBoxDelegate(padding=12))
            sink_list.setStyleSheet('QListWidget { margin: 0px; padding: 0px; border: none; }')
            sink_list.setMinimumHeight(80)
            sink_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            pane_layout.addWidget(sink_list)
            self.sink_lists[sink] = sink_list
            self._splitter_center.addWidget(pane)
        center_layout.addWidget(self._splitter_center)
```

- [ ] **Step 2: Commit**

```bash
git add SoundSwitch.py
git commit -m "refactor: convert center panel to vertical QSplitter with 4 sink panes"
```

---

### Task 4: Replace root layout with `_splitter_main`, wire in `_splitter_right`

Remove the `main_widget` / `main_layout` setup at the top of `init_ui`. Rename the local `right_splitter` to `self._splitter_right`. Replace the three `main_layout.addLayout/addWidget` calls at the bottom with a root `QSplitter(Horizontal)`.

**Files:**
- Modify: `SoundSwitch.py` — `init_ui()`, lines 901–1034

- [ ] **Step 1: Remove the `main_widget` / `main_layout` preamble**

Find and delete these four lines at the top of `init_ui`:

```python
        main_widget = QWidget()
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
```

- [ ] **Step 2: Rename `right_splitter` to `self._splitter_right` throughout `init_ui`**

In the right panel block (from `# Right panel` onward), change every occurrence of `right_splitter` to `self._splitter_right`. The affected lines are:

```python
        # Right panel — splitter with Output Devices (top) and Input Devices (bottom)
        self._splitter_right = QSplitter(Qt.Vertical)
        ...
        self._splitter_right.addWidget(outputs_widget)
        self._splitter_right.addWidget(inputs_widget)
        self._splitter_right.setStyleSheet(
            'QSplitter::handle { background: #444; height: 4px; }'
        )
```

Also **remove** the `self._splitter_right.setSizes([300, 300])` line — sizes will be restored from state in Task 6.

- [ ] **Step 3: Replace the bottom `main_layout` additions with `_splitter_main`**

Find and replace these lines at the end of `init_ui`:

```python
        # Add panels to main layout
        main_layout.addLayout(devices_panel, 2)
        main_layout.addSpacing(16)
        main_layout.addLayout(sinks_panel, 3)
        main_layout.addSpacing(16)
        main_layout.addWidget(right_splitter, 2)
```

With:

```python
        # Root horizontal splitter
        self._splitter_main = QSplitter(Qt.Horizontal)
        self._splitter_main.setStyleSheet('QSplitter::handle { background: #444; width: 4px; }')
        self._splitter_main.addWidget(self._splitter_left)
        self._splitter_main.addWidget(center_widget)
        self._splitter_main.addWidget(self._splitter_right)
        self.setCentralWidget(self._splitter_main)
```

- [ ] **Step 4: Run the app and verify the UI renders correctly**

```bash
source .venv/bin/activate && python3 SoundSwitch.py
```

Expected: window opens with three horizontally draggable columns; left column has two vertically splittable panes; center column has four individually splittable sink panes; right column retains its existing output/input splitter. All lists, buttons, drag-and-drop, and right-click menus work as before.

- [ ] **Step 5: Commit**

```bash
git add SoundSwitch.py
git commit -m "refactor: replace root layout with horizontal QSplitter"
```

---

### Task 5: Save layout state in `real_close()`

Capture window geometry and all four splitter sizes just before `save_state()` is called.

**Files:**
- Modify: `SoundSwitch.py` — `real_close()`, line ~1625

- [ ] **Step 1: Insert layout capture before `self.save_state()`**

Find `real_close()`:

```python
    def real_close(self):
        self._teardown_nc_modules()
        self.save_state()
```

Change it to:

```python
    def real_close(self):
        self._teardown_nc_modules()
        self.state['layout'] = {
            'window': {
                'x': self.x(), 'y': self.y(),
                'width': self.width(), 'height': self.height(),
            },
            'splitter_main':   list(self._splitter_main.sizes()),
            'splitter_left':   list(self._splitter_left.sizes()),
            'splitter_center': list(self._splitter_center.sizes()),
            'splitter_right':  list(self._splitter_right.sizes()),
        }
        self.save_state()
```

- [ ] **Step 2: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: save window geometry and splitter sizes on close"
```

---

### Task 6: Restore layout state on startup

Apply saved splitter sizes at the end of `init_ui()`, and restore window geometry in `__init__` immediately after `init_ui()` returns.

**Files:**
- Modify: `SoundSwitch.py` — end of `init_ui()` and `__init__()` line ~754

- [ ] **Step 1: Append splitter restore to the end of `init_ui()`**

Add these lines immediately after `self.setCentralWidget(self._splitter_main)` at the end of `init_ui`:

```python
        layout_state = self.state.get('layout', {})
        self._splitter_main.setSizes(layout_state.get('splitter_main', [280, 420, 280]))
        self._splitter_left.setSizes(layout_state.get('splitter_left', [300, 250]))
        self._splitter_center.setSizes(layout_state.get('splitter_center', [120, 120, 120, 120]))
        self._splitter_right.setSizes(layout_state.get('splitter_right', [300, 300]))
```

- [ ] **Step 2: Restore window geometry in `__init__` after `init_ui()`**

Find this line in `__init__`:

```python
        self.init_ui()
        self.ensure_custom_sinks()
```

Change it to:

```python
        self.init_ui()
        layout_state = self.state.get('layout', {})
        if 'window' in layout_state:
            w = layout_state['window']
            self.setGeometry(w['x'], w['y'], w['width'], w['height'])
        self.ensure_custom_sinks()
```

- [ ] **Step 3: Run the app, resize panels, close, reopen and verify positions are restored**

```bash
source .venv/bin/activate && python3 SoundSwitch.py
```

Expected:
- On first run (no saved layout): window opens at 1000×600, columns in roughly 2:3:2 proportions, panes equal height.
- Drag splitter handles to new positions, then close via File → Exit (not the X button, which hides to tray).
- Reopen: window restores to previous size/position and all splitter handles are at the saved positions.

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: restore window geometry and splitter positions on startup"
```
