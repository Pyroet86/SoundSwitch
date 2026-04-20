# Noise Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to apply RNNoise-based noise cancellation to a hardware microphone via a right-click context menu, exposing a virtual source other apps (Discord etc.) can select as their input.

**Architecture:** Three pactl modules are loaded per mic (null-sink + LADSPA-sink + loopback); their IDs are persisted in `routing_state.json` and re-applied on startup. A `NoiseCancelDialog` exposes VAD threshold and channel mode settings. UI indicators (cyan `[NC]` badge + virtual-source sub-item) are rendered in the existing `refresh_devices_and_sinks()` refresh cycle.

**Tech Stack:** Python 3, PyQt5, pactl (PipeWire/PulseAudio compat), module-ladspa-sink, module-null-sink, module-loopback, `/usr/lib/ladspa/librnnoise_ladspa.so` (noise-suppression-for-voice package)

> **Note:** No automated test suite exists. Each task uses manual shell verification.

---

## File Structure

| File | Change |
|---|---|
| `SoundSwitch.py` | All changes — add constant, helper, dialog class, methods, context menu, refresh indicators, restore logic |

---

### Task 1: Add `RNNOISE_LADSPA` constant, `_safe_mic_id()` helper, and `QSlider` import

**Files:**
- Modify: `SoundSwitch.py` lines 9–30 (imports + constants)

- [ ] **Step 1: Add `QSlider` to the PyQt5 imports**

Find:
```python
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QLabel, QPushButton, QListWidgetItem, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QLineEdit,
    QComboBox, QMenu, QSystemTrayIcon, QAction, QDialog,
    QSpinBox, QCheckBox, QSplitter,
)
```

Replace with:
```python
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QLabel, QPushButton, QListWidgetItem, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QLineEdit,
    QComboBox, QMenu, QSystemTrayIcon, QAction, QDialog,
    QSpinBox, QCheckBox, QSplitter, QSlider,
)
```

- [ ] **Step 2: Add `RNNOISE_LADSPA` constant after `CUSTOM_SINKS`**

Find:
```python
STATE_FILE = 'routing_state.json'
CUSTOM_SINKS = ['Game', 'Media', 'Chat', 'Aux']
```

Replace with:
```python
STATE_FILE = 'routing_state.json'
CUSTOM_SINKS = ['Game', 'Media', 'Chat', 'Aux']
RNNOISE_LADSPA = '/usr/lib/ladspa/librnnoise_ladspa.so'
```

- [ ] **Step 3: Add `_safe_mic_id()` module-level helper after the constants block**

Add this function directly after the `RNNOISE_LADSPA = ...` line:

```python

def _safe_mic_id(mic_name):
    """Return a PipeWire-safe sink name component derived from a source name."""
    return re.sub(r'[^a-zA-Z0-9]', '_', mic_name)[:30]
```

- [ ] **Step 4: Verify the constant and helper are importable**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 -c "
from SoundSwitch import RNNOISE_LADSPA, _safe_mic_id
print('RNNOISE_LADSPA:', RNNOISE_LADSPA)
print('safe_id:', _safe_mic_id('alsa_input.usb-046d_0825_CC7CA3E0-02.mono-fallback'))
import os
print('package installed:', os.path.exists(RNNOISE_LADSPA))
"
```

Expected (package installed):
```
RNNOISE_LADSPA: /usr/lib/ladspa/librnnoise_ladspa.so
safe_id: alsa_input_usb_046d_0825_CC7CA
package installed: True
```

- [ ] **Step 5: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add RNNOISE_LADSPA constant and _safe_mic_id() helper"
```

---

### Task 2: Add `NoiseCancelDialog` class

**Files:**
- Modify: `SoundSwitch.py` — add class after `SettingsDialog` (around line 403)

- [ ] **Step 1: Add `NoiseCancelDialog` class after the closing of `SettingsDialog`**

Find the end of `SettingsDialog`:
```python
    def _on_minimized_changed(self, _state):
        if self._autostart_cb.isChecked():
            autostart.enable(start_minimized=self._minimized_cb.isChecked())
```

Add this entire class directly after it (before the `_QT_MOD_TO_XDG` dict):

```python

class NoiseCancelDialog(QDialog):

    def __init__(self, mic_name, mic_description, current_settings=None, parent=None):
        super().__init__(parent)
        self.mic_name = mic_name
        self.setWindowTitle('Noise Cancellation Settings')
        self.setModal(True)
        self.setMinimumWidth(400)
        self._init_ui(mic_description, current_settings or {})

    def _init_ui(self, mic_description, settings):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel(f'Microphone: {mic_description}'))

        threshold_label_row = QHBoxLayout()
        threshold_label_row.addWidget(QLabel('VAD Threshold:'))
        threshold_label_row.addStretch()
        layout.addLayout(threshold_label_row)

        threshold_row = QHBoxLayout()
        self._threshold_slider = QSlider(Qt.Horizontal)
        self._threshold_slider.setRange(0, 100)
        self._threshold_slider.setValue(settings.get('vad_threshold', 50))
        self._threshold_spin = QSpinBox()
        self._threshold_spin.setRange(0, 100)
        self._threshold_spin.setValue(settings.get('vad_threshold', 50))
        self._threshold_slider.valueChanged.connect(self._threshold_spin.setValue)
        self._threshold_spin.valueChanged.connect(self._threshold_slider.setValue)
        threshold_row.addWidget(self._threshold_slider)
        threshold_row.addWidget(self._threshold_spin)
        layout.addLayout(threshold_row)

        hint = QLabel('Lower = more aggressive noise suppression')
        hint.setStyleSheet('color: #aaa; font-size: 11px;')
        layout.addWidget(hint)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel('Channel Mode:'))
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(['Mono', 'Stereo'])
        self._mode_combo.setCurrentText(settings.get('channel_mode', 'mono').capitalize())
        mode_row.addWidget(self._mode_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        layout.addWidget(QLabel('Select this source name in Discord / other apps:'))
        safe_id = _safe_mic_id(self.mic_name)
        self._virt_field = QLineEdit(f'rnnoise_out_{safe_id}.monitor')
        self._virt_field.setReadOnly(True)
        layout.addWidget(self._virt_field)

        btn_row = QHBoxLayout()
        apply_btn = QPushButton('Apply')
        apply_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def get_settings(self):
        return {
            'vad_threshold': self._threshold_spin.value(),
            'channel_mode': self._mode_combo.currentText().lower(),
        }
```

- [ ] **Step 2: Verify dialog opens without errors**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 -c "
import sys
from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)
from SoundSwitch import NoiseCancelDialog
dlg = NoiseCancelDialog(
    'alsa_input.usb-046d_0825_CC7CA3E0-02.mono-fallback',
    'Webcam C270 Mono',
    {'vad_threshold': 30, 'channel_mode': 'stereo'},
)
dlg.show()
print('settings:', dlg.get_settings())
app.quit()
"
```

Expected:
```
settings: {'vad_threshold': 30, 'channel_mode': 'stereo'}
```

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add NoiseCancelDialog for RNNoise settings"
```

---

### Task 3: Add `enable_noise_cancellation()` and `disable_noise_cancellation()` methods

**Files:**
- Modify: `SoundSwitch.py` — add two methods to `MainWindow` after `set_default_sink()` (around line 1027)

- [ ] **Step 1: Add both methods after `set_default_sink()`**

Find the end of `set_default_sink()`:
```python
        QMessageBox.information(self, 'Default Sink', f'Set {sink_name} as the default output device and routed custom sinks to it.')
```

Add directly after it:

```python

    def enable_noise_cancellation(self, mic_name, vad_threshold, channel_mode):
        safe_id = _safe_mic_id(mic_name)
        label = 'noise_suppressor_mono' if channel_mode == 'mono' else 'noise_suppressor_stereo'
        virtual_source = f'rnnoise_out_{safe_id}.monitor'

        existing = self.state.get('noise_cancel', {}).get(mic_name)
        if existing:
            self.disable_noise_cancellation(mic_name)

        null_out = self.run_pactl([
            'load-module', 'module-null-sink',
            f'sink_name=rnnoise_out_{safe_id}',
            f'sink_properties=device.description="{virtual_source}"',
        ])
        try:
            null_id = int(null_out.strip())
        except ValueError:
            self.show_status('Failed to create noise cancellation sink.', error=True)
            return

        ladspa_out = self.run_pactl([
            'load-module', 'module-ladspa-sink',
            f'sink_name=rnnoise_ladspa_{safe_id}',
            f'sink_master=rnnoise_out_{safe_id}',
            f'label={label}',
            f'plugin={RNNOISE_LADSPA}',
            f'control={vad_threshold}',
        ])
        try:
            ladspa_id = int(ladspa_out.strip())
        except ValueError:
            self.run_pactl(['unload-module', str(null_id)])
            self.show_status('Failed to load RNNoise LADSPA plugin.', error=True)
            return

        loopback_out = self.run_pactl([
            'load-module', 'module-loopback',
            f'source={mic_name}',
            f'sink=rnnoise_ladspa_{safe_id}',
            'source_dont_move=true',
            'sink_dont_move=true',
        ])
        try:
            loopback_id = int(loopback_out.strip())
        except ValueError:
            self.run_pactl(['unload-module', str(ladspa_id)])
            self.run_pactl(['unload-module', str(null_id)])
            self.show_status('Failed to create noise cancellation loopback.', error=True)
            return

        self.state.setdefault('noise_cancel', {})[mic_name] = {
            'modules': [null_id, ladspa_id, loopback_id],
            'settings': {'vad_threshold': vad_threshold, 'channel_mode': channel_mode},
            'virtual_source': virtual_source,
        }
        self.save_state()
        self.show_status(f'Noise cancellation enabled: {virtual_source}')
        self.refresh_devices_and_sinks(force=True)

    def disable_noise_cancellation(self, mic_name):
        nc = self.state.get('noise_cancel', {}).get(mic_name)
        if not nc:
            return
        for mod_id in reversed(nc['modules']):
            self.run_pactl(['unload-module', str(mod_id)])
        del self.state['noise_cancel'][mic_name]
        self.save_state()
        self.show_status('Noise cancellation disabled.')
        self.refresh_devices_and_sinks(force=True)
```

- [ ] **Step 2: Verify the methods exist**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 -c "
import sys
from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)
from SoundSwitch import MainWindow
w = MainWindow()
assert hasattr(w, 'enable_noise_cancellation'), 'missing enable'
assert hasattr(w, 'disable_noise_cancellation'), 'missing disable'
print('OK: both methods present')
app.quit()
"
```

Expected: `OK: both methods present`

- [ ] **Step 3: Verify noise cancellation loads correctly (requires noise-suppression-for-voice installed)**

Get a real mic name first:
```bash
pactl list short sources | grep -v monitor
```

Then test (replace `<mic_name>` with actual name from above):
```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 -c "
import sys
from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)
from SoundSwitch import MainWindow
w = MainWindow()
mic = '<mic_name>'
w.enable_noise_cancellation(mic, 50, 'mono')
print('noise_cancel state:', w.state.get('noise_cancel', {}))
app.quit()
"
```

Expected: a dict entry under `noise_cancel` with three integer module IDs and `virtual_source` ending in `.monitor`.

Then verify the virtual source appears in pactl:
```bash
pactl list short sources | grep rnnoise
```

Expected: `rnnoise_out_<safe_id>.monitor` listed.

- [ ] **Step 4: Test disable removes modules**

```bash
pactl list short sources | grep rnnoise
# Should now show nothing after disable
```

Run in Python (continuing from Step 3 session):
```python
w.disable_noise_cancellation(mic)
```

Then:
```bash
pactl list short sources | grep rnnoise
```

Expected: no output (modules unloaded).

- [ ] **Step 5: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add enable/disable_noise_cancellation() methods"
```

---

### Task 4: Add context menu to `inputs_list` and `open_noise_cancel_dialog()`

**Files:**
- Modify: `SoundSwitch.py` — `init_ui()` to wire context menu signal, add two new methods to `MainWindow`

- [ ] **Step 1: Wire context menu signal on `inputs_list` in `init_ui()`**

Find in `init_ui()`:
```python
        self.inputs_list.setItemDelegate(RoundedBoxDelegate())
        inputs_panel.addWidget(inputs_label)
        inputs_panel.addWidget(self.inputs_list)
```

Replace with:
```python
        self.inputs_list.setItemDelegate(RoundedBoxDelegate())
        self.inputs_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.inputs_list.customContextMenuRequested.connect(self.show_input_context_menu)
        inputs_panel.addWidget(inputs_label)
        inputs_panel.addWidget(self.inputs_list)
```

- [ ] **Step 2: Add `show_input_context_menu()` and `show_rnnoise_install_info()` and `open_noise_cancel_dialog()` methods**

Add these three methods to `MainWindow`. A good place is after `show_stream_context_menu()` (around line 1150). Find:

```python
    def reset_manual_override(self, stream_index):
```

Add the three new methods directly before it:

```python
    def show_input_context_menu(self, pos):
        item = self.inputs_list.itemAt(pos)
        if not item:
            return
        mic_name = item.data(Qt.ItemDataRole.UserRole)
        if not mic_name:
            return
        menu = QMenu(self)
        import os
        if not os.path.exists(RNNOISE_LADSPA):
            action = menu.addAction('Noise Cancellation (package not installed)…')
            action.triggered.connect(self.show_rnnoise_install_info)
        else:
            nc = self.state.get('noise_cancel', {}).get(mic_name)
            if nc:
                settings_action = menu.addAction('Noise Cancellation Settings…')
                settings_action.triggered.connect(lambda: self.open_noise_cancel_dialog(mic_name))
                disable_action = menu.addAction('Disable Noise Cancellation')
                disable_action.triggered.connect(lambda: self.disable_noise_cancellation(mic_name))
            else:
                enable_action = menu.addAction('Enable Noise Cancellation…')
                enable_action.triggered.connect(lambda: self.open_noise_cancel_dialog(mic_name))
        menu.exec_(self.inputs_list.viewport().mapToGlobal(pos))

    def show_rnnoise_install_info(self):
        QMessageBox.information(
            self,
            'Package Required',
            'Noise cancellation requires the noise-suppression-for-voice package.\n\n'
            'Install it with:\n'
            '    sudo pacman -S noise-suppression-for-voice\n\n'
            'Then restart SoundSwitch.',
        )

    def open_noise_cancel_dialog(self, mic_name):
        sources = self.get_input_sources()
        mic_description = next(
            (s['description'] for s in sources if s['name'] == mic_name),
            mic_name,
        )
        current_settings = self.state.get('noise_cancel', {}).get(mic_name, {}).get('settings')
        dlg = NoiseCancelDialog(mic_name, mic_description, current_settings, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            settings = dlg.get_settings()
            self.enable_noise_cancellation(mic_name, settings['vad_threshold'], settings['channel_mode'])

```

- [ ] **Step 3: Remove the stale `import os` inside the method**

The `import os` inside `show_input_context_menu` is unnecessary since `os` is already imported at the top of the file. Replace:

```python
        import os
        if not os.path.exists(RNNOISE_LADSPA):
```

With:

```python
        if not os.path.exists(RNNOISE_LADSPA):
```

- [ ] **Step 4: Verify context menu appears**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 SoundSwitch.py
```

Right-click a microphone in the Input Devices list. Expected:
- If `noise-suppression-for-voice` is installed: menu shows "Enable Noise Cancellation…"
- If not installed: menu shows "Noise Cancellation (package not installed)…" which opens an info dialog

- [ ] **Step 5: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add noise cancellation context menu and dialog wiring"
```

---

### Task 5: Update `refresh_devices_and_sinks()` to show NC indicators

**Files:**
- Modify: `SoundSwitch.py` — the Input Devices population block (around line 1237)

- [ ] **Step 1: Replace the inputs_list population block**

Find the entire Input Devices panel block:
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
```

Replace with:
```python
        # Input Devices panel
        self.inputs_list.clear()
        input_sources = self.get_input_sources()
        nc_state = self.state.get('noise_cancel', {})
        if input_sources:
            for i, source in enumerate(input_sources):
                mic_name = source['name']
                nc = nc_state.get(mic_name)
                bg = QColor('#232629') if i % 2 == 0 else QColor('#2d2f31')

                display = source['description'] + (' [NC]' if nc else '')
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, mic_name)
                item.setBackground(QBrush(bg))
                if nc:
                    item.setForeground(QBrush(QColor('#00bfff')))
                self.inputs_list.addItem(item)

                if nc:
                    sub = QListWidgetItem(f"  \u21b3 {nc['virtual_source']}")
                    sub.setFlags(Qt.NoItemFlags)
                    sub.setBackground(QBrush(bg))
                    sub.setForeground(QBrush(QColor('#888')))
                    font = sub.font()
                    font.setItalic(True)
                    sub.setFont(font)
                    self.inputs_list.addItem(sub)
        else:
            placeholder = QListWidgetItem('(No microphones found)')
            placeholder.setFlags(Qt.NoItemFlags)
            placeholder.setForeground(QBrush(QColor('#555')))
            self.inputs_list.addItem(placeholder)
```

- [ ] **Step 2: Verify NC indicator renders correctly**

Enable noise cancellation on a mic via the context menu, then check the Input Devices list shows:
- The mic entry in cyan with `[NC]` appended
- A greyed italic sub-item `  ↳ rnnoise_out_<safe_id>.monitor` beneath it

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 SoundSwitch.py
```

Right-click mic → Enable Noise Cancellation… → Apply. The Input Devices list should update within 2 seconds (or immediately after Apply).

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: show NC badge and virtual source sub-item in Input Devices list"
```

---

### Task 6: Restore noise cancellation state on startup

**Files:**
- Modify: `SoundSwitch.py` — `restore_routing_state()` method (around line 1008)

- [ ] **Step 1: Extend `restore_routing_state()` to re-apply NC entries**

Find:
```python
    def restore_routing_state(self):
        # Restore default sink
        default_sink = self.state.get('default_sink')
        if default_sink:
            self.run_pactl(['set-default-sink', default_sink])
        # Restore loopbacks for custom sinks
        if 'loopbacks' in self.state and default_sink:
            self.setup_custom_sink_loopbacks(default_sink)
```

Replace with:
```python
    def restore_routing_state(self):
        # Restore default sink
        default_sink = self.state.get('default_sink')
        if default_sink:
            self.run_pactl(['set-default-sink', default_sink])
        # Restore loopbacks for custom sinks
        if 'loopbacks' in self.state and default_sink:
            self.setup_custom_sink_loopbacks(default_sink)
        # Restore noise cancellation
        nc_entries = list(self.state.get('noise_cancel', {}).items())
        if nc_entries:
            available = {s['name'] for s in self.get_input_sources()}
            self.state['noise_cancel'] = {}
            self.save_state()
            for mic_name, nc in nc_entries:
                if mic_name in available:
                    s = nc.get('settings', {})
                    self.enable_noise_cancellation(
                        mic_name,
                        s.get('vad_threshold', 50),
                        s.get('channel_mode', 'mono'),
                    )
```

The logic clears `noise_cancel` from state first (removing stale module IDs from the previous session), then re-enables for each mic that is still connected. Mics that have been unplugged are silently dropped.

- [ ] **Step 2: Verify NC restores on restart**

Enable noise cancellation on a mic, then quit and relaunch SoundSwitch:

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate
python3 SoundSwitch.py &
# Enable NC via context menu, then close the app (File → Exit)
python3 SoundSwitch.py
```

Expected on relaunch: the Input Devices list shows the mic with `[NC]` and the sub-item immediately after startup, and:
```bash
pactl list short sources | grep rnnoise
```
shows `rnnoise_out_<safe_id>.monitor`.

- [ ] **Step 3: Verify unplugged mic is gracefully skipped**

Edit `routing_state.json` manually and add a fake entry under `noise_cancel`:
```json
"noise_cancel": {
  "alsa_input.nonexistent-device": {
    "modules": [999, 998, 997],
    "settings": {"vad_threshold": 50, "channel_mode": "mono"},
    "virtual_source": "rnnoise_out_alsa_input_nonexistent.monitor"
  }
}
```

Launch SoundSwitch. Expected: no crash, no warning dialog, the fake entry is removed from `routing_state.json` after startup.

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: restore noise cancellation state on startup"
```
