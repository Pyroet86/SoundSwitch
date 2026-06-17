# Stream Mute Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an always-visible drawn mute button to each stream item in the four sink panels (Game/Media/Chat/Aux) that toggles PipeWire mute state via `pactl`.

**Architecture:** Single-file change in `SoundSwitch.py`. Parse `Mute:` from `pactl list sink-inputs`, expose it on each stream dict. Add a `MuteButton` QPushButton subclass that draws a speaker icon with QPainter. Switch the sink panel item loop to use `setItemWidget` so each row has the text labels plus the mute button inline.

**Tech Stack:** Python 3, PyQt5, pactl (PipeWire/PulseAudio CLI)

## Global Constraints

- No test suite exists — verification is manual (run the app, observe behaviour).
- All changes are in `SoundSwitch.py` only.
- Dark theme palette: background `#232629` / `#2d2f31`, text `#f0f0f0`, subtitle `#b0b0b0`, accent cyan `#00bfff`, mute-cross red `#ff4444`.
- `pactl set-sink-input-mute <index> toggle` is the mute command.
- Python virtual environment must be activated before running: `source .venv/bin/activate`.

---

### Task 1: Parse mute state in `get_sink_inputs()` and update the change-detection snapshot

**Files:**
- Modify: `SoundSwitch.py:1500-1519` (`get_sink_inputs`)
- Modify: `SoundSwitch.py:1220-1228` (`conditional_refresh` snapshot tuple)

**Interfaces:**
- Produces: each stream dict from `get_sink_inputs()` now has a `'muted': bool` key (`True` = muted, `False` = unmuted/absent).
- Produces: the snapshot in `conditional_refresh()` includes mute state, so external mute changes trigger a UI redraw within 2 s.

---

- [ ] **Step 1: Add `Mute:` parsing to `get_sink_inputs()`**

`pactl list sink-inputs` outputs `Mute: yes` or `Mute: no` as a top-level field for each sink input, before the `Properties` block. Add one `elif` branch to parse it.

In `SoundSwitch.py`, replace the entire `get_sink_inputs` method (lines 1500–1519) with:

```python
def get_sink_inputs(self):
    output = self.run_pactl(['list', 'sink-inputs'])
    inputs = []
    current = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith('Sink Input #'):
            if current:
                inputs.append(current)
            current = {'index': line.split('#')[1].strip()}
        elif line.startswith('Mute:'):
            current['muted'] = line.split(':', 1)[1].strip() == 'yes'
        elif line.startswith('application.name = '):
            current['app_name'] = line.split('=', 1)[1].strip().strip('"')
        elif line.startswith('media.name = '):
            current['media_name'] = line.split('=', 1)[1].strip().strip('"')
        elif line.startswith('Sink:'):
            current['sink'] = line.split(':', 1)[1].strip()
    if current:
        inputs.append(current)
    return inputs
```

- [ ] **Step 2: Add `muted` to the change-detection snapshot**

In `conditional_refresh()` (around line 1222), update the sink_inputs tuple element to include `s.get('muted')`. Find this block:

```python
        tuple(sorted((s['index'], s.get('sink'), s.get('app_name'), s.get('media_name')) for s in sink_inputs)),
```

Replace it with:

```python
        tuple(sorted((s['index'], s.get('sink'), s.get('app_name'), s.get('media_name'), s.get('muted')) for s in sink_inputs)),
```

- [ ] **Step 3: Verify manually**

```bash
source .venv/bin/activate
python3 -c "
import sys
from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)
# Import and instantiate just enough to call get_sink_inputs
import importlib.util, types
spec = importlib.util.spec_from_file_location('ss', 'SoundSwitch.py')
# Just check syntax compiles
import py_compile; py_compile.compile('SoundSwitch.py', doraise=True)
print('Syntax OK')
"
```

Expected output: `Syntax OK`

Also run the app briefly and check the terminal for no errors:

```bash
source .venv/bin/activate && timeout 5 python3 SoundSwitch.py 2>&1 | head -20 || true
```

Expected: app starts without traceback (it will be killed by timeout after 5 s).

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: parse mute state from pactl in get_sink_inputs"
```

---

### Task 2: Add `MuteButton` class and `toggle_stream_mute` method

**Files:**
- Modify: `SoundSwitch.py` — add `MuteButton` class near the other widget classes (after `RoundedBoxDelegate`, before `VolumeOSD`); add `toggle_stream_mute` method to `MainWindow`.

**Interfaces:**
- Consumes: `stream['muted']: bool` from Task 1.
- Produces: `MuteButton(stream_index: str, muted: bool, toggle_cb: callable, parent=None)` — a 28×28 QPushButton that draws a speaker icon and calls `toggle_cb(stream_index)` on click.
- Produces: `MainWindow.toggle_stream_mute(stream_index: str)` — calls pactl and force-refreshes the UI.

---

- [ ] **Step 1: Add the `MuteButton` class**

Insert the following class into `SoundSwitch.py` immediately after the `RuleItemDelegate` class (after line 276, before the `VolumeOSD` class). The icon is drawn in a 16×16 area centred inside the 28×28 button (6 px offset each side).

```python
class MuteButton(QPushButton):
    def __init__(self, stream_index, muted, toggle_cb, parent=None):
        super().__init__(parent)
        self.stream_index = stream_index
        self._muted = muted
        self.setFixedSize(28, 28)
        self.setFlat(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet('QPushButton { background: transparent; border: none; }'
                           'QPushButton:hover { background: rgba(255,255,255,20); border-radius: 4px; }')
        self.clicked.connect(lambda: toggle_cb(stream_index))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        ox, oy = 6, 6  # offset: centres 16×16 icon in 28×28 button

        color = QColor('#f0f0f0')

        # Speaker body — small rounded rectangle on the left
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(ox + 1, oy + 6, 3, 4, 1, 1)

        # Speaker cone — trapezoid opening to the right
        cone = QPainterPath()
        cone.moveTo(ox + 4, oy + 6)
        cone.lineTo(ox + 8, oy + 2)
        cone.lineTo(ox + 8, oy + 14)
        cone.lineTo(ox + 4, oy + 10)
        cone.closeSubpath()
        painter.fillPath(cone, QBrush(color))

        if not self._muted:
            # Two sound-wave arcs
            painter.setBrush(Qt.NoBrush)
            for radius, alpha in ((4, 220), (6, 150)):
                wave = QColor('#f0f0f0')
                wave.setAlpha(alpha)
                painter.setPen(QPen(wave, 1.5, Qt.SolidLine, Qt.RoundCap))
                cx, cy = ox + 8, oy + 8
                painter.drawArc(cx - radius, cy - radius,
                                radius * 2, radius * 2,
                                -50 * 16, 100 * 16)
        else:
            # Red diagonal cross overlaid on the right side of the icon
            painter.setPen(QPen(QColor('#ff4444'), 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(ox + 10, oy + 3, ox + 15, oy + 13)
            painter.drawLine(ox + 10, oy + 13, ox + 15, oy + 3)

        painter.end()
```

- [ ] **Step 2: Add `toggle_stream_mute` method to `MainWindow`**

Insert the following method into `MainWindow` immediately after `move_sink_input` (after line 2140, before `get_sink_volume`):

```python
def toggle_stream_mute(self, stream_index):
    self.run_pactl(['set-sink-input-mute', str(stream_index), 'toggle'])
    self.refresh_devices_and_sinks(force=True)
```

- [ ] **Step 3: Verify syntax**

```bash
source .venv/bin/activate
python3 -c "import py_compile; py_compile.compile('SoundSwitch.py', doraise=True); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add MuteButton widget and toggle_stream_mute method"
```

---

### Task 3: Switch sink panel loop to `setItemWidget` with inline `MuteButton`

**Files:**
- Modify: `SoundSwitch.py:1913-1953` — the `for sink in CUSTOM_SINKS` loop inside `refresh_devices_and_sinks`.

**Interfaces:**
- Consumes: `MuteButton(stream_index, muted, toggle_cb)` from Task 2.
- Consumes: `stream['muted']: bool` from Task 1.
- Consumes: `self.toggle_stream_mute` from Task 2.

---

- [ ] **Step 1: Replace the sink panel item loop**

In `refresh_devices_and_sinks()`, find and replace the entire `# Sinks panel` block (from the comment line `# Sinks panel: show each sink's streams in its own list...` through to just before `# Outputs panel`). The exact block to replace starts at the comment on line ~1913 and ends after `sink_list.addItem(stream_item)` on line ~1953.

Replace it with:

```python
        # Sinks panel: show each sink's streams in its own list, skip hidden streams
        for sink in CUSTOM_SINKS:
            sink_list = self.sink_lists[sink]
            sink_list.clear()
            streams = [s for s in sink_map.get(sink, []) if s['index'] not in self.hidden_streams]
            for j, stream in enumerate(streams):
                url = stream.get('url', '')
                domain = _url_domain(url)
                title = stream.get('title', '')
                artist = stream.get('artist', '')
                media_name = stream.get('media_name', '')
                app_label = f"{stream.get('app_name', 'Unknown App')} (#{stream['index']})"
                if domain:
                    if artist and title:
                        enriched = f"{domain} — {artist} - {title}"
                    elif title:
                        enriched = f"{domain} — {title}"
                    else:
                        enriched = domain
                else:
                    enriched = media_name
                main_label = enriched if enriched else app_label
                sub_label = app_label if enriched else ''

                bg = '#232629' if j % 2 == 0 else '#2d2f31'

                stream_item = QListWidgetItem()
                stream_item.setSizeHint(QtCore.QSize(0, 52))
                stream_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                tooltip_parts = [f"App: {stream.get('app_name', 'Unknown App')}"]
                if url:
                    tooltip_parts.append(f"URL: {url}")
                if title:
                    tooltip_parts.append(f"Title: {artist} - {title}" if artist else f"Title: {title}")
                elif not url:
                    tooltip_parts.append(f"Media: {media_name}")
                stream_item.setToolTip('\n'.join(tooltip_parts))

                widget = QWidget()
                widget.setStyleSheet(f'background: {bg};')
                row = QHBoxLayout(widget)
                row.setContentsMargins(8, 4, 4, 4)
                row.setSpacing(4)

                text_col = QVBoxLayout()
                text_col.setSpacing(2)
                text_col.setContentsMargins(0, 0, 0, 0)

                main_lbl = QLabel(main_label)
                main_lbl.setStyleSheet('color: #f0f0f0; font-size: 10pt; background: transparent;')
                main_lbl.setWordWrap(False)
                text_col.addWidget(main_lbl)

                if sub_label:
                    sub_lbl = QLabel(sub_label)
                    sub_lbl.setStyleSheet(
                        'color: #b0b0b0; font-size: 8pt; font-style: italic; background: transparent;')
                    sub_lbl.setWordWrap(False)
                    text_col.addWidget(sub_lbl)

                row.addLayout(text_col, 1)
                row.addWidget(MuteButton(stream['index'], stream.get('muted', False),
                                         self.toggle_stream_mute))

                sink_list.addItem(stream_item)
                sink_list.setItemWidget(stream_item, widget)
```

- [ ] **Step 2: Verify syntax**

```bash
source .venv/bin/activate
python3 -c "import py_compile; py_compile.compile('SoundSwitch.py', doraise=True); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 3: Run the app and verify end-to-end**

```bash
source .venv/bin/activate && python3 SoundSwitch.py
```

Check:
1. Each stream item in a sink panel shows a drawn speaker icon on the right.
2. Clicking the icon on an unmuted stream: icon changes to speaker + red cross; audio is silenced (`pactl list sink-inputs | grep -A2 'Sink Input'` should show `Mute: yes`).
3. Clicking again: icon reverts to speaker + waves; audio resumes.
4. The 2-second timer also picks up the mute state change (test by muting externally with `pactl set-sink-input-mute <index> 1` and waiting 2 s — icon should update).
5. Streams with no sub-label (no media name / URL) show at 52 px height with just the main label centred.
6. Drag-and-drop from the left Application Streams panel into a sink still works.

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add inline mute button to sink panel stream items"
```
