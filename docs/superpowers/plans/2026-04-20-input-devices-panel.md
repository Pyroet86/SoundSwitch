# Input Devices Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Input Devices section to the right panel listing available hardware microphones, splitting the panel with a QSplitter.

**Architecture:** The right panel `outputs_panel` QVBoxLayout is replaced by a `QSplitter(Qt.Vertical)`. The splitter's top child holds the existing Output Devices widgets; its bottom child holds a new Input Devices label + list. A new `get_input_sources()` method parses `pactl list sources` long-form output, filters out monitor sources, and returns friendly descriptions for display.

**Tech Stack:** Python 3, PyQt5, pactl (PipeWire/PulseAudio CLI)

> **Note:** This codebase has no automated test suite (see CLAUDE.md). Each task uses manual verification via shell commands instead of unit tests.

---

### Task 1: Create feature branch

**Files:**
- No file changes — git only

- [ ] **Step 1: Create and switch to the feature branch**

```bash
git checkout -b feature/input-devices-panel
```

Expected output:
```
Switched to a new branch 'feature/input-devices-panel'
```

- [ ] **Step 2: Verify branch**

```bash
git branch --show-current
```

Expected: `feature/input-devices-panel`

---

### Task 2: Add `get_input_sources()` method

**Files:**
- Modify: `SoundSwitch.py` — replace the existing `get_sources()` stub (line ~918) with `get_input_sources()` that parses long-form `pactl list sources` output and filters monitors.

- [ ] **Step 1: Replace `get_sources()` with `get_input_sources()`**

Find this existing method in `SoundSwitch.py` (around line 918):

```python
def get_sources(self):
    # Returns a list of dicts with 'index', 'name', 'description'
    output = self.run_pactl(['list', 'short', 'sources'])
    sources = []
    for line in output.strip().split('\n'):
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) >= 2:
            sources.append({'index': parts[0], 'name': parts[1], 'description': parts[1]})
    return sources
```

Replace it with:

```python
def get_input_sources(self):
    output = self.run_pactl(['list', 'sources'])
    sources = []
    current = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith('Source #'):
            if current.get('name') and not current['name'].endswith('.monitor'):
                sources.append(current)
            current = {}
        elif line.startswith('Name:'):
            current['name'] = line.split(':', 1)[1].strip()
        elif line.startswith('device.description ='):
            current['description'] = line.split('=', 1)[1].strip().strip('"')
    if current.get('name') and not current['name'].endswith('.monitor'):
        sources.append(current)
    for s in sources:
        s.setdefault('description', s['name'])
    return sources
```

- [ ] **Step 2: Verify the method parses correctly**

Run in a terminal (with the venv active):

```bash
source .venv/bin/activate
python3 -c "
import subprocess, re

output = subprocess.run(['pactl', 'list', 'sources'], capture_output=True, text=True).stdout
sources = []
current = {}
for line in output.splitlines():
    line = line.strip()
    if line.startswith('Source #'):
        if current.get('name') and not current['name'].endswith('.monitor'):
            sources.append(current)
        current = {}
    elif line.startswith('Name:'):
        current['name'] = line.split(':', 1)[1].strip()
    elif line.startswith('device.description ='):
        current['description'] = line.split('=', 1)[1].strip().strip('\"')
if current.get('name') and not current['name'].endswith('.monitor'):
    sources.append(current)
for s in sources:
    s.setdefault('description', s['name'])
for s in sources:
    print(s)
"
```

Expected: one or more dicts printed, none with a `name` ending in `.monitor`. Example:
```
{'name': 'alsa_input.usb-...', 'description': 'USB Audio Microphone'}
```

If no real microphone is connected, expected output is an empty list `[]`.

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add get_input_sources() with monitor filtering"
```

---

### Task 3: Add Input Devices list widget in `init_ui()`

**Files:**
- Modify: `SoundSwitch.py` — `init_ui()` method, right panel section (around lines 876–899)
- Add `QSplitter` to imports

- [ ] **Step 1: Add QSplitter to the PyQt5 imports**

Find the existing imports block at the top of `SoundSwitch.py`:

```python
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QLabel, QPushButton, QListWidgetItem, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QLineEdit,
    QComboBox, QMenu, QSystemTrayIcon, QAction, QDialog,
    QSpinBox, QCheckBox,
)
```

Replace with:

```python
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QLabel, QPushButton, QListWidgetItem, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QLineEdit,
    QComboBox, QMenu, QSystemTrayIcon, QAction, QDialog,
    QSpinBox, QCheckBox, QSplitter,
)
```

- [ ] **Step 2: Replace the Outputs panel block with a splitter-based right panel**

Find the Outputs panel block in `init_ui()` and the final `main_layout.addLayout` call. The section currently looks like this (around lines 876–899):

```python
        # Outputs panel
        outputs_panel = QVBoxLayout()
        outputs_label = QLabel('Output Devices')
        outputs_label.setFont(QFont('', 12, QFont.Bold))
        outputs_label.setStyleSheet('margin-bottom: 8px;')
        self.outputs_list = QListWidget()
        self.outputs_list.setAlternatingRowColors(True)
        self.outputs_list.setSelectionMode(QListWidget.SingleSelection)
        self.outputs_list.setContentsMargins(0, 0, 0, 0)
        self.outputs_list.setStyleSheet('QListWidget { padding: 8px; }')
        self.outputs_delegate = RoundedBoxDelegate(highlight_selected=True, default_sink_name=self.get_default_sink_name())
        self.outputs_list.setItemDelegate(self.outputs_delegate)
        outputs_panel.addWidget(outputs_label)
        outputs_panel.addWidget(self.outputs_list)
        self.set_default_btn = QPushButton('Set as Default Output')
        self.set_default_btn.clicked.connect(self.set_default_sink)
        outputs_panel.addWidget(self.set_default_btn)
        outputs_panel.addSpacing(10)

        # Add panels to main layout
        main_layout.addLayout(devices_panel, 2)
        main_layout.addSpacing(16)
        main_layout.addLayout(sinks_panel, 3)
        main_layout.addSpacing(16)
        main_layout.addLayout(outputs_panel, 2)
```

Replace with:

```python
        # Right panel — splitter with Output Devices (top) and Input Devices (bottom)
        right_splitter = QSplitter(Qt.Vertical)

        # Output Devices widget
        outputs_widget = QWidget()
        outputs_panel = QVBoxLayout(outputs_widget)
        outputs_panel.setContentsMargins(0, 0, 0, 0)
        outputs_label = QLabel('Output Devices')
        outputs_label.setFont(QFont('', 12, QFont.Bold))
        outputs_label.setStyleSheet('margin-bottom: 8px;')
        self.outputs_list = QListWidget()
        self.outputs_list.setAlternatingRowColors(True)
        self.outputs_list.setSelectionMode(QListWidget.SingleSelection)
        self.outputs_list.setContentsMargins(0, 0, 0, 0)
        self.outputs_list.setStyleSheet('QListWidget { padding: 8px; }')
        self.outputs_delegate = RoundedBoxDelegate(highlight_selected=True, default_sink_name=self.get_default_sink_name())
        self.outputs_list.setItemDelegate(self.outputs_delegate)
        outputs_panel.addWidget(outputs_label)
        outputs_panel.addWidget(self.outputs_list)
        self.set_default_btn = QPushButton('Set as Default Output')
        self.set_default_btn.clicked.connect(self.set_default_sink)
        outputs_panel.addWidget(self.set_default_btn)

        # Input Devices widget
        inputs_widget = QWidget()
        inputs_panel = QVBoxLayout(inputs_widget)
        inputs_panel.setContentsMargins(0, 8, 0, 0)
        inputs_label = QLabel('Input Devices')
        inputs_label.setFont(QFont('', 12, QFont.Bold))
        inputs_label.setStyleSheet('margin-bottom: 8px;')
        self.inputs_list = QListWidget()
        self.inputs_list.setAlternatingRowColors(True)
        self.inputs_list.setSelectionMode(QListWidget.SingleSelection)
        self.inputs_list.setContentsMargins(0, 0, 0, 0)
        self.inputs_list.setStyleSheet('QListWidget { padding: 8px; }')
        self.inputs_list.setItemDelegate(RoundedBoxDelegate())
        inputs_panel.addWidget(inputs_label)
        inputs_panel.addWidget(self.inputs_list)

        right_splitter.addWidget(outputs_widget)
        right_splitter.addWidget(inputs_widget)
        right_splitter.setSizes([300, 300])

        # Add panels to main layout
        main_layout.addLayout(devices_panel, 2)
        main_layout.addSpacing(16)
        main_layout.addLayout(sinks_panel, 3)
        main_layout.addSpacing(16)
        main_layout.addWidget(right_splitter, 2)
```

- [ ] **Step 3: Verify the app launches without errors**

```bash
source .venv/bin/activate
python3 SoundSwitch.py
```

Expected: app opens, right panel shows "Output Devices" on top and "Input Devices" below with a draggable divider. Input Devices list is empty (will be populated in Task 4).

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: split right panel with QSplitter, add Input Devices widget"
```

---

### Task 4: Populate Input Devices list in `refresh_devices_and_sinks()`

**Files:**
- Modify: `SoundSwitch.py` — `refresh_devices_and_sinks()` method (around line 1115)

- [ ] **Step 1: Add inputs list refresh at the end of `refresh_devices_and_sinks()`**

Find this block near the end of `refresh_devices_and_sinks()` (just before the `# Refresh rules list` comment, around line 1200):

```python
        # Refresh rules list
        self.refresh_rules_list()
        
        # Update status bar
        self.update_status_bar()
```

Replace with:

```python
        # Input Devices panel
        self.inputs_list.clear()
        input_sources = self.get_input_sources()
        if input_sources:
            for i, source in enumerate(input_sources):
                item = QListWidgetItem(source['description'])
                item.setData(Qt.ItemDataRole.UserRole, source['name'])
                if i % 2 == 0:
                    item.setBackground(QBrush(QColor('#232629')))
                else:
                    item.setBackground(QBrush(QColor('#2d2f31')))
                self.inputs_list.addItem(item)
        else:
            placeholder = QListWidgetItem('(No microphones found)')
            placeholder.setFlags(Qt.NoItemFlags)
            placeholder.setForeground(QBrush(QColor('#555')))
            self.inputs_list.addItem(placeholder)

        # Refresh rules list
        self.refresh_rules_list()

        # Update status bar
        self.update_status_bar()
```

- [ ] **Step 2: Run the app and verify the Input Devices list populates**

```bash
source .venv/bin/activate
python3 SoundSwitch.py
```

Expected:
- If a microphone is connected: the Input Devices list shows its friendly description (e.g. "USB Audio Microphone"). No `.monitor` entries appear.
- If no microphone is connected: the list shows `(No microphones found)` in grey, non-selectable.

- [ ] **Step 3: Verify monitor sources are excluded**

In a separate terminal, confirm what sources exist on your system:

```bash
pactl list short sources
```

Any source name ending in `.monitor` must **not** appear in the app's Input Devices list.

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: populate Input Devices list from get_input_sources()"
```

---

### Task 5: Style the splitter handle

**Files:**
- Modify: `SoundSwitch.py` — `apply_dark_theme()` method (around line 718) or inline after splitter creation in `init_ui()`

- [ ] **Step 1: Style the splitter handle to match the dark theme**

In `init_ui()`, directly after the line `right_splitter.setSizes([300, 300])`, add:

```python
        right_splitter.setStyleSheet(
            'QSplitter::handle { background: #444; height: 4px; }'
        )
```

- [ ] **Step 2: Run the app and verify the divider is visible**

```bash
source .venv/bin/activate
python3 SoundSwitch.py
```

Expected: a thin dark-grey horizontal bar separates the two right-panel sections; it is draggable.

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "style: dark theme for right-panel splitter handle"
```
