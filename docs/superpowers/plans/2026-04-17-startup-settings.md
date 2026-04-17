# Startup Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an autostart-on-login feature controlled via a new Settings dialog, using XDG autostart (`.desktop` file).

**Architecture:** A new `autostart.py` module handles all `.desktop` file I/O with no Qt dependency. A `SettingsDialog` class is added to `SoundSwitch.py` alongside the existing `OSDSettingsDialog`. Both the tray menu and File menu get a "Settings…" entry to open the dialog.

**Tech Stack:** Python 3, PyQt5, XDG autostart spec (`~/.config/autostart/`)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `autostart.py` | Create | XDG `.desktop` file read/write/delete |
| `SoundSwitch.py` | Modify | Add `import autostart`, `SettingsDialog` class, menu wiring |

---

## Task 1: Create feature branch

- [ ] **Step 1: Create and switch to the feature branch**

```bash
git checkout -b feature/startup-settings
```

Expected output: `Switched to a new branch 'feature/startup-settings'`

---

## Task 2: Create `autostart.py`

**Files:**
- Create: `autostart.py`

The `.desktop` file path is `~/.config/autostart/soundswitch.desktop`.  
`Exec` line uses `sys.executable` (the current Python interpreter) and resolves `SoundSwitch.py` absolute path relative to `autostart.py`'s own `__file__`.

- [ ] **Step 1: Create `autostart.py`**

```python
import os
import sys

_DESKTOP_PATH = os.path.expanduser('~/.config/autostart/soundswitch.desktop')
_SOUNDSWITCH_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'SoundSwitch.py')

_DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Name=SoundSwitch
Exec={python} {script}{minimized}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""


def is_enabled() -> bool:
    return os.path.isfile(_DESKTOP_PATH)


def is_minimized() -> bool:
    if not is_enabled():
        return True
    with open(_DESKTOP_PATH) as f:
        for line in f:
            if line.startswith('Exec='):
                return '--minimized' in line
    return True


def enable(start_minimized: bool = True) -> None:
    os.makedirs(os.path.dirname(_DESKTOP_PATH), exist_ok=True)
    minimized_flag = ' --minimized' if start_minimized else ''
    content = _DESKTOP_TEMPLATE.format(
        python=sys.executable,
        script=_SOUNDSWITCH_PY,
        minimized=minimized_flag,
    )
    with open(_DESKTOP_PATH, 'w') as f:
        f.write(content)


def disable() -> None:
    if os.path.isfile(_DESKTOP_PATH):
        os.remove(_DESKTOP_PATH)
```

- [ ] **Step 2: Verify the file was created correctly**

```bash
python3 -c "import autostart; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Quick manual smoke test**

```bash
python3 -c "
import autostart
print('enabled before:', autostart.is_enabled())
autostart.enable(start_minimized=True)
print('enabled after:', autostart.is_enabled())
print('minimized:', autostart.is_minimized())
autostart.disable()
print('enabled after disable:', autostart.is_enabled())
"
```

Expected output:
```
enabled before: False
enabled after: True
minimized: True
enabled after disable: False
```

- [ ] **Step 4: Commit**

```bash
git add autostart.py
git commit -m "feat: add autostart.py XDG autostart module"
```

---

## Task 3: Add `SettingsDialog` to `SoundSwitch.py`

**Files:**
- Modify: `SoundSwitch.py` — insert after `OSDSettingsDialog` class (after line 356), before the `_QT_MOD_TO_XDG` dict (line 358)

The dialog has two checkboxes. Changes apply immediately (no Apply/Cancel). The "Start minimized" checkbox is disabled when autostart is off.

- [ ] **Step 1: Add `import autostart` at the top of `SoundSwitch.py`**

Add after line 7 (`import os`):

```python
import autostart
```

So the imports block becomes:
```python
import sys
import re
import threading
import uuid
import subprocess
import json
import os
import autostart
```

- [ ] **Step 2: Add `SettingsDialog` class after `OSDSettingsDialog` (after line 356)**

Insert between the end of `OSDSettingsDialog._apply` and the `_QT_MOD_TO_XDG` dict:

```python

class SettingsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.setModal(True)
        self.setMinimumWidth(300)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._autostart_cb = QCheckBox('Start SoundSwitch on login')
        self._autostart_cb.setChecked(autostart.is_enabled())
        layout.addWidget(self._autostart_cb)

        self._minimized_cb = QCheckBox('Start minimized to tray')
        self._minimized_cb.setChecked(autostart.is_minimized())
        self._minimized_cb.setEnabled(autostart.is_enabled())
        layout.addWidget(self._minimized_cb)

        self._autostart_cb.stateChanged.connect(self._on_autostart_changed)
        self._minimized_cb.stateChanged.connect(self._on_minimized_changed)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_autostart_changed(self, state):
        enabled = bool(state)
        self._minimized_cb.setEnabled(enabled)
        if enabled:
            autostart.enable(start_minimized=self._minimized_cb.isChecked())
        else:
            autostart.disable()

    def _on_minimized_changed(self, _state):
        if self._autostart_cb.isChecked():
            autostart.enable(start_minimized=self._minimized_cb.isChecked())
```

- [ ] **Step 3: Add `QCheckBox` to the PyQt5 imports**

The existing import on line 8-14 currently does not include `QCheckBox`. Add it:

```python
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QLabel, QPushButton, QListWidgetItem, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QLineEdit,
    QComboBox, QMenu, QSystemTrayIcon, QAction, QDialog,
    QSpinBox, QCheckBox,
)
```

- [ ] **Step 4: Verify the app still starts**

```bash
source .venv/bin/activate && python3 SoundSwitch.py &
sleep 2 && kill %1
```

Expected: no import errors or tracebacks.

- [ ] **Step 5: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add SettingsDialog with autostart toggle"
```

---

## Task 4: Wire Settings dialog into tray menu and File menu

**Files:**
- Modify: `SoundSwitch.py:656-668` (File menu — `init_menu_bar`)
- Modify: `SoundSwitch.py:1174-1198` (tray menu — `init_tray_icon`)
- Modify: `SoundSwitch.py:1302-1305` (add `open_settings` method after `open_osd_settings`)

- [ ] **Step 1: Add `open_settings` method to `MainWindow`**

Add after `open_osd_settings` (after line 1305):

```python
    def open_settings(self):
        SettingsDialog(parent=self).exec_()
```

- [ ] **Step 2: Wire into File menu (`init_menu_bar`)**

Replace the current `init_menu_bar` method (lines 656-668):

```python
    def init_menu_bar(self):
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)
        menubar.setStyleSheet('QMenuBar { background: #232629; color: #f0f0f0; } QMenuBar::item:selected { background: #005f87; } QMenu { background: #232629; color: #f0f0f0; } QMenu::item:selected { background: #005f87; }')
        file_menu = menubar.addMenu('File')
        settings_action = file_menu.addAction('Settings\u2026')
        settings_action.triggered.connect(self.open_settings)
        hotkey_action = file_menu.addAction('Hotkey Settings\u2026')
        hotkey_action.triggered.connect(self.open_hotkey_settings)
        osd_action = file_menu.addAction('OSD Settings\u2026')
        osd_action.triggered.connect(self.open_osd_settings)
        file_menu.addSeparator()
        exit_action = file_menu.addAction('Exit')
        exit_action.triggered.connect(self.real_close)
        self.setMenuBar(menubar)
```

- [ ] **Step 3: Wire into tray menu (`init_tray_icon`)**

Replace the `init_tray_icon` method (lines 1174-1198):

```python
    def init_tray_icon(self):
        icon = create_app_icon()
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_menu = QMenu()
        self.action_show = QAction('Show', self)
        self.action_show.triggered.connect(self.show_from_tray)
        self.action_hide = QAction('Hide', self)
        self.action_hide.triggered.connect(self.hide_to_tray)
        self.action_exit = QAction('Exit', self)
        self.action_exit.triggered.connect(self.real_close)
        self.tray_menu.addAction(self.action_show)
        self.tray_menu.addAction(self.action_hide)
        self.tray_menu.addSeparator()
        action_settings = QAction('Settings\u2026', self)
        action_settings.triggered.connect(self.open_settings)
        self.tray_menu.addAction(action_settings)
        action_hotkey = QAction('Hotkey Settings\u2026', self)
        action_hotkey.triggered.connect(self.open_hotkey_settings)
        self.tray_menu.addAction(action_hotkey)
        action_osd = QAction('OSD Settings\u2026', self)
        action_osd.triggered.connect(self.open_osd_settings)
        self.tray_menu.addAction(action_osd)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.action_exit)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.setToolTip('SoundSwitch - PipeWire Audio Router')
        self.tray_icon.show()
```

- [ ] **Step 4: Verify the app starts and menus show the new entry**

```bash
source .venv/bin/activate && python3 SoundSwitch.py
```

Open the File menu and right-click the tray icon. Confirm "Settings…" appears above "Hotkey Settings…" in both. Open the dialog, toggle autostart on, verify `~/.config/autostart/soundswitch.desktop` is created. Toggle it off, verify the file is removed.

- [ ] **Step 5: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: wire Settings dialog into tray and File menu"
```

---

## Task 5: Final verification

- [ ] **Step 1: Run the app with `--minimized` flag to confirm it still works**

```bash
source .venv/bin/activate && python3 SoundSwitch.py --minimized &
sleep 2 && kill %1
```

Expected: no errors; app starts in tray.

- [ ] **Step 2: Enable autostart via the Settings dialog and inspect the generated `.desktop` file**

```bash
cat ~/.config/autostart/soundswitch.desktop
```

Expected output should look like:
```ini
[Desktop Entry]
Type=Application
Name=SoundSwitch
Exec=/home/<user>/projects/soundSwitch-wip/.venv/bin/python3 /home/<user>/projects/soundSwitch-wip/SoundSwitch.py --minimized
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
```

- [ ] **Step 3: Clean up test `.desktop` file**

```bash
rm -f ~/.config/autostart/soundswitch.desktop
```
