# Rules Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inline rules editing controls in the main window with a read-only highlighted list and a single "Manage Rules…" button that opens a dedicated `RulesDialog`.

**Architecture:** All changes are in `SoundSwitch.py` (single-file project). A new `RuleItemDelegate` handles highlighted keyword rendering. A new `RulesDialog` provides the side-by-side list + form UI. `MainWindow.init_ui()` is trimmed of inline controls and `refresh_rules_list()` is updated to use the new delegate.

**Tech Stack:** Python 3, PyQt5

---

## File Map

| File | Change |
|---|---|
| `SoundSwitch.py` | Add `QFontMetrics` import; add `RuleItemDelegate` class; add `RulesDialog` class; update `init_ui()` rules section; update `refresh_rules_list()`; add `open_rules_dialog()`; delete `add_rule_from_ui()` and `remove_selected_rule()` |

---

## Task 1: Add `QFontMetrics` to imports and add `RuleItemDelegate`

**Files:**
- Modify: `SoundSwitch.py:17` (QtGui import line)
- Modify: `SoundSwitch.py:177` (after `RoundedBoxDelegate`, before `VolumeOSD`)

- [ ] **Step 1: Add `QFontMetrics` to the QtGui import**

Find line 17 in `SoundSwitch.py`:
```python
from PyQt5.QtGui import QFont, QIcon, QColor, QBrush, QPalette, QPainter, QPixmap, QPen, QPainterPath
```
Change to:
```python
from PyQt5.QtGui import QFont, QFontMetrics, QIcon, QColor, QBrush, QPalette, QPainter, QPixmap, QPen, QPainterPath
```

- [ ] **Step 2: Add `RuleItemDelegate` after the `RoundedBoxDelegate` class (after line 177)**

Insert this new class between `RoundedBoxDelegate` and `VolumeOSD`:

```python
class RuleItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect.adjusted(4, 4, -4, -4)
        radius = 10
        if option.state & QStyle.State_Selected:
            bg = QColor('#005f87')
            border = QColor('#fff')
        elif option.state & QStyle.State_MouseOver:
            bg = QColor('#2d4157')
            border = QColor('#444')
        else:
            bg = QColor('#232629') if index.row() % 2 == 0 else QColor('#2d2f31')
            border = QColor('#444')
        painter.setRenderHint(painter.Antialiasing)
        painter.setBrush(bg)
        painter.setPen(border)
        painter.drawRoundedRect(rect, radius, radius)
        data = index.data(Qt.UserRole)
        if not data or not isinstance(data, dict):
            painter.restore()
            return
        app_name = data.get('app_name', '')
        sink = data.get('sink', '')
        base_font = QFont(option.font)
        base_font.setPointSize(10)
        fm_normal = QFontMetrics(base_font)
        bold_font = QFont(base_font)
        bold_font.setBold(True)
        fm_bold = QFontMetrics(bold_font)
        x = rect.x() + 10
        y = rect.y() + (rect.height() + fm_normal.ascent() - fm_normal.descent()) // 2
        segments = [
            ('If audio stream is ', base_font, fm_normal, QColor('#f0f0f0')),
            (app_name,             bold_font,  fm_bold,   QColor('#00bfff')),
            (' route to ',         base_font,  fm_normal, QColor('#f0f0f0')),
            (sink,                 bold_font,  fm_bold,   QColor('#00bfff')),
        ]
        for text, font, fm, color in segments:
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(x, y, text)
            x += fm.horizontalAdvance(text)
        painter.restore()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        return base.expandedTo(QtCore.QSize(base.width(), 36))
```

- [ ] **Step 3: Run the app to verify it starts without errors**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 SoundSwitch.py
```

Expected: app opens normally, no tracebacks. The rules list still uses plain text at this point (delegate not wired yet). Close the app.

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add RuleItemDelegate with cyan+bold keyword highlighting"
```

---

## Task 2: Update the main UI rules panel

**Files:**
- Modify: `SoundSwitch.py` — `init_ui()` rules section (~lines 962–987) and `refresh_rules_list()` (~lines 1403–1407)

- [ ] **Step 1: Replace the rules section in `init_ui()`**

Find this block (lines 962–987):
```python
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
```

Replace with:
```python
        rules_widget = QWidget()
        rules_layout = QVBoxLayout(rules_widget)
        rules_layout.setContentsMargins(0, 8, 0, 0)
        rules_label = QLabel('Auto-Routing Rules')
        rules_label.setFont(QFont('', 12, QFont.Bold))
        rules_label.setStyleSheet('margin-bottom: 8px;')
        self.rules_list = QListWidget()
        self.rules_list.setAlternatingRowColors(True)
        self.rules_list.setSelectionMode(QListWidget.SingleSelection)
        self.rules_list.setStyleSheet('QListWidget { padding: 4px; }')
        self.rules_list.setItemDelegate(RuleItemDelegate())
        manage_rules_btn = QPushButton('Manage Rules…')
        manage_rules_btn.clicked.connect(self.open_rules_dialog)
        rules_layout.addWidget(rules_label)
        rules_layout.addWidget(self.rules_list)
        rules_layout.addWidget(manage_rules_btn)
```

- [ ] **Step 2: Update `refresh_rules_list()` to populate structured item data**

Find `refresh_rules_list()` (~line 1403):
```python
    def refresh_rules_list(self):
        self.rules_list.clear()
        for rule in self.state['rules']:
            item = QListWidgetItem(f"If app is '{rule['app_name']}' → {rule['sink']}")
            self.rules_list.addItem(item)
```

Replace with:
```python
    def refresh_rules_list(self):
        self.rules_list.clear()
        for rule in self.state['rules']:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, {'app_name': rule['app_name'], 'sink': rule['sink']})
            item.setData(Qt.DisplayRole, f"{rule['app_name']} → {rule['sink']}")
            self.rules_list.addItem(item)
```

- [ ] **Step 3: Add a stub `open_rules_dialog()` so the button doesn't crash**

Add this method to `MainWindow` (e.g. near `open_settings()`):

```python
    def open_rules_dialog(self):
        pass
```

- [ ] **Step 4: Run the app and verify**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 SoundSwitch.py
```

Expected:
- "Auto-Routing Rules" header is the same size and spacing as "Application Streams" above it — no longer cramped against the splitter
- The inline text field, dropdowns, Add Rule, and Remove Selected buttons are gone
- A single "Manage Rules…" button appears below the rules list
- Existing rules display as `"If audio stream is Firefox route to Aux"` with "Firefox" and "Aux" in cyan bold
- Clicking "Manage Rules…" does nothing yet (stub). Close the app.

- [ ] **Step 5: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: update rules panel — fix header, remove inline controls, add delegate"
```

---

## Task 3: Add `RulesDialog`

**Files:**
- Modify: `SoundSwitch.py` — insert `RulesDialog` class before `MainWindow` (after `NoiseCancelDialog`)

- [ ] **Step 1: Insert `RulesDialog` class before `MainWindow`**

Insert this class immediately before the `_QT_MOD_TO_XDG` dict (~line 495, or just before `class MainWindow`). Place it after `NoiseCancelDialog`:

```python
class RulesDialog(QDialog):
    def __init__(self, state, save_state_cb, refresh_rules_cb, parent=None):
        super().__init__(parent)
        self.state = state
        self._save_state_cb = save_state_cb
        self._refresh_rules_cb = refresh_rules_cb
        self.setWindowTitle('Manage Auto-Routing Rules')
        self.setModal(True)
        self.setMinimumWidth(500)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        main_row = QHBoxLayout()
        main_row.setSpacing(12)

        left = QVBoxLayout()
        left.addWidget(QLabel('Rules'))
        self._list = QListWidget()
        self._list.setItemDelegate(RuleItemDelegate())
        self._list.setAlternatingRowColors(True)
        self._list.currentRowChanged.connect(self._on_row_changed)
        left.addWidget(self._list)
        main_row.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(8)
        new_btn = QPushButton('New Rule')
        new_btn.clicked.connect(self._new_rule)
        right.addWidget(new_btn)

        right.addWidget(QLabel('App name:'))
        self._app_input = QLineEdit()
        self._app_input.setPlaceholderText('App name e.g. Firefox')
        right.addWidget(self._app_input)

        right.addWidget(QLabel('Route to:'))
        self._sink_combo = QComboBox()
        self._sink_combo.addItems(CUSTOM_SINKS)
        right.addWidget(self._sink_combo)

        btn_row = QHBoxLayout()
        self._save_btn = QPushButton('Save')
        self._save_btn.clicked.connect(self._save_rule)
        self._delete_btn = QPushButton('Delete')
        self._delete_btn.clicked.connect(self._delete_rule)
        self._delete_btn.setEnabled(False)
        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._delete_btn)
        right.addLayout(btn_row)
        right.addStretch()
        main_row.addLayout(right, 2)

        layout.addLayout(main_row)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        bottom_row.addWidget(close_btn)
        layout.addLayout(bottom_row)

        self._refresh_list()

    def _refresh_list(self):
        self._list.clear()
        for rule in self.state.get('rules', []):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, {'app_name': rule['app_name'], 'sink': rule['sink']})
            item.setData(Qt.DisplayRole, f"{rule['app_name']} → {rule['sink']}")
            self._list.addItem(item)

    def _on_row_changed(self, row):
        if row < 0:
            self._delete_btn.setEnabled(False)
            return
        rule = self.state['rules'][row]
        self._app_input.setText(rule['app_name'])
        idx = CUSTOM_SINKS.index(rule['sink']) if rule['sink'] in CUSTOM_SINKS else 0
        self._sink_combo.setCurrentIndex(idx)
        self._delete_btn.setEnabled(True)

    def _new_rule(self):
        self._list.setCurrentRow(-1)
        self._app_input.clear()
        self._sink_combo.setCurrentIndex(0)
        self._delete_btn.setEnabled(False)

    def _save_rule(self):
        app_name = self._app_input.text().strip()
        if not app_name:
            return
        sink = self._sink_combo.currentText()
        row = self._list.currentRow()
        if row >= 0:
            self.state['rules'][row] = {'app_name': app_name, 'sink': sink}
        else:
            self.state['rules'].append({'app_name': app_name, 'sink': sink})
        self._save_state_cb()
        self._refresh_rules_cb()
        self._refresh_list()
        self._new_rule()

    def _delete_rule(self):
        row = self._list.currentRow()
        if row < 0:
            return
        del self.state['rules'][row]
        self._save_state_cb()
        self._refresh_rules_cb()
        self._refresh_list()
        self._new_rule()
```

- [ ] **Step 2: Run the app to verify it starts without errors**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 SoundSwitch.py
```

Expected: app opens normally, no tracebacks. "Manage Rules…" still does nothing (stub). Close the app.

- [ ] **Step 3: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add RulesDialog with side-by-side list and form"
```

---

## Task 4: Wire up `open_rules_dialog()` and delete dead code

**Files:**
- Modify: `SoundSwitch.py` — replace stub `open_rules_dialog()`; delete `add_rule_from_ui()` and `remove_selected_rule()`

- [ ] **Step 1: Replace the stub `open_rules_dialog()` with the real implementation**

Find:
```python
    def open_rules_dialog(self):
        pass
```

Replace with:
```python
    def open_rules_dialog(self):
        RulesDialog(self.state, self.save_state, self.refresh_rules_list, parent=self).exec_()
```

- [ ] **Step 2: Delete `add_rule_from_ui()`**

Find and delete this entire method:
```python
    def add_rule_from_ui(self):
        app_name = self.rule_app_input.text().strip()
        sink = self.rule_sink_combo.currentText()
        if not app_name:
            self.show_status('App name required for rule.', error=True)
            return
        self.state['rules'].append({'app_name': app_name, 'sink': sink})
        self.save_state()
        self.refresh_rules_list()
        self.rule_app_input.clear()
        self.apply_routing_rules()
```

- [ ] **Step 3: Delete `remove_selected_rule()`**

Find and delete this entire method:
```python
    def remove_selected_rule(self):
        row = self.rules_list.currentRow()
        if row >= 0 and row < len(self.state['rules']):
            del self.state['rules'][row]
            self.save_state()
            self.refresh_rules_list()
```

- [ ] **Step 4: Run the app and fully verify**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate && python3 SoundSwitch.py
```

Check each of the following:

1. **Header:** "Auto-Routing Rules" header matches the size and spacing of "Application Streams" — same font size, same gap above the list.
2. **Rule display:** Rules in the main panel show `"If audio stream is Firefox route to Aux"` with "Firefox" and "Aux" rendered cyan and bold.
3. **Single button:** Only "Manage Rules…" appears below the rules list; no text fields or dropdowns visible.
4. **Open dialog:** Click "Manage Rules…" — dialog opens titled "Manage Auto-Routing Rules" with existing rules in the left list (cyan+bold highlighting) and a blank form on the right. Delete button is disabled.
5. **Select rule:** Click a rule — app name and sink populate the form. Delete button enables.
6. **Edit rule:** Change the app name, click Save — rule updates in the dialog list AND in the main window list. Form clears.
7. **New Rule button:** Click New Rule — form clears, list deselects, Delete disables.
8. **Add rule:** With blank form, type an app name, pick a sink, click Save — new rule appears in both lists.
9. **Delete rule:** Select a rule, click Delete — rule removed from both lists. Form clears.
10. **Close:** Click Close — dialog closes. Main window rules list reflects all changes.
11. **Routing still works:** Drag a matching stream to verify auto-routing rules still apply correctly.

- [ ] **Step 5: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: wire RulesDialog to main window, remove dead rule editing code"
```

---

## Self-Review Checklist

- [x] **Spec §1 — Header alignment:** Task 2 Step 1 sets `setContentsMargins(0, 8, 0, 0)` and `margin-bottom: 8px`.
- [x] **Spec §1 — Header font size:** Task 2 Step 1 changes to `QFont('', 12, QFont.Bold)`.
- [x] **Spec §1 — Single button:** Task 2 Step 1 removes inline controls, adds `manage_rules_btn`.
- [x] **Spec §2 — RulesDialog layout:** Task 3 implements side-by-side list + form with all specified controls.
- [x] **Spec §2 — Interaction flow:** `_on_row_changed`, `_new_rule`, `_save_rule`, `_delete_rule` implement the full interaction spec.
- [x] **Spec §2 — Delete disabled initially:** `self._delete_btn.setEnabled(False)` set at init.
- [x] **Spec §3 — RuleItemDelegate:** Task 1 implements all four text segments with correct colors and weights.
- [x] **Spec §3 — Used in both lists:** `RuleItemDelegate` applied to `self.rules_list` (Task 2) and `self._list` in `RulesDialog` (Task 3).
- [x] **Spec §4 — Data flow:** `RulesDialog` takes `save_state_cb` and `refresh_rules_cb` and calls both on every mutation, plus its own `_refresh_list()`.
- [x] **Spec §4 — Dead code deleted:** `add_rule_from_ui()` and `remove_selected_rule()` deleted in Task 4.
- [x] **Type consistency:** `Qt.UserRole` used consistently in `refresh_rules_list()`, `RulesDialog._refresh_list()`, and `RuleItemDelegate.paint()`. `CUSTOM_SINKS` referenced consistently. No name mismatches.
