import sys
import re
import threading
import uuid
import subprocess
import json
import os
import autostart
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QLabel, QPushButton, QListWidgetItem, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QLineEdit,
    QComboBox, QMenu, QSystemTrayIcon, QAction, QDialog,
    QSpinBox, QCheckBox, QSplitter,
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QIcon, QColor, QBrush, QPalette, QPainter, QPixmap, QPen, QPainterPath
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


class VolumeOSD(QWidget):
    """Non-focus-stealing on-screen display for volume changes."""

    _MARGIN = 20
    _FADE_MS = 400

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint |
                         Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus |
                         Qt.X11BypassWindowManagerHint)
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
        self._hide_timer.start(int(duration * 1000))

    def _start_fade(self):
        # QTimer.timeout cannot connect directly to QPropertyAnimation.start
        # because start() is overloaded; this wrapper resolves the ambiguity.
        self._anim.start()

    def _position_on_screen(self, position):
        screen = QApplication.primaryScreen()
        if screen is None:
            self.move(0, 0)
            return
        sg = screen.geometry()
        w, h = self.width(), self.height()
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


class HotkeySettingsDialog(QDialog):

    def __init__(self, state, on_apply, parent=None):
        super().__init__(parent)
        self.state = state
        self.on_apply = on_apply
        self.setWindowTitle('Hotkey Settings')
        self.setModal(True)
        self.setMinimumWidth(320)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        info = QLabel('Shortcut keys are managed by KDE.')
        info.setStyleSheet('color: #aaa; font-size: 11px;')
        layout.addWidget(info)

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
        reset_btn = QPushButton('Reset shortcuts')
        reset_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _apply(self):
        old_step = self.state.get('volume_step')
        self.state['volume_step'] = self._step_spin.value()
        try:
            self.on_apply(self._step_spin.value())
        except Exception:
            self.state['volume_step'] = old_step
            raise
        self.accept()


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

    def _on_autostart_changed(self, _state):
        enabled = self._autostart_cb.isChecked()
        self._minimized_cb.setEnabled(enabled)
        if enabled:
            autostart.enable(start_minimized=self._minimized_cb.isChecked())
        else:
            autostart.disable()

    def _on_minimized_changed(self, _state):
        if self._autostart_cb.isChecked():
            autostart.enable(start_minimized=self._minimized_cb.isChecked())


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
        self._pending_version = 0

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
            self.bind_shortcuts(self._pending_hotkeys, self._pending_version)

    def bind_shortcuts(self, hotkeys, version=0):
        """Register all shortcuts with the portal. hotkeys is a dict of
        {shortcut_id: Qt-format key string}, e.g. {'Game_up': 'Ctrl+Alt+1'}.
        version is appended to each ID (e.g. 'Game_up_v1') so that changed
        bindings are always treated as new registrations by kwin.
        If the session is not yet established, the hotkeys are queued and
        registered automatically when the session becomes ready."""
        if not self._session_handle:
            self._pending_hotkeys = hotkeys
            self._pending_version = version
            return
        self._pending_hotkeys = None
        shortcuts = dbus.Array(
            [
                (
                    dbus.String(f'{key_id}_v{version}'),
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


    @staticmethod
    def _strip_version(shortcut_id):
        """Remove _vN suffix: 'Game_up_v2' -> 'Game_up'."""
        parts = shortcut_id.rsplit('_v', 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0]
        return shortcut_id

    def _description(self, key_id):
        """Return human-readable description for a shortcut ID (no version suffix)."""
        clean = self._strip_version(key_id)
        sink, direction = clean.split('_', 1)
        arrow = '\u2191' if direction == 'up' else '\u2193'
        return f'{sink} Volume {arrow} {direction.title()}'

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
            self.shortcut_activated.emit(self._strip_version(str(shortcut_id)))

    def restart(self, hotkeys, version):
        """Destroy the current portal session and start a fresh one.

        Using a new version causes kwin to see the shortcut IDs as entirely
        new registrations and apply the preferred_trigger values directly,
        bypassing any cached bindings from the previous version.

        Returns True if the new session started successfully."""
        if self._glib_loop:
            self._glib_loop.quit()
        self._bus = None
        self._portal = None
        self._session_handle = None
        self._glib_loop = None
        self._available = False
        self._pending_hotkeys = hotkeys
        self._pending_version = version
        return self.start()

    @property
    def is_available(self):
        return self._available

    def stop(self):
        if self._glib_loop:
            self._glib_loop.quit()


def create_app_icon():
    """Create a programmatic speaker-with-soundwaves icon in the app's cyan-on-dark colour scheme."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)

    # Dark navy circular background
    p.setBrush(QBrush(QColor('#1e2a3a')))
    p.setPen(QPen(QColor('#2a3f55'), 2))
    p.drawEllipse(2, 2, 60, 60)

    cyan = QColor('#00bfff')

    # Speaker box (left rectangle)
    p.setBrush(QBrush(cyan))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(12, 27, 9, 10, 2, 2)

    # Speaker cone (trapezoid opening to the right)
    cone = QPainterPath()
    cone.moveTo(21, 27)
    cone.lineTo(31, 17)
    cone.lineTo(31, 47)
    cone.lineTo(21, 37)
    cone.closeSubpath()
    p.fillPath(cone, QBrush(cyan))

    # Sound waves: three arcs emanating from the cone opening
    p.setBrush(Qt.NoBrush)
    for i, (offset, alpha, width) in enumerate([(0, 255, 3), (7, 210, 2), (14, 150, 2)]):
        wave_color = QColor('#00bfff')
        wave_color.setAlpha(alpha)
        pen = QPen(wave_color, width, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        margin = 8 + offset
        p.drawArc(31 - margin, 32 - margin, margin * 2, margin * 2, -55 * 16, 110 * 16)

    p.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self, start_minimized=False):
        super().__init__()
        self.setWindowTitle('SoundSwitch - PipeWire Audio Router')
        self.setWindowIcon(create_app_icon())
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
        if 'shortcut_version' not in self.state:
            self.state['shortcut_version'] = 0
        if 'osd_position' not in self.state:
            self.state['osd_position'] = 'bottom-right'
        if 'osd_duration' not in self.state:
            self.state['osd_duration'] = 3
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
        self._osd = VolumeOSD()
        self._shortcuts_manager = GlobalShortcutsManager(self)
        if self._shortcuts_manager.start():
            self._shortcuts_manager.shortcut_activated.connect(self._on_shortcut_activated)
            self._shortcuts_manager.bind_shortcuts(
                GlobalShortcutsManager.DEFAULT_HOTKEYS,
                self.state.get('shortcut_version', 0),
            )
        else:
            self.show_status('Global hotkeys unavailable: xdg-desktop-portal-kde not running', error=True)
        if start_minimized:
            self.hide_to_tray()

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
        right_splitter.setStyleSheet(
            'QSplitter::handle { background: #444; height: 4px; }'
        )

        # Add panels to main layout
        main_layout.addLayout(devices_panel, 2)
        main_layout.addSpacing(16)
        main_layout.addLayout(sinks_panel, 3)
        main_layout.addSpacing(16)
        main_layout.addWidget(right_splitter, 2)

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

    def get_input_sources(self):
        # Uses the top-level Description: field (always present) rather than the
        # nested device.description property, which avoids Properties-block parsing complexity.
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
            elif line.startswith('Description:'):
                current['description'] = line.split(':', 1)[1].strip()
        if current.get('name') and not current['name'].endswith('.monitor'):
            sources.append(current)
        for s in sources:
            s.setdefault('description', s['name'])
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
        action_settings = QAction('Settings…', self)
        action_settings.triggered.connect(self.open_settings)
        self.tray_menu.addAction(action_settings)
        action_hotkey = QAction('Hotkey Settings…', self)
        action_hotkey.triggered.connect(self.open_hotkey_settings)
        self.tray_menu.addAction(action_hotkey)
        action_osd = QAction('OSD Settings…', self)
        action_osd.triggered.connect(self.open_osd_settings)
        self.tray_menu.addAction(action_osd)
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

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.WindowStateChange and self.isMinimized():
            QTimer.singleShot(0, self.hide_to_tray)
        super().changeEvent(event)

    def closeEvent(self, event):
        # Close button hides to tray; only real_close() actually quits.
        event.ignore()
        self.hide_to_tray()

    def real_close(self):
        self.save_state()
        if hasattr(self, '_shortcuts_manager'):
            self._shortcuts_manager.stop()
        if self.tray_icon:
            self.tray_icon.hide()
        QApplication.instance().quit()

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

    def get_sink_volume(self, sink_name):
        """Return current volume of a sink as an integer 0-100, or None on failure."""
        try:
            result = subprocess.run(
                ['pactl', 'get-sink-volume', sink_name],
                capture_output=True, text=True, check=True,
            )
            match = re.search(r'(\d+)%', result.stdout)
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return None

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

    def _on_shortcut_activated(self, shortcut_id):
        parts = shortcut_id.rsplit('_', 1)
        if len(parts) != 2:
            return
        sink_name, direction = parts
        if sink_name not in CUSTOM_SINKS or direction not in ('up', 'down'):
            return
        self.set_sink_volume(sink_name, direction)

    def open_hotkey_settings(self):
        def on_apply(step):
            self.state['shortcut_version'] = self.state.get('shortcut_version', 0) + 1
            self.save_state()
            if self._shortcuts_manager.is_available:
                ok = self._shortcuts_manager.restart(
                    GlobalShortcutsManager.DEFAULT_HOTKEYS,
                    self.state['shortcut_version'],
                )
                if ok:
                    self.show_status('Shortcuts reset to defaults.')
                else:
                    self.show_status('Settings saved — could not restart shortcut session.', error=True)
            else:
                self.show_status('Settings saved — hotkeys inactive (portal unavailable).', error=True)
        HotkeySettingsDialog(self.state, on_apply, parent=self).exec_()

    def open_osd_settings(self):
        def on_apply():
            self.save_state()
        OSDSettingsDialog(self.state, on_apply, parent=self).exec_()

    def open_settings(self):
        SettingsDialog(parent=self).exec_()

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
