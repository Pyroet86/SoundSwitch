# Volume Hotkeys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-sink volume up/down control to SoundSwitch, triggered by user-configurable global keyboard shortcuts registered with the XDG GlobalShortcuts portal on KDE Plasma/Wayland.

**Architecture:** Three additions to `SoundSwitch.py`: a `GlobalShortcutsManager` class that owns the D-Bus session with the XDG GlobalShortcuts portal (runs a GLib main loop in a daemon thread for signal handling), a `HotkeySettingsDialog` with `KeyCaptureEdit` widgets for configuring bindings, and a `set_sink_volume()` method on `MainWindow` that calls `pactl set-sink-volume`. Hotkeys and step size are persisted in `routing_state.json`.

**Tech Stack:** PyQt5, dbus-python (`dbus`), python-gobject (`gi.repository.GLib`), pactl

> **Dependencies already available** — verified in `.venv`: `dbus` and `gi` import cleanly.

---

## File Structure

Only `SoundSwitch.py` is modified. New classes are inserted before `MainWindow` in this order:

| Class | Purpose |
|---|---|
| `KeyCaptureEdit` | `QLineEdit` subclass — captures a key combo on click |
| `HotkeySettingsDialog` | `QDialog` — 4×2 grid of `KeyCaptureEdit` + step spinbox |
| `GlobalShortcutsManager` | `QObject` — D-Bus portal session + signal dispatch |

New method on `MainWindow`:
- `set_sink_volume(sink_name, direction)` — calls `pactl set-sink-volume`
- `_on_shortcut_activated(shortcut_id)` — parses ID and calls `set_sink_volume`
- `open_hotkey_settings()` — opens `HotkeySettingsDialog`

---

### Task 1: Update imports and add state defaults

**Files:**
- Modify: `SoundSwitch.py` lines 1–10 (imports block)
- Modify: `SoundSwitch.py` `MainWindow.__init__` (state defaults)

- [ ] **Step 1: Replace the imports block**

Replace lines 1–10 of `SoundSwitch.py` (the existing `import sys` … `from PyQt5.QtGui import …` block) with:

```python
import sys
import threading
import uuid
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QLabel, QPushButton, QListWidgetItem, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QLineEdit,
    QComboBox, QMenu, QSystemTrayIcon, QAction, QDialog, QGridLayout,
    QSpinBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIcon, QColor, QBrush, QPalette, QKeySequence
import subprocess
import json
import os
from PyQt5 import QtCore, QtGui

try:
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
```

- [ ] **Step 2: Add state defaults in `MainWindow.__init__`**

In `__init__`, after the existing block:
```python
        if 'manual_overrides' not in self.state:
            self.state['manual_overrides'] = {}
```
add:
```python
        if 'volume_step' not in self.state:
            self.state['volume_step'] = 5
        if 'hotkeys' not in self.state:
            self.state['hotkeys'] = {
                'Game_up':    'Ctrl+Alt+1',
                'Game_down':  'Ctrl+Alt+Shift+1',
                'Media_up':   'Ctrl+Alt+2',
                'Media_down': 'Ctrl+Alt+Shift+2',
                'Chat_up':    'Ctrl+Alt+3',
                'Chat_down':  'Ctrl+Alt+Shift+3',
                'Aux_up':     'Ctrl+Alt+4',
                'Aux_down':   'Ctrl+Alt+Shift+4',
            }
```

- [ ] **Step 3: Verify the app still launches**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 -c "from SoundSwitch import MainWindow; print('Import OK')"
```

Expected output: `Import OK`

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add imports and state defaults for volume hotkeys"
```

---

### Task 2: Add `set_sink_volume` to MainWindow

**Files:**
- Modify: `SoundSwitch.py` — `MainWindow` class, after `move_sink_input`

- [ ] **Step 1: Add the method**

After the `move_sink_input` method (which ends with `self.refresh_devices_and_sinks(force=True)`), add:

```python
    def set_sink_volume(self, sink_name, direction):
        step = self.state.get('volume_step', 5)
        delta = f'+{step}%' if direction == 'up' else f'-{step}%'
        self.run_pactl(['set-sink-volume', sink_name, delta])
        self.show_status(f'{sink_name} volume {direction} ({delta})')
```

- [ ] **Step 2: Verify the pactl command works**

With the app running (so the Game sink exists), run:

```bash
pactl set-sink-volume Game +5% && echo "UP OK"
pactl set-sink-volume Game -5% && echo "DOWN OK"
pactl list sinks | grep -A3 "Name: Game" | grep Volume
```

Expected: `UP OK`, `DOWN OK`, and the Volume line shows a value that changed.

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add set_sink_volume method to MainWindow"
```

---

### Task 3: Add `KeyCaptureEdit` widget

**Files:**
- Modify: `SoundSwitch.py` — add class after `RoundedBoxDelegate`, before `MainWindow`

- [ ] **Step 1: Add the class**

Insert after the `RoundedBoxDelegate` class (after its `sizeHint` method) and before `class MainWindow`:

```python
class KeyCaptureEdit(QLineEdit):
    """QLineEdit that captures a key combination on click."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._capturing = False
        self._previous = ''
        self.setReadOnly(True)
        self.setPlaceholderText('Click to set hotkey')
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            'QLineEdit { background: #2d2f31; color: #f0f0f0; border: 1px solid #444; '
            'border-radius: 4px; padding: 4px 8px; }'
            'QLineEdit:focus { border-color: #00bfff; }'
        )

    def mousePressEvent(self, event):
        self._previous = self.text()
        self._capturing = True
        self.setText('Press keys\u2026')
        self.setFocus()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if not self._capturing:
            return
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt,
                   Qt.Key_Meta, Qt.Key_AltGr):
            return  # ignore modifier-only presses
        if key == Qt.Key_Escape:
            self.setText(self._previous)
            self._capturing = False
            return
        seq = QKeySequence(int(event.modifiers()) | key)
        self.setText(seq.toString())
        self._capturing = False

    def focusOutEvent(self, event):
        if self._capturing:
            self.setText(self._previous)
            self._capturing = False
        super().focusOutEvent(event)
```

- [ ] **Step 2: Smoke-test the widget**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate
python3 - <<'EOF'
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
from SoundSwitch import KeyCaptureEdit
app = QApplication(sys.argv)
w = QWidget()
layout = QVBoxLayout(w)
edit = KeyCaptureEdit()
edit.setText('Ctrl+Alt+1')
layout.addWidget(edit)
w.show()
sys.exit(app.exec_())
EOF
```

Expected: a window with one input field showing `Ctrl+Alt+1`. Click it → shows `Press keys…`. Press e.g. Ctrl+Alt+2 → shows `Ctrl+Alt+2`. Press Escape → reverts to `Ctrl+Alt+1`.

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add KeyCaptureEdit widget for in-app hotkey capture"
```

---

### Task 4: Add `HotkeySettingsDialog`

**Files:**
- Modify: `SoundSwitch.py` — add class after `KeyCaptureEdit`

- [ ] **Step 1: Add the class**

Insert immediately after `KeyCaptureEdit` and before `class MainWindow`:

```python
class HotkeySettingsDialog(QDialog):
    DEFAULT_HOTKEYS = {
        'Game_up':    'Ctrl+Alt+1',
        'Game_down':  'Ctrl+Alt+Shift+1',
        'Media_up':   'Ctrl+Alt+2',
        'Media_down': 'Ctrl+Alt+Shift+2',
        'Chat_up':    'Ctrl+Alt+3',
        'Chat_down':  'Ctrl+Alt+Shift+3',
        'Aux_up':     'Ctrl+Alt+4',
        'Aux_down':   'Ctrl+Alt+Shift+4',
    }

    def __init__(self, state, on_apply, parent=None):
        super().__init__(parent)
        self.state = state
        self.on_apply = on_apply
        self._captures = {}
        self.setWindowTitle('Hotkey Settings')
        self.setModal(True)
        self.setMinimumWidth(500)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        for col, text in enumerate(['Sink', 'Volume Up', 'Volume Down']):
            lbl = QLabel(text)
            lbl.setFont(QFont('', 10, QFont.Bold))
            grid.addWidget(lbl, 0, col)

        for row, sink in enumerate(CUSTOM_SINKS, start=1):
            grid.addWidget(QLabel(sink), row, 0)
            for col, direction in enumerate(['up', 'down'], start=1):
                key_id = f'{sink}_{direction}'
                edit = KeyCaptureEdit()
                edit.setText(
                    self.state.get('hotkeys', {}).get(
                        key_id, self.DEFAULT_HOTKEYS[key_id]
                    )
                )
                self._captures[key_id] = edit
                grid.addWidget(edit, row, col)

        layout.addLayout(grid)

        step_row = QHBoxLayout()
        step_row.addWidget(QLabel('Volume Step:'))
        self._step_spin = QSpinBox()
        self._step_spin.setRange(1, 100)
        self._step_spin.setSuffix(' %')
        self._step_spin.setValue(self.state.get('volume_step', 5))
        step_row.addWidget(self._step_spin)
        step_row.addStretch()
        layout.addLayout(step_row)

        btn_row = QHBoxLayout()
        apply_btn = QPushButton('Apply')
        apply_btn.clicked.connect(self._apply)
        reset_btn = QPushButton('Reset to Defaults')
        reset_btn.clicked.connect(self._reset)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _apply(self):
        hotkeys = {key_id: edit.text() for key_id, edit in self._captures.items()}
        self.state['hotkeys'] = hotkeys
        self.state['volume_step'] = self._step_spin.value()
        self.on_apply(hotkeys, self._step_spin.value())
        self.accept()

    def _reset(self):
        for key_id, edit in self._captures.items():
            edit.setText(self.DEFAULT_HOTKEYS[key_id])
        self._step_spin.setValue(5)
```

- [ ] **Step 2: Smoke-test the dialog**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate
python3 - <<'EOF'
import sys
from PyQt5.QtWidgets import QApplication
from SoundSwitch import HotkeySettingsDialog
app = QApplication(sys.argv)
state = {'hotkeys': {}, 'volume_step': 5}
dlg = HotkeySettingsDialog(state, lambda h, s: print('Applied:', s, '%', h))
dlg.show()
sys.exit(app.exec_())
EOF
```

Expected: dialog opens with a 4-row table (Game/Media/Chat/Aux), each row showing two `KeyCaptureEdit` fields pre-filled with defaults, a `Volume Step: 5 %` spinbox, and Apply / Reset to Defaults / Cancel buttons. Clicking Apply prints the hotkey dict.

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add HotkeySettingsDialog with KeyCaptureEdit grid and step spinbox"
```

---

### Task 5: Add `GlobalShortcutsManager`

**Files:**
- Modify: `SoundSwitch.py` — add class after `HotkeySettingsDialog`, before `MainWindow`

- [ ] **Step 1: Add the class**

Insert immediately after `HotkeySettingsDialog` and before `class MainWindow`:

```python
_dbus_main_loop_initialized = False


class GlobalShortcutsManager(QtCore.QObject):
    """Registers and handles global shortcuts via the XDG GlobalShortcuts portal."""

    shortcut_activated = QtCore.pyqtSignal(str)  # emits shortcut_id

    PORTAL_BUS   = 'org.freedesktop.portal.Desktop'
    PORTAL_PATH  = '/org/freedesktop/portal/desktop'
    PORTAL_IFACE = 'org.freedesktop.portal.GlobalShortcuts'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bus = None
        self._portal = None
        self._session_handle = None
        self._glib_loop = None
        self._available = False

    def start(self):
        """Connect to the portal, create a session, and start the GLib event loop.
        Returns True on success, False if the portal is unavailable."""
        global _dbus_main_loop_initialized
        if not DBUS_AVAILABLE:
            return False
        try:
            if not _dbus_main_loop_initialized:
                DBusGMainLoop(set_as_default=True)
                _dbus_main_loop_initialized = True
            self._bus = dbus.SessionBus()
            self._portal = dbus.Interface(
                self._bus.get_object(self.PORTAL_BUS, self.PORTAL_PATH),
                self.PORTAL_IFACE,
            )
            self._glib_loop = GLib.MainLoop()
            threading.Thread(target=self._glib_loop.run, daemon=True).start()
            self._create_session()
            self._available = True
            return True
        except Exception:
            return False

    def _sender_token(self):
        """Return the D-Bus unique name in path-safe form (e.g. ':1.234' → '1_234')."""
        return self._bus.get_unique_name()[1:].replace('.', '_')

    def _create_session(self):
        token = f'ss_{uuid.uuid4().hex[:8]}'
        session_token = f'ss_s_{uuid.uuid4().hex[:8]}'
        request_path = (
            f'/org/freedesktop/portal/desktop/request/'
            f'{self._sender_token()}/{token}'
        )
        # Subscribe to Response BEFORE calling CreateSession to avoid the race.
        self._bus.add_signal_receiver(
            self._on_create_session_response,
            signal_name='Response',
            dbus_interface='org.freedesktop.portal.Request',
            path=request_path,
        )
        self._portal.CreateSession({
            'handle_token': dbus.String(token),
            'session_handle_token': dbus.String(session_token),
        })

    def _on_create_session_response(self, response_code, results):
        if response_code != 0:
            return
        self._session_handle = str(results.get('session_handle', ''))
        # Subscribe to Activated on the portal object (filtered by session_handle
        # inside the callback).
        self._bus.add_signal_receiver(
            self._on_activated,
            signal_name='Activated',
            dbus_interface=self.PORTAL_IFACE,
            path=self.PORTAL_PATH,
        )

    def bind_shortcuts(self, hotkeys):
        """Register all shortcuts with the portal. hotkeys is a dict of
        {shortcut_id: Qt-format key string}, e.g. {'Game_up': 'Ctrl+Alt+1'}."""
        if not self._session_handle:
            return
        shortcuts = dbus.Array(
            [
                (
                    dbus.String(key_id),
                    dbus.Dictionary(
                        {
                            'description': dbus.String(self._description(key_id)),
                            'preferred_trigger': dbus.String(trigger.lower()),
                        },
                        signature='sv',
                    ),
                )
                for key_id, trigger in hotkeys.items()
            ],
            signature='(sa{sv})',
        )
        token = f'ss_{uuid.uuid4().hex[:8]}'
        self._portal.BindShortcuts(
            dbus.ObjectPath(self._session_handle),
            shortcuts,
            dbus.String(''),
            dbus.Dictionary({'handle_token': dbus.String(token)}, signature='sv'),
        )

    def rebind(self, hotkeys):
        """Re-register shortcuts after the user changes bindings in settings."""
        self.bind_shortcuts(hotkeys)

    def _description(self, key_id):
        sink, direction = key_id.split('_', 1)
        return f'{sink} Volume {direction.title()}'

    def _on_activated(self, session_handle, shortcut_id, timestamp, options):
        if str(session_handle) == self._session_handle:
            self.shortcut_activated.emit(str(shortcut_id))

    def stop(self):
        if self._glib_loop:
            self._glib_loop.quit()
```

- [ ] **Step 2: Verify the app still imports cleanly**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 -c "from SoundSwitch import GlobalShortcutsManager; print('Import OK')"
```

Expected output: `Import OK`

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add GlobalShortcutsManager for XDG GlobalShortcuts portal"
```

---

### Task 6: Wire everything into MainWindow

**Files:**
- Modify: `SoundSwitch.py` — `init_menu_bar`, `MainWindow.__init__`, `closeEvent`, new methods

- [ ] **Step 1: Update `init_menu_bar` to add File → Hotkey Settings…**

Replace the current `init_menu_bar` body:
```python
    def init_menu_bar(self):
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)
        menubar.setStyleSheet('QMenuBar { background: #232629; color: #f0f0f0; } QMenuBar::item:selected { background: #005f87; } QMenu { background: #232629; color: #f0f0f0; } QMenu::item:selected { background: #005f87; }')
        file_menu = menubar.addMenu('File')
        exit_action = file_menu.addAction('Exit')
        exit_action.triggered.connect(self.close)
        self.setMenuBar(menubar)
```

with:
```python
    def init_menu_bar(self):
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)
        menubar.setStyleSheet('QMenuBar { background: #232629; color: #f0f0f0; } QMenuBar::item:selected { background: #005f87; } QMenu { background: #232629; color: #f0f0f0; } QMenu::item:selected { background: #005f87; }')
        file_menu = menubar.addMenu('File')
        hotkey_action = file_menu.addAction('Hotkey Settings\u2026')
        hotkey_action.triggered.connect(self.open_hotkey_settings)
        file_menu.addSeparator()
        exit_action = file_menu.addAction('Exit')
        exit_action.triggered.connect(self.close)
        self.setMenuBar(menubar)
```

- [ ] **Step 2: Instantiate `GlobalShortcutsManager` in `MainWindow.__init__`**

After `self.init_tray_icon()` (the last line of `__init__` before the `if start_minimized:` block), add:

```python
        self._shortcuts_manager = GlobalShortcutsManager(self)
        if self._shortcuts_manager.start():
            self._shortcuts_manager.shortcut_activated.connect(self._on_shortcut_activated)
            self._shortcuts_manager.bind_shortcuts(self.state.get('hotkeys', {}))
        else:
            self.show_status('Global hotkeys unavailable: xdg-desktop-portal-kde not running', error=True)
```

- [ ] **Step 3: Add `_on_shortcut_activated` and `open_hotkey_settings` to MainWindow**

After `set_sink_volume`, add:

```python
    def _on_shortcut_activated(self, shortcut_id):
        parts = shortcut_id.rsplit('_', 1)
        if len(parts) != 2:
            return
        sink_name, direction = parts
        if sink_name not in CUSTOM_SINKS or direction not in ('up', 'down'):
            return
        self.set_sink_volume(sink_name, direction)

    def open_hotkey_settings(self):
        def on_apply(hotkeys, step):
            self.save_state()
            self._shortcuts_manager.rebind(hotkeys)
            self.show_status('Hotkey settings saved.')
        HotkeySettingsDialog(self.state, on_apply, parent=self).exec_()
```

- [ ] **Step 4: Stop the GLib loop on close**

Replace the current `closeEvent`:
```python
    def closeEvent(self, event):
        self.save_state()
        if self.tray_icon:
            self.tray_icon.hide()
        super().closeEvent(event)
```

with:
```python
    def closeEvent(self, event):
        self.save_state()
        if hasattr(self, '_shortcuts_manager'):
            self._shortcuts_manager.stop()
        if self.tray_icon:
            self.tray_icon.hide()
        super().closeEvent(event)
```

- [ ] **Step 5: End-to-end manual verification**

Launch the app:
```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 SoundSwitch.py
```

Check each of the following:

1. **Menu item exists:** File menu shows `Hotkey Settings…` above a separator and `Exit`.

2. **Dialog opens:** Click `File → Hotkey Settings…` — dialog shows Game/Media/Chat/Aux rows, each with two `KeyCaptureEdit` fields pre-filled with defaults, and `Volume Step: 5 %`.

3. **Key capture works:** Click a field → shows `Press keys…` → press `Ctrl+Alt+5` → field shows `Ctrl+Alt+5`. Press Escape → reverts.

4. **Portal registration:** Click Apply — KDE may show a system dialog asking to approve the shortcut bindings (first time only). Approve it.

5. **Volume up works:** Press `Ctrl+Alt+1` — status bar shows `Game volume up (+5%)`. Verify:
   ```bash
   pactl list sinks | grep -A5 "Name: Game" | grep Volume
   ```
   Volume should be above 100% (or below if it was at 100%).

6. **Volume down works:** Press `Ctrl+Alt+Shift+1` — status bar shows `Game volume down (-5%)`.

7. **Step change works:** Open settings, set step to 10%, click Apply. Press `Ctrl+Alt+2` — status bar shows `Media volume up (+10%)`.

8. **State persists:** Close and reopen the app — `routing_state.json` should contain `volume_step` and `hotkeys` keys, and hotkeys should be re-registered on startup.

- [ ] **Step 6: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: wire volume hotkeys — menu, GlobalShortcutsManager, HotkeySettingsDialog"
```
