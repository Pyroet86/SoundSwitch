# Volume OSD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a non-focus-stealing on-screen display that shows sink name and new volume percentage whenever a global keyboard shortcut adjusts a virtual sink's volume.

**Architecture:** A singleton `VolumeOSD(QWidget)` is constructed once in `MainWindow.__init__` and reused across all volume events; it uses `Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus` to guarantee focus is never stolen. A new `OSDSettingsDialog` lets the user configure position and fade duration, persisted in `routing_state.json`.

**Tech Stack:** Python 3, PyQt5 (`QWidget`, `QPropertyAnimation`, `QTimer`, `QApplication.primaryScreen`)

---

## File Map

| File | Change |
|------|--------|
| `SoundSwitch.py` | Add `VolumeOSD` class (lines ~160, before `HotkeySettingsDialog`); add `OSDSettingsDialog` class (lines ~215, after `HotkeySettingsDialog`); add `get_sink_volume()` method to `MainWindow`; update `set_sink_volume()`; update `__init__` defaults + OSD construction; update `init_tray_icon()` and `init_menu_bar()` |

---

### Task 1: Add `VolumeOSD` widget class

**Files:**
- Modify: `SoundSwitch.py` — insert new class before `HotkeySettingsDialog` at line 167

- [ ] **Step 1: Add `QPropertyAnimation` to PyQt5 imports**

At `SoundSwitch.py:11`, change:
```python
from PyQt5.QtCore import Qt, QTimer
```
to:
```python
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
```

- [ ] **Step 2: Insert `VolumeOSD` class before `HotkeySettingsDialog`**

Insert immediately before the line `class HotkeySettingsDialog(QDialog):` (currently line 167):

```python
class VolumeOSD(QWidget):
    """Non-focus-stealing on-screen display for volume changes."""

    _MARGIN = 20
    _FADE_MS = 400

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint |
                         Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(
            'QLabel {'
            '  background: #1e1e2e;'
            '  color: #ffffff;'
            '  font-size: 14px;'
            '  font-weight: bold;'
            '  border-radius: 8px;'
            '  padding: 12px 20px;'
            '}'
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self.setMinimumWidth(180)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_fade)

        self._anim = QPropertyAnimation(self, b'windowOpacity')
        self._anim.setDuration(self._FADE_MS)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self.hide)

    def show_volume(self, sink_name, volume, position, duration):
        """Show the OSD with the given text, position, and fade duration (seconds)."""
        self._label.setText(f'{sink_name}: {volume}%')
        self.adjustSize()
        self._position_on_screen(position)
        # Cancel any in-flight fade and reset opacity
        self._anim.stop()
        self._hide_timer.stop()
        self.setWindowOpacity(1.0)
        self.show()
        self._hide_timer.start(duration * 1000)

    def _start_fade(self):
        self._anim.start()

    def _position_on_screen(self, position):
        screen = QApplication.primaryScreen()
        if screen is None:
            self.move(0, 0)
            return
        sg = screen.geometry()
        w, h = self.sizeHint().width(), self.sizeHint().height()
        m = self._MARGIN
        positions = {
            'top-left':      (sg.x() + m,                        sg.y() + m),
            'top-center':    (sg.x() + (sg.width() - w) // 2,   sg.y() + m),
            'top-right':     (sg.x() + sg.width() - w - m,      sg.y() + m),
            'bottom-left':   (sg.x() + m,                        sg.y() + sg.height() - h - m),
            'bottom-center': (sg.x() + (sg.width() - w) // 2,   sg.y() + sg.height() - h - m),
            'bottom-right':  (sg.x() + sg.width() - w - m,      sg.y() + sg.height() - h - m),
        }
        x, y = positions.get(position, positions['bottom-right'])
        self.move(x, y)

```

- [ ] **Step 3: Verify the file parses cleanly**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 -c "import ast; ast.parse(open('SoundSwitch.py').read()); print('OK')"
```
Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add VolumeOSD non-focus-stealing widget"
```

---

### Task 2: Add `OSDSettingsDialog` class

**Files:**
- Modify: `SoundSwitch.py` — insert new class after `HotkeySettingsDialog._apply()` ends (currently around line 213, before `_QT_MOD_TO_XDG`)

- [ ] **Step 1: Insert `OSDSettingsDialog` class**

Insert immediately before the line `_QT_MOD_TO_XDG = {` (currently ~line 215, will have shifted slightly after Task 1):

```python
class OSDSettingsDialog(QDialog):

    POSITIONS = [
        ('Top Left',      'top-left'),
        ('Top Center',    'top-center'),
        ('Top Right',     'top-right'),
        ('Bottom Left',   'bottom-left'),
        ('Bottom Center', 'bottom-center'),
        ('Bottom Right',  'bottom-right'),
    ]

    def __init__(self, state, on_apply, parent=None):
        super().__init__(parent)
        self.state = state
        self.on_apply = on_apply
        self.setWindowTitle('OSD Settings')
        self.setModal(True)
        self.setMinimumWidth(320)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel('Position:'))
        self._pos_combo = QComboBox()
        for label, _ in self.POSITIONS:
            self._pos_combo.addItem(label)
        current_pos = self.state.get('osd_position', 'bottom-right')
        keys = [k for _, k in self.POSITIONS]
        if current_pos in keys:
            self._pos_combo.setCurrentIndex(keys.index(current_pos))
        pos_row.addWidget(self._pos_combo)
        pos_row.addStretch()
        layout.addLayout(pos_row)

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel('Display Duration:'))
        self._dur_spin = QSpinBox()
        self._dur_spin.setRange(1, 5)
        self._dur_spin.setSuffix(' s')
        self._dur_spin.setValue(self.state.get('osd_duration', 3))
        dur_row.addWidget(self._dur_spin)
        dur_row.addStretch()
        layout.addLayout(dur_row)

        btn_row = QHBoxLayout()
        apply_btn = QPushButton('Apply')
        apply_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _apply(self):
        self.state['osd_position'] = self.POSITIONS[self._pos_combo.currentIndex()][1]
        self.state['osd_duration'] = self._dur_spin.value()
        self.on_apply()
        self.accept()

```

- [ ] **Step 2: Verify the file parses cleanly**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 -c "import ast; ast.parse(open('SoundSwitch.py').read()); print('OK')"
```
Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add OSDSettingsDialog with position and duration controls"
```

---

### Task 3: Add state defaults and `VolumeOSD` instance to `MainWindow`

**Files:**
- Modify: `SoundSwitch.py` — `MainWindow.__init__` (currently around lines 416–462)

- [ ] **Step 1: Add OSD state defaults alongside existing defaults**

Find this block (currently around lines 433–436):
```python
        if 'volume_step' not in self.state:
            self.state['volume_step'] = 5
        if 'shortcut_version' not in self.state:
            self.state['shortcut_version'] = 0
```

Replace with:
```python
        if 'volume_step' not in self.state:
            self.state['volume_step'] = 5
        if 'shortcut_version' not in self.state:
            self.state['shortcut_version'] = 0
        if 'osd_position' not in self.state:
            self.state['osd_position'] = 'bottom-right'
        if 'osd_duration' not in self.state:
            self.state['osd_duration'] = 3
```

- [ ] **Step 2: Construct the OSD singleton after `init_tray_icon()`**

Find this line (currently around line 451):
```python
        self.init_tray_icon()
        self._shortcuts_manager = GlobalShortcutsManager(self)
```

Replace with:
```python
        self.init_tray_icon()
        self._osd = VolumeOSD()
        self._shortcuts_manager = GlobalShortcutsManager(self)
```

- [ ] **Step 3: Verify the file parses cleanly**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 -c "import ast; ast.parse(open('SoundSwitch.py').read()); print('OK')"
```
Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: wire VolumeOSD singleton and OSD state defaults into MainWindow"
```

---

### Task 4: Add `get_sink_volume()` and update `set_sink_volume()`

**Files:**
- Modify: `SoundSwitch.py` — `MainWindow.get_sink_volume` (new method) and `MainWindow.set_sink_volume` (currently around lines 1037–1041, will have shifted)

- [ ] **Step 1: Add `get_sink_volume()` method immediately before `set_sink_volume()`**

Find the line:
```python
    def set_sink_volume(self, sink_name, direction):
```

Insert immediately before it:
```python
    def get_sink_volume(self, sink_name):
        """Return current volume of a sink as an integer 0-100, or None on failure."""
        try:
            output = self.run_pactl(['get-sink-volume', sink_name])
            import re
            match = re.search(r'(\d+)%', output)
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return None

```

- [ ] **Step 2: Update `set_sink_volume()` to read back volume and show OSD**

Find:
```python
    def set_sink_volume(self, sink_name, direction):
        step = self.state.get('volume_step', 5)
        delta = f'+{step}%' if direction == 'up' else f'-{step}%'
        self.run_pactl(['set-sink-volume', sink_name, delta])
        self.show_status(f'{sink_name} volume {direction} ({delta})')
```

Replace with:
```python
    def set_sink_volume(self, sink_name, direction):
        step = self.state.get('volume_step', 5)
        delta = f'+{step}%' if direction == 'up' else f'-{step}%'
        self.run_pactl(['set-sink-volume', sink_name, delta])
        self.show_status(f'{sink_name} volume {direction} ({delta})')
        volume = self.get_sink_volume(sink_name)
        if volume is not None:
            self._osd.show_volume(
                sink_name,
                volume,
                self.state.get('osd_position', 'bottom-right'),
                self.state.get('osd_duration', 3),
            )
```

- [ ] **Step 3: Verify the file parses cleanly**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 -c "import ast; ast.parse(open('SoundSwitch.py').read()); print('OK')"
```
Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: read back sink volume after change and show OSD"
```

---

### Task 5: Add OSD Settings to tray menu and file menu

**Files:**
- Modify: `SoundSwitch.py` — `MainWindow.init_tray_icon()` (currently around lines 980–997) and `MainWindow.init_menu_bar()` (currently around lines 464–474) and add `open_osd_settings()` method

- [ ] **Step 1: Add `open_osd_settings()` method after `open_hotkey_settings()`**

Find the end of `open_hotkey_settings()` (currently ending around line 1067 with `HotkeySettingsDialog(...).exec_()`):
```python
        HotkeySettingsDialog(self.state, on_apply, parent=self).exec_()
```

Insert the following method immediately after it:
```python
    def open_osd_settings(self):
        def on_apply():
            self.save_state()
        OSDSettingsDialog(self.state, on_apply, parent=self).exec_()

```

- [ ] **Step 2: Add "OSD Settings…" to tray menu**

Find in `init_tray_icon()`:
```python
        self.tray_menu.addAction(self.action_show)
        self.tray_menu.addAction(self.action_hide)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.action_exit)
```

Replace with:
```python
        self.tray_menu.addAction(self.action_show)
        self.tray_menu.addAction(self.action_hide)
        self.tray_menu.addSeparator()
        action_hotkey = QAction('Hotkey Settings\u2026', self)
        action_hotkey.triggered.connect(self.open_hotkey_settings)
        self.tray_menu.addAction(action_hotkey)
        action_osd = QAction('OSD Settings\u2026', self)
        action_osd.triggered.connect(self.open_osd_settings)
        self.tray_menu.addAction(action_osd)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.action_exit)
```

- [ ] **Step 3: Add "OSD Settings…" to File menu in menu bar**

Find in `init_menu_bar()`:
```python
        hotkey_action = file_menu.addAction('Hotkey Settings\u2026')
        hotkey_action.triggered.connect(self.open_hotkey_settings)
        file_menu.addSeparator()
        exit_action = file_menu.addAction('Exit')
```

Replace with:
```python
        hotkey_action = file_menu.addAction('Hotkey Settings\u2026')
        hotkey_action.triggered.connect(self.open_hotkey_settings)
        osd_action = file_menu.addAction('OSD Settings\u2026')
        osd_action.triggered.connect(self.open_osd_settings)
        file_menu.addSeparator()
        exit_action = file_menu.addAction('Exit')
```

- [ ] **Step 4: Verify the file parses cleanly**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 -c "import ast; ast.parse(open('SoundSwitch.py').read()); print('OK')"
```
Expected output: `OK`

- [ ] **Step 5: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add OSD Settings entry to tray menu and file menu"
```

---

### Task 6: Manual smoke test

There is no automated test suite in this project. Verify the feature manually.

- [ ] **Step 1: Launch the app**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 SoundSwitch.py
```

Expected: app launches without errors or tracebacks in the terminal.

- [ ] **Step 2: Verify OSD appears on volume hotkey**

Press one of the configured volume hotkeys (e.g. `Ctrl+Alt+1` for Game up). Expected: a dark rounded overlay appears in the bottom-right corner showing e.g. `Game: 70%`, then fades out after ~3 seconds without stealing focus from the current window.

- [ ] **Step 3: Verify OSD settings dialog**

Open tray menu → "OSD Settings…". Expected: dialog with Position combo (6 options) and Display Duration spinner (1–5 s). Change position to `Top Left`, duration to `1 s`, click Apply. Press a volume hotkey again — OSD should now appear top-left and fade after 1 second.

- [ ] **Step 4: Verify persistence**

Close and relaunch the app. Open OSD Settings — the saved position and duration should be restored.

- [ ] **Step 5: Verify no focus steal**

Open a full-screen application or video. Press a volume hotkey. Verify the OSD appears overlaid but focus remains in the full-screen app (keyboard input still goes to it, not to the OSD).

- [ ] **Step 6: Final commit if any fixes were needed**

```bash
git add SoundSwitch.py
git commit -m "fix: <describe any fixes from smoke test>"
```
