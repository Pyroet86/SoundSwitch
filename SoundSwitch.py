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

STATE_FILE = 'routing_state.json'
CUSTOM_SINKS = ['Game', 'Media', 'Chat', 'Aux']

class DraggableListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet('QListWidget { padding: 8px; }')

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item:
            drag = QtGui.QDrag(self)
            mime = QtCore.QMimeData()
            mime.setText(item.text())
            mime.setData('application/x-sink-input-index', str(item.data(Qt.ItemDataRole.UserRole)).encode())
            drag.setMimeData(mime)
            drag.exec_(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('application/x-sink-input-index'):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat('application/x-sink-input-index'):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        super().dropEvent(event)

class SinkDropListWidget(QListWidget):
    def __init__(self, sink_name, move_sink_input_callback, parent=None):
        super().__init__(parent)
        self.sink_name = sink_name
        self.setAcceptDrops(True)
        self.move_sink_input_callback = move_sink_input_callback
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet('QListWidget { padding: 8px; }')
        self._drag_over_row = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('application/x-sink-input-index'):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat('application/x-sink-input-index'):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat('application/x-sink-input-index'):
            sink_input_index = bytes(event.mimeData().data('application/x-sink-input-index')).decode()
            self.move_sink_input_callback(sink_input_index, self.sink_name)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def dragLeaveEvent(self, event):
        super().dragLeaveEvent(event)

class RoundedBoxDelegate(QStyledItemDelegate):
    def __init__(self, highlight_selected=False, default_sink_name=None, padding=10, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.highlight_selected = highlight_selected
        self.default_sink_name = default_sink_name
        self.padding = padding

    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect.adjusted(4, 4, -4, -4)
        radius = 10
        # Get main and subtitle text
        data = index.data(Qt.UserRole + 1)
        if data and isinstance(data, dict):
            main_text = data.get('main', index.data(Qt.DisplayRole))
            sub_text = data.get('sub', '')
        else:
            main_text = index.data(Qt.DisplayRole)
            sub_text = ''
        text = main_text
        is_default = False
        if self.default_sink_name and self.default_sink_name in text:
            is_default = True
        # Background and border color
        if is_default:
            bg = QColor('#003366')
            border = QColor('#00bfff')
        elif option.state & QStyle.State_Selected and self.highlight_selected:
            bg = QColor('#00bfff')
            border = QColor('#fff')
        elif option.state & QStyle.State_Selected:
            bg = QColor('#005f87')
            border = QColor('#fff')
        elif option.state & QStyle.State_MouseOver:
            bg = QColor('#2d4157')
            border = QColor('#444')
        else:
            bg = QColor('#232629') if index.row() % 2 == 0 else QColor('#2d2f31')
            border = QColor('#444')
        # Draw rounded rect
        painter.setRenderHint(painter.Antialiasing)
        painter.setBrush(bg)
        painter.setPen(border)
        painter.drawRoundedRect(rect, radius, radius)
        # Draw main text
        painter.setPen(QColor('#f0f0f0'))
        font = option.font
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(rect.adjusted(self.padding, 2, -self.padding, -2), Qt.AlignTop | Qt.AlignLeft, main_text)
        # Draw subtitle (media name)
        if sub_text:
            font.setPointSize(8)
            font.setItalic(True)
            painter.setFont(font)
            painter.setPen(QColor('#b0b0b0'))
            painter.drawText(rect.adjusted(self.padding, 20, -self.padding, -2), Qt.AlignTop | Qt.AlignLeft, sub_text)
        painter.restore()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        # If subtitle present, make it taller
        data = index.data(Qt.UserRole + 1)
        if data and isinstance(data, dict) and data.get('sub'):
            return base.expandedTo(QtCore.QSize(base.width(), 48))
        return base.expandedTo(QtCore.QSize(base.width(), 36))

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
                   Qt.Key_Meta, Qt.Key_AltGr,
                   Qt.Key_Super_L, Qt.Key_Super_R,
                   Qt.Key_Hyper_L, Qt.Key_Hyper_R,
                   Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock):
            return
        if key == Qt.Key_Escape:
            self.setText(self._previous)
            self._capturing = False
            return
        if event.modifiers() == Qt.NoModifier:
            return
        seq = QKeySequence(int(event.modifiers()) | key)
        self.setText(seq.toString())
        self._capturing = False

    def focusOutEvent(self, event):
        if self._capturing:
            self.setText(self._previous)
            self._capturing = False
        super().focusOutEvent(event)


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

        info = QLabel(
            'Set your preferred key combinations below, then click Apply.\n'
            'KDE will show a shortcut confirmation dialog — accept it to activate the new bindings.'
        )
        info.setWordWrap(True)
        info.setStyleSheet('color: #aaa; font-size: 11px;')
        layout.addWidget(info)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        for col, text in enumerate(['Sink', 'Volume \u2191 Up', 'Volume \u2193 Down']):
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
        for key_id, edit in self._captures.items():
            if not edit.text().strip():
                edit.setText(self.DEFAULT_HOTKEYS[key_id])
        hotkeys = {key_id: edit.text() for key_id, edit in self._captures.items()}
        old_hotkeys = self.state.get('hotkeys')
        old_step = self.state.get('volume_step')
        self.state['hotkeys'] = hotkeys
        self.state['volume_step'] = self._step_spin.value()
        try:
            self.on_apply(hotkeys, self._step_spin.value())
        except Exception:
            self.state['hotkeys'] = old_hotkeys
            self.state['volume_step'] = old_step
            raise
        self.accept()

    def _reset(self):
        for key_id, edit in self._captures.items():
            edit.setText(self.DEFAULT_HOTKEYS[key_id])
        self._step_spin.setValue(5)

_QT_MOD_TO_XDG = {
    'ctrl':  '<Control>',
    'alt':   '<Alt>',
    'shift': '<Shift>',
    'meta':  '<Super>',
}

_dbus_main_loop_initialized = False


class GlobalShortcutsManager(QtCore.QObject):
    """Registers and handles global shortcuts via the XDG GlobalShortcuts portal."""

    shortcut_activated = QtCore.pyqtSignal(str)  # emits shortcut_id

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
        self._pending_hotkeys = None

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
            if self._glib_loop:
                self._glib_loop.quit()
            self._glib_loop = None
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
        session_handle = str(results.get('session_handle', ''))
        if not session_handle:
            return
        self._session_handle = session_handle
        # Subscribe to Activated on the portal object (filtered by session_handle
        # inside the callback).
        self._bus.add_signal_receiver(
            self._on_activated,
            signal_name='Activated',
            dbus_interface=self.PORTAL_IFACE,
            path=self.PORTAL_PATH,
        )
        if self._pending_hotkeys is not None:
            self.bind_shortcuts(self._pending_hotkeys)

    def bind_shortcuts(self, hotkeys):
        """Register all shortcuts with the portal. hotkeys is a dict of
        {shortcut_id: Qt-format key string}, e.g. {'Game_up': 'Ctrl+Alt+1'}.
        If the session is not yet established, the hotkeys are queued and
        registered automatically when the session becomes ready."""
        if not self._session_handle:
            self._pending_hotkeys = hotkeys
            return
        self._pending_hotkeys = None
        shortcuts = dbus.Array(
            [
                (
                    dbus.String(key_id),
                    dbus.Dictionary(
                        {
                            'description': dbus.String(self._description(key_id)),
                            'preferred_trigger': dbus.String(self._qt_to_xdg_trigger(trigger)),
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


    def _description(self, key_id):
        sink, direction = key_id.split('_', 1)
        return f'{sink} Volume {direction.title()}'

    def _qt_to_xdg_trigger(self, qt_key):
        """Convert Qt key sequence string to XDG accelerator format.
        e.g. 'Ctrl+Alt+1' -> '<Control><Alt>1'"""
        parts = [p.strip() for p in qt_key.split('+')]
        result = ''
        for p in parts[:-1]:
            result += _QT_MOD_TO_XDG.get(p.lower(), f'<{p}>')
        result += parts[-1]
        return result

    def _on_activated(self, session_handle, shortcut_id, timestamp, options):
        if str(session_handle) == self._session_handle:
            self.shortcut_activated.emit(str(shortcut_id))

    def restart(self, hotkeys):
        """Destroy the current portal session and start a fresh one.

        Creating a new session causes KDE to treat the shortcuts as new
        registrations, so it will show its shortcut confirmation dialog with
        the supplied preferred_trigger values pre-filled, letting the user
        accept or adjust the new bindings.

        Returns True if the new session started successfully."""
        if self._glib_loop:
            self._glib_loop.quit()
        self._bus = None
        self._portal = None
        self._session_handle = None
        self._glib_loop = None
        self._available = False
        self._pending_hotkeys = hotkeys
        return self.start()

    @property
    def is_available(self):
        return self._available

    def stop(self):
        if self._glib_loop:
            self._glib_loop.quit()


class MainWindow(QMainWindow):
    def __init__(self, start_minimized=False):
        super().__init__()
        self.setWindowTitle('SoundSwitch - PipeWire Audio Router')
        self.setWindowIcon(QIcon.fromTheme('audio-card'))
        self.resize(1000, 600)
        self.init_menu_bar()
        self.tray_icon = None
        self.tray_menu = None
        self.is_hidden_to_tray = False
        self.state = self.load_state()
        if 'rules' not in self.state:
            self.state['rules'] = [
                {'app_name': 'Firefox', 'sink': 'Aux'}
            ]
        if 'manual_overrides' not in self.state:
            self.state['manual_overrides'] = {}
        if 'volume_step' not in self.state:
            self.state['volume_step'] = 5
        if 'hotkeys' not in self.state:
            self.state['hotkeys'] = dict(HotkeySettingsDialog.DEFAULT_HOTKEYS)
        self._last_snapshot = None
        self.hidden_sinks = set(CUSTOM_SINKS)
        self.hidden_streams = set()  # Will be populated with loopback stream indices
        self.init_ui()
        self.ensure_custom_sinks()
        self.restore_routing_state()
        self.refresh_devices_and_sinks(force=True)
        # Auto-refresh every 2 seconds
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.conditional_refresh)
        self.refresh_timer.start(2000)
        # Dark theme palette
        self.apply_dark_theme()
        self.statusBar().showMessage('Ready')
        self.init_tray_icon()
        self._shortcuts_manager = GlobalShortcutsManager(self)
        if self._shortcuts_manager.start():
            self._shortcuts_manager.shortcut_activated.connect(self._on_shortcut_activated)
            self._shortcuts_manager.bind_shortcuts(self.state.get('hotkeys', GlobalShortcutsManager.DEFAULT_HOTKEYS))
        else:
            self.show_status('Global hotkeys unavailable: xdg-desktop-portal-kde not running', error=True)
        if start_minimized:
            self.hide_to_tray()

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

    def apply_dark_theme(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor('#232629'))
        dark_palette.setColor(QPalette.WindowText, QColor('#f0f0f0'))
        dark_palette.setColor(QPalette.Base, QColor('#232629'))
        dark_palette.setColor(QPalette.AlternateBase, QColor('#2d2f31'))
        dark_palette.setColor(QPalette.ToolTipBase, QColor('#232629'))
        dark_palette.setColor(QPalette.ToolTipText, QColor('#f0f0f0'))
        dark_palette.setColor(QPalette.Text, QColor('#f0f0f0'))
        dark_palette.setColor(QPalette.Button, QColor('#232629'))
        dark_palette.setColor(QPalette.ButtonText, QColor('#f0f0f0'))
        dark_palette.setColor(QPalette.BrightText, QColor('#ff3333'))
        dark_palette.setColor(QPalette.Highlight, QColor('#005f87'))
        dark_palette.setColor(QPalette.HighlightedText, QColor('#ffffff'))
        self.setPalette(dark_palette)
        self.setStyleSheet('QStatusBar { background: #232629; color: #f0f0f0; } QLabel { color: #f0f0f0; } QPushButton { background: #2d2f31; color: #f0f0f0; border: 1px solid #444; border-radius: 4px; padding: 4px 8px; } QPushButton:hover { background: #005f87; color: #fff; }')

    def show_status(self, message, error=False):
        bar = self.statusBar() if hasattr(self, 'statusBar') else None
        if bar:
            bar.setStyleSheet('color: #ff3333;' if error else 'color: #f0f0f0;')
            bar.showMessage(message, 4000)

    def update_status_bar(self):
        """Update the status bar with current system state"""
        try:
            sinks = self.get_sinks()
            sink_inputs = self.get_sink_inputs()
            default_sink = self.get_default_sink_name()
            
            # Count active streams
            active_streams = len([s for s in sink_inputs if s['index'] not in self.hidden_streams])
            
            # Count available sinks
            available_sinks = len([s for s in sinks if s['name'] not in self.hidden_sinks])
            
            # Count active rules
            active_rules = len(self.state.get('rules', []))
            
            # Build status message
            status_parts = []
            status_parts.append(f"Streams: {active_streams}")
            status_parts.append(f"Sinks: {available_sinks}")
            status_parts.append(f"Rules: {active_rules}")
            if default_sink:
                status_parts.append(f"Default: {default_sink}")
            
            status_message = " | ".join(status_parts)
            
            # Update status bar
            bar = self.statusBar() if hasattr(self, 'statusBar') else None
            if bar:
                bar.setStyleSheet('color: #f0f0f0;')
                bar.showMessage(status_message, 0)  # 0 = permanent message
                
        except Exception as e:
            # If there's an error, show a simple status
            bar = self.statusBar() if hasattr(self, 'statusBar') else None
            if bar:
                bar.setStyleSheet('color: #ff3333;')
                bar.showMessage(f"Status update error: {str(e)}", 5000)

    def conditional_refresh(self):
        # Only refresh UI if state has changed
        sinks = self.get_sinks()
        sink_inputs = self.get_sink_inputs()
        default_sink = self.get_default_sink_name()
        # Build a snapshot: sorted sinks, sorted streams with routing, default sink
        snapshot = (
            tuple(sorted((s['index'], s['name']) for s in sinks)),
            tuple(sorted((s['index'], s.get('sink'), s.get('app_name'), s.get('media_name')) for s in sink_inputs)),
            default_sink
        )
        if snapshot != self._last_snapshot:
            self.refresh_devices_and_sinks(force=True)
            self._last_snapshot = snapshot

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Devices panel
        devices_panel = QVBoxLayout()
        devices_label = QLabel('Application Streams')
        devices_label.setFont(QFont('', 12, QFont.Bold))
        devices_label.setStyleSheet('margin-bottom: 8px;')
        self.devices_list = DraggableListWidget()
        self.devices_list.setItemDelegate(RoundedBoxDelegate())
        self.devices_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.devices_list.customContextMenuRequested.connect(self.show_stream_context_menu)
        devices_panel.addWidget(devices_label)
        devices_panel.addWidget(self.devices_list)
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.clicked.connect(lambda: self.refresh_devices_and_sinks(force=True))
        devices_panel.addWidget(self.refresh_btn)
        devices_panel.addSpacing(10)

        # Rules panel
        rules_label = QLabel('Auto-Routing Rules')
        rules_label.setFont(QFont('', 11, QFont.Bold))
        rules_label.setStyleSheet('margin-bottom: 4px;')
        devices_panel.addWidget(rules_label)
        self.rules_list = QListWidget()
        self.rules_list.setAlternatingRowColors(True)
        self.rules_list.setSelectionMode(QListWidget.SingleSelection)
        self.rules_list.setStyleSheet('QListWidget { padding: 4px; }')
        devices_panel.addWidget(self.rules_list)
        # Add rule controls
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
        devices_panel.addLayout(rule_controls)
        devices_panel.addSpacing(10)

        # Sinks panel (now stacked vertically)
        sinks_panel = QVBoxLayout()
        sinks_label = QLabel('Audio Sinks')
        sinks_label.setFont(QFont('', 12, QFont.Bold))
        sinks_label.setStyleSheet('margin-bottom: 4px;')
        sinks_panel.addWidget(sinks_label)
        self.sink_lists = {}
        for sink in CUSTOM_SINKS:
            vbox = QVBoxLayout()
            vbox.setSpacing(0)
            label = QLabel(sink)
            label.setAlignment(Qt.AlignCenter)
            label.setFont(QFont('', 11, QFont.Bold))
            label.setStyleSheet('margin: 0px; padding: 0px;')
            vbox.addWidget(label)
            sink_list = SinkDropListWidget(sink, self.move_sink_input)
            sink_list.setItemDelegate(RoundedBoxDelegate(padding=12))
            sink_list.setStyleSheet('QListWidget { margin: 0px; padding: 0px; border: none; }')
            # Fixed height for 5 items
            option = QStyleOptionViewItem()
            item_height = sink_list.itemDelegate().sizeHint(option, sink_list.model().index(0, 0)).height() if sink_list.itemDelegate() else 36
            visible_items = 5
            total_height = visible_items * item_height + 8
            sink_list.setMinimumHeight(total_height)
            sink_list.setMaximumHeight(total_height)
            sink_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            vbox.addWidget(sink_list)
            self.sink_lists[sink] = sink_list
            sinks_panel.addLayout(vbox)
        sinks_panel.addSpacing(0)

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

    def run_pactl(self, args):
        try:
            result = subprocess.run(['pactl'] + args, capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            QMessageBox.warning(self, 'pactl Error', f'Failed to run pactl {args}: {e.stderr}')
            return ''

    def ensure_custom_sinks(self):
        # Get current sinks
        sinks = self.get_sinks()
        existing_sink_names = [sink['name'] for sink in sinks]
        for sink in CUSTOM_SINKS:
            if sink not in existing_sink_names:
                # Create null sink
                self.run_pactl(['load-module', 'module-null-sink', f'sink_name={sink}', f'sink_properties=device.description={sink}'])

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

    def get_sinks(self):
        # Returns a list of dicts with 'index', 'name', 'description'
        output = self.run_pactl(['list', 'short', 'sinks'])
        sinks = []
        for line in output.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                sinks.append({'index': parts[0], 'name': parts[1], 'description': parts[1]})
        return sinks

    def get_sink_inputs(self):
        # Returns a list of dicts with 'index', 'name', 'app_name', 'sink'
        output = self.run_pactl(['list', 'sink-inputs'])
        inputs = []
        current = {}
        for line in output.splitlines():
            line = line.strip()
            if line.startswith('Sink Input #'):
                if current:
                    inputs.append(current)
                current = {'index': line.split('#')[1].strip()}
            elif line.startswith('application.name = '):
                current['app_name'] = line.split('=', 1)[1].strip().strip('"')
            elif line.startswith('media.name = '):
                current['media_name'] = line.split('=', 1)[1].strip('"')
            elif line.startswith('Sink:'):
                current['sink'] = line.split(':', 1)[1].strip()
        if current:
            inputs.append(current)
        return inputs

    def get_default_sink_name(self):
        # Get the current default sink name using pactl info
        output = self.run_pactl(['info'])
        for line in output.splitlines():
            if line.startswith('Default Sink:'):
                return line.split(':', 1)[1].strip()
        return None

    def restore_routing_state(self):
        # Restore default sink
        default_sink = self.state.get('default_sink')
        if default_sink:
            self.run_pactl(['set-default-sink', default_sink])
        # Restore loopbacks for custom sinks
        if 'loopbacks' in self.state and default_sink:
            self.setup_custom_sink_loopbacks(default_sink)

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

    def setup_custom_sink_loopbacks(self, hardware_sink_name):
        # Track loopback module IDs in self.state['loopbacks']
        if 'loopbacks' not in self.state:
            self.state['loopbacks'] = {}
        # Get all loaded modules
        modules = self.get_loaded_modules()
        # Remove previous loopbacks for our custom sinks
        for custom_sink in CUSTOM_SINKS:
            # Remove any loopback from custom_sink.monitor to any sink
            for mod_id, mod_info in list(self.state['loopbacks'].get(custom_sink, {}).items()):
                if self.is_module_loaded(mod_id, modules):
                    self.run_pactl(['unload-module', str(mod_id)])
            self.state['loopbacks'][custom_sink] = {}
        # Create new loopbacks from each custom sink's monitor to the selected hardware sink
        for custom_sink in CUSTOM_SINKS:
            source = f'{custom_sink}.monitor'
            sink = hardware_sink_name
            # Load loopback
            out = self.run_pactl(['load-module', 'module-loopback', f'source={source}', f'sink={sink}'])
            try:
                mod_id = int(out.strip())
                self.state['loopbacks'][custom_sink][mod_id] = {'source': source, 'sink': sink}
            except Exception:
                pass
        self.save_state()

    def get_loaded_modules(self):
        output = self.run_pactl(['list', 'short', 'modules'])
        modules = {}
        for line in output.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                modules[parts[0]] = parts[1]
        return modules

    def is_module_loaded(self, mod_id, modules):
        return str(mod_id) in modules

    def update_hidden_streams(self, sink_inputs):
        # Hide loopback streams created by this app (by property or app name)
        loopback_indices = set()
        for stream in sink_inputs:
            app_name = stream.get('app_name', '').lower()
            media_name = stream.get('media_name', '').lower()
            # Heuristic: hide if app_name is 'pipewire', 'pulseaudio', or media_name contains 'loopback'
            if 'loopback' in media_name or app_name in {'pipewire', 'pulseaudio'}:
                loopback_indices.add(stream['index'])
        # Also hide any indices tracked in state['loopbacks']
        if 'loopbacks' in self.state:
            for sink_loopbacks in self.state['loopbacks'].values():
                for mod in sink_loopbacks.values():
                    idx = mod.get('stream_index')
                    if idx:
                        loopback_indices.add(str(idx))
        self.hidden_streams = loopback_indices

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

    def apply_routing_rules(self):
        sinks = self.get_sinks()
        sink_inputs = self.get_sink_inputs()
        self.update_hidden_streams(sink_inputs)
        sink_index_to_name = {sink['index']: sink['name'] for sink in sinks}
        for rule in self.state.get('rules', []):
            for stream in sink_inputs:
                if stream['index'] in self.hidden_streams:
                    continue
                # Skip if manual override exists and matches current sink
                if str(stream['index']) in self.state.get('manual_overrides', {}):
                    if self.state['manual_overrides'][str(stream['index'])] == stream.get('sink_name'):
                        continue
                sink_index = stream.get('sink', None)
                sink_name = sink_index_to_name.get(sink_index, 'Unknown') if sink_index else 'Unknown'
                if stream.get('app_name', '').lower() == rule['app_name'].lower() and sink_name != rule['sink']:
                    self.run_pactl(['move-sink-input', str(stream['index']), rule['sink']])
                    self.show_status(f"Auto-moved {stream['app_name']} (#{stream['index']}) to {rule['sink']}")
        
        # Update status bar after applying rules
        self.update_status_bar()

    def remove_selected_rule(self):
        row = self.rules_list.currentRow()
        if row >= 0 and row < len(self.state['rules']):
            del self.state['rules'][row]
            self.save_state()
            self.refresh_rules_list()

    def refresh_rules_list(self):
        self.rules_list.clear()
        for rule in self.state['rules']:
            item = QListWidgetItem(f"If app is '{rule['app_name']}' → {rule['sink']}")
            self.rules_list.addItem(item)

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

    def reset_manual_override(self, stream_index):
        if stream_index in self.state['manual_overrides']:
            del self.state['manual_overrides'][stream_index]
            self.save_state()
            self.refresh_devices_and_sinks(force=True)
            self.show_status(f'Reset manual override for stream #{stream_index}')

    def refresh_devices_and_sinks(self, force=False):
        if not force:
            return
        self.devices_list.clear()
        self.outputs_list.clear()
        for sink_list in getattr(self, 'sink_lists', {}).values():
            sink_list.clear()
        sinks = self.get_sinks()
        sink_inputs = self.get_sink_inputs()
        self.update_hidden_streams(sink_inputs)
        sink_index_to_name = {sink['index']: sink['name'] for sink in sinks}
        sink_map = {sink['name']: [] for sink in sinks}
        for stream in sink_inputs:
            sink_index = stream.get('sink', None)
            sink_name = sink_index_to_name.get(sink_index, 'Unknown') if sink_index else 'Unknown'
            if sink_name in sink_map:
                sink_map[sink_name].append(stream)
            stream['sink_name'] = sink_name
        # Clean up manual overrides for streams that no longer exist
        current_indices = {str(s['index']) for s in sink_inputs}
        to_remove = [idx for idx in self.state['manual_overrides'] if idx not in current_indices]
        for idx in to_remove:
            del self.state['manual_overrides'][idx]
        self.save_state()
        # Auto-routing logic
        self.apply_routing_rules()
        # Application Streams panel: show current sink for each stream, skip hidden
        for i, stream in enumerate([s for s in sink_inputs if s['index'] not in self.hidden_streams]):
            main_label = f"{stream.get('app_name', 'Unknown App')} (#{stream['index']}) - {stream.get('sink_name', 'Unknown')}"
            sub_label = stream.get('media_name', '')
            item = QListWidgetItem()
            item.setData(Qt.DisplayRole, main_label)
            item.setData(Qt.UserRole + 1, {'main': main_label, 'sub': sub_label})
            item.setData(Qt.ItemDataRole.UserRole, stream['index'])
            item.setToolTip(f"App: {stream.get('app_name', 'Unknown App')}\nSink: {stream.get('sink_name', 'Unknown')}\nMedia: {stream.get('media_name', '')}")
            # Dark alternating row colors
            if i % 2 == 0:
                item.setBackground(QBrush(QColor('#232629')))
            else:
                item.setBackground(QBrush(QColor('#2d2f31')))
            self.devices_list.addItem(item)
        # Sinks panel: show each sink's streams in its own list, skip hidden streams
        for sink in CUSTOM_SINKS:
            sink_list = self.sink_lists[sink]
            sink_list.clear()
            streams = [s for s in sink_map.get(sink, []) if s['index'] not in self.hidden_streams]
            for j, stream in enumerate(streams):
                main_label = f"{stream.get('app_name', 'Unknown App')} (#{stream['index']})"
                sub_label = stream.get('media_name', '')
                stream_item = QListWidgetItem()
                stream_item.setData(Qt.DisplayRole, main_label)
                stream_item.setData(Qt.UserRole + 1, {'main': main_label, 'sub': sub_label})
                stream_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                stream_item.setToolTip(f"App: {stream.get('app_name', 'Unknown App')}\nMedia: {stream.get('media_name', '')}")
                # Dark alternating row colors
                if j % 2 == 0:
                    stream_item.setBackground(QBrush(QColor('#232629')))
                else:
                    stream_item.setBackground(QBrush(QColor('#2d2f31')))
                sink_list.addItem(stream_item)
            # Placeholder for empty list
            if sink_list.count() == 0:
                placeholder = QListWidgetItem('(No streams)')
                placeholder.setFlags(Qt.NoItemFlags)
                placeholder.setForeground(QBrush(QColor('#555')))
                sink_list.addItem(placeholder)
        # Outputs panel: show all sinks (hardware and custom), highlight default, skip hidden sinks
        if hasattr(self, 'outputs_delegate'):
            self.outputs_delegate.default_sink_name = self.get_default_sink_name()
        for i, sink in enumerate([s for s in sinks if s['name'] not in self.hidden_sinks]):
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
        # Refresh rules list
        self.refresh_rules_list()
        
        # Update status bar
        self.update_status_bar()

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                QMessageBox.warning(self, 'Error', f'Failed to load state: {e}')
        return {}

    def save_state(self):
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            QMessageBox.warning(self, 'Error', f'Failed to save state: {e}')

    def init_tray_icon(self):
        icon = QIcon.fromTheme('audio-card')
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_menu = QMenu()
        self.action_show = QAction('Show', self)
        self.action_show.triggered.connect(self.show_from_tray)
        self.action_hide = QAction('Hide', self)
        self.action_hide.triggered.connect(self.hide_to_tray)
        self.action_exit = QAction('Exit', self)
        self.action_exit.triggered.connect(self.close)
        self.tray_menu.addAction(self.action_show)
        self.tray_menu.addAction(self.action_hide)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.action_exit)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.setToolTip('SoundSwitch - PipeWire Audio Router')
        self.tray_icon.show()

    def hide_to_tray(self):
        self.hide()
        self.is_hidden_to_tray = True
        self.tray_icon.showMessage('SoundSwitch', 'SoundSwitch is running in the system tray.', QSystemTrayIcon.Information, 2000)

    def show_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.is_hidden_to_tray = False

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isHidden() or self.is_hidden_to_tray:
                self.show_from_tray()
            else:
                self.hide_to_tray()

    def closeEvent(self, event):
        self.save_state()
        if hasattr(self, '_shortcuts_manager'):
            self._shortcuts_manager.stop()
        if self.tray_icon:
            self.tray_icon.hide()
        super().closeEvent(event)

    def move_sink_input(self, sink_input_index, sink_name):
        # Move the sink input to the selected sink
        result = self.run_pactl(['move-sink-input', str(sink_input_index), sink_name])
        if result is not None:
            # Track manual override
            self.state.setdefault('manual_overrides', {})[str(sink_input_index)] = sink_name
            self.save_state()
            self.show_status(f'Moved stream #{sink_input_index} to sink {sink_name}')
        else:
            self.show_status(f'Failed to move stream #{sink_input_index} to sink {sink_name}', error=True)
        self.refresh_devices_and_sinks(force=True)

    def set_sink_volume(self, sink_name, direction):
        step = self.state.get('volume_step', 5)
        delta = f'+{step}%' if direction == 'up' else f'-{step}%'
        self.run_pactl(['set-sink-volume', sink_name, delta])
        self.show_status(f'{sink_name} volume {direction} ({delta})')

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
            if self._shortcuts_manager.is_available:
                ok = self._shortcuts_manager.restart(hotkeys)
                if ok:
                    self.show_status('Hotkey settings saved — accept the KDE shortcut dialog to activate.')
                else:
                    self.show_status('Settings saved — could not restart shortcut session.', error=True)
            else:
                self.show_status('Settings saved — hotkeys inactive (portal unavailable).', error=True)
        HotkeySettingsDialog(self.state, on_apply, parent=self).exec_()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--minimized', action='store_true', help='Start minimized to tray')
    args = parser.parse_args()
    app = QApplication(sys.argv)
    window = MainWindow(start_minimized=args.minimized)
    if not args.minimized:
        window.show()
    sys.exit(app.exec_())
