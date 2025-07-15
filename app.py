import sys
import json
import subprocess
import re
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QFrame, QListWidget, QListWidgetItem, QScrollArea, QGridLayout)
from PyQt5.QtCore import Qt, QMimeData, QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QDrag, QFont, QColor, QPalette
import os

# PipeWirePoller and dependencies (from subscribe.py)
try:
    from pipewire_python import link  # pip install pipewire_python
except ImportError:
    link = None  # For environments without pipewire_python

USER_ROLE = 32  # Qt.UserRole

class PipeWirePoller(QObject):
    stream_added = pyqtSignal(str, str, str, str)  # id, device, port, type
    stream_removed = pyqtSignal(str)
    app_name_map_updated = pyqtSignal()

    def __init__(self, interval_ms: int = 500, monitor_outputs: bool = True):
        super().__init__()
        self._monitor_outputs = monitor_outputs
        self._active_ids = {}
        self._port_type_map = {}
        self._device_ports = {}

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_once)
        self._timer.start(interval_ms)

        self._app_name_timer = QTimer(self)
        self._app_name_timer.timeout.connect(self._update_app_name_map)
        self._app_name_timer.start(2000)

        self._poll_once()
        self._update_app_name_map()

    def get_device_ports(self):
        return self._device_ports

    def _update_app_name_map(self):
        def parse_pw_link_output(output: str, port_type: str):
            id_to_info = {}
            for line in output.splitlines():
                m = re.match(r'\s*(\d+)\s+([^:]+):([^\s]+)', line)
                if m:
                    port_id, device, port = m.group(1), m.group(2), m.group(3)
                    id_to_info[port_id] = (device, port, port_type)
            return id_to_info
        try:
            if link is None:
                self._device_ports = {}
                self.app_name_map_updated.emit()
                return
            out_o = subprocess.check_output(["pw-link", "-o", "-I"], text=True)
            out_i = subprocess.check_output(["pw-link", "-i", "-I"], text=True)
            id_to_info = parse_pw_link_output(out_o, "output")
            id_to_info.update(parse_pw_link_output(out_i, "input"))
            device_ports = {}
            for port_id, (device, port, port_type) in id_to_info.items():
                if device not in device_ports:
                    device_ports[device] = []
                device_ports[device].append({
                    'id': port_id,
                    'port': port,
                    'type': port_type
                })
                self._port_type_map[port_id] = port_type
            self._device_ports = device_ports
            self.app_name_map_updated.emit()
        except Exception as e:
            self._device_ports = {}
            self.app_name_map_updated.emit()

    def _get_current_ports(self):
        if link is None:
            return []
        if self._monitor_outputs:
            ports = link.list_outputs(pair_stereo=False)
        else:
            ports = link.list_inputs(pair_stereo=False)
        return [p for p in ports if hasattr(p, 'id') and not (hasattr(p, 'is_midi') and getattr(p, 'is_midi', False))]

    def _poll_once(self):
        if link is None:
            return
        current_ports = self._get_current_ports()
        current_ids = {str(getattr(p, 'id', '')) for p in current_ports if getattr(p, 'id', None) is not None}
        for port in current_ports:
            port_id = getattr(port, 'id', None)
            if port_id is None:
                continue
            port_id = str(port_id)
            if port_id not in self._active_ids:
                self._active_ids[port_id] = port
                self.stream_added.emit(
                    port_id,
                    getattr(port, 'device', None) or "Unknown Device",
                    getattr(port, 'name', None) or "Unknown Port",
                    getattr(port, 'type', None) or self._port_type_map.get(port_id, "unknown")
                )
        for lost_id in set(self._active_ids.keys()) - current_ids:
            self.stream_removed.emit(lost_id)
            del self._active_ids[lost_id]

    def emit_all_active_streams(self):
        if link is None:
            return
        current_ports = self._get_current_ports()
        for port in current_ports:
            port_id = getattr(port, 'id', None)
            if port_id is None:
                continue
            port_id = str(port_id)
            self.stream_added.emit(
                port_id,
                getattr(port, 'device', None) or "Unknown Device",
                getattr(port, 'name', None) or "Unknown Port",
                getattr(port, 'type', None) or self._port_type_map.get(port_id, "unknown")
            )

class DraggableLabel(QLabel):
    """
    A custom QLabel that can be dragged and contains metadata.
    """
    # Define a custom MIME type for our data
    MIME_TYPE = 'application/x-draggable-label'
    
    def __init__(self, name, ports_metadata, parent=None, fixed=False):
        super().__init__(name, parent)
        self.ports_metadata = ports_metadata  # List of dicts: [{id, port, type}, ...]
        self.fixed = fixed
        
        self.setText(name)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(180, 40)
        self.setStyleSheet("""
            background-color: #222;
            color: #eee;
            border: 1px solid #444;
            border-radius: 5px;
        """)

        font = QFont("Arial", 10)
        font.setBold(True)
        self.setFont(font)

    def mousePressEvent(self, event):
        """
        Handle the mouse press event to initiate a drag operation.
        """
        if self.fixed:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            mime_data = QMimeData()
            
            # Create a dictionary of the metadata
            metadata = {
                'name': self.text(),
                'ports': self.ports_metadata
            }
            
            # Serialize the dictionary to a JSON string and store in the MIME data
            mime_data.setData(self.MIME_TYPE, json.dumps(metadata).encode('utf-8'))

            drag = QDrag(self)
            drag.setMimeData(mime_data)
            drag.setPixmap(self.grab())
            
            drag.exec_(Qt.DropAction.MoveAction)


class Bucket(QFrame):
    """
    A custom QFrame that acts as a drop target (a "bucket").
    """
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#333"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#eee"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(5)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(self._layout)

        title_label = QLabel(self.name)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #eee;")
        self._layout.addWidget(title_label)
        # Info label for sync device metadata
        self.sync_info_label = QLabel("")
        self.sync_info_label.setStyleSheet("font-size: 10px; color: #b0b0b0;")
        self._layout.addWidget(self.sync_info_label)
        self._layout.addStretch(1)
        self.sync_metadata = None
        self._is_sync_bucket = False

    def set_sync_bucket(self, is_sync):
        self._is_sync_bucket = is_sync

    def set_sync_available(self, available):
        if self._is_sync_bucket:
            if not available:
                self.setEnabled(False)
                self.setStyleSheet("background-color: #222; border: 2px dashed #666;")
            else:
                self.setEnabled(True)
                self.setStyleSheet("")

    def dragEnterEvent(self, event):
        """
        Accept a drag event if the data is of our custom MIME type.
        """
        if hasattr(self, '_is_sync_bucket') and self._is_sync_bucket and not self.isEnabled():
            event.ignore()
            return
        if event.mimeData().hasFormat(DraggableLabel.MIME_TYPE):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        Handle a successful drop event and access the metadata.
        """
        if hasattr(self, '_is_sync_bucket') and self._is_sync_bucket and not self.isEnabled():
            event.ignore()
            return
        if event.mimeData().hasFormat(DraggableLabel.MIME_TYPE):
            source_widget = event.source()
            
            # Get the metadata from the MIME data
            encoded_data = event.mimeData().data(DraggableLabel.MIME_TYPE)
            metadata = json.loads(str(encoded_data, 'utf-8'))
            
            # Only allow the correct sync device in this bucket, or any device in Outputs
            main_window = self.window()
            if main_window is not None and hasattr(main_window, 'SYNC_DEVICES') and self.name in main_window.SYNC_DEVICES:
                expected_device = main_window.SYNC_DEVICES[self.name]
                if metadata['name'] == expected_device:
                    event.ignore()
                    return
            elif self.name != 'Outputs' and not (hasattr(self, '_is_sync_bucket') and self._is_sync_bucket):
                event.ignore()
                return

            # Print the received metadata to demonstrate it works
            print(f"Dropped '{metadata['name']}' into '{self.name}'.")
            for port in metadata.get('ports', []):
                print(f"  - Port ID: {port.get('id')} | Port: {port.get('port')} | Type: {port.get('type')}")
            
            if isinstance(source_widget, DraggableLabel):
                # Remove from any parent (including AvailableItemsFrame or other buckets)
                parent = source_widget.parent()
                if isinstance(parent, QFrame):
                    layout = parent.layout()
                    if layout is not None:
                        layout.removeWidget(source_widget)
                source_widget.setParent(None)
                self._layout.insertWidget(self._layout.count() - 1, source_widget)
                # Update label location in main window
                main_window = self.window()
                if main_window is not None and hasattr(main_window, '_label_locations'):
                    main_window._label_locations[metadata['name']] = self.name
                    if hasattr(main_window, '_save_label_locations'):
                        main_window._save_label_locations()
                event.acceptProposedAction()
        else:
            event.ignore()

class AvailableItemsFrame(QFrame):
    """
    A custom QFrame to hold the initial set of items.
    It also acts as a drop target.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Raised)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#222"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#eee"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._layout = QGridLayout()
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setHorizontalSpacing(10)
        self._layout.setVerticalSpacing(10)
        self._label = QLabel("Available Items (Live PipeWire Devices)")
        self._label.setStyleSheet("color: #eee; font-weight: bold;")
        self._layout.addWidget(self._label, 0, 0, 1, 2)
        self.setLayout(self._layout)
        self._row = 1
        self._col = 0

    def add_label(self, label):
        # Prevent duplicates: only add if not already in this layout
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            if item is not None and item.widget() is label:
                return
        self._layout.addWidget(label, self._row, self._col)
        self._col += 1
        if self._col >= 2:
            self._col = 0
            self._row += 1

    def clear_labels(self):
        # Remove all DraggableLabel widgets
        for i in reversed(range(self._layout.count())):
            item = self._layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if widget is not None and isinstance(widget, DraggableLabel):
                    widget.setParent(None)
        self._row = 1
        self._col = 0

    def dragEnterEvent(self, event):
        """
        Accept drag events.
        """
        if event.mimeData().hasFormat(DraggableLabel.MIME_TYPE):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        Handle the drop of a label back into this frame.
        """
        if event.mimeData().hasFormat(DraggableLabel.MIME_TYPE):
            source_widget = event.source()

            # Get the metadata from the MIME data
            encoded_data = event.mimeData().data(DraggableLabel.MIME_TYPE)
            metadata = json.loads(str(encoded_data, 'utf-8'))
            
            print(f"Returned '{metadata['name']}' to 'Available Items'.")
            for port in metadata.get('ports', []):
                print(f"  - Port ID: {port.get('id')} | Port: {port.get('port')} | Type: {port.get('type')}")
            
            if isinstance(source_widget, DraggableLabel):
                # Remove from any parent (including buckets)
                parent = source_widget.parent()
                if isinstance(parent, QFrame):
                    layout = parent.layout()
                    if layout is not None:
                        layout.removeWidget(source_widget)
                source_widget.setParent(None)
                self.add_label(source_widget)
                # Update label location in main window
                main_window = self.window()
                if main_window is not None and hasattr(main_window, '_label_locations'):
                    main_window._label_locations[metadata['name']] = 'available'
                    if hasattr(main_window, '_save_label_locations'):
                        main_window._save_label_locations()
                event.acceptProposedAction()
        else:
            event.ignore()

class DragDropApp(QMainWindow):
    STATE_FILE = 'bucket_state.json'
    SYNC_DEVICES = {
        'Game': 'GAME',
        'Chat': 'CHAT',
        'Media': 'MEDIA',
        'Aux': 'AUX',
    }
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt5 Drag and Drop with Metadata and PipeWire Monitor")
        self.setGeometry(100, 100, 900, 700)

        # Set dark palette for the main window
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor("#111"))
        dark_palette.setColor(QPalette.ColorRole.WindowText, QColor("#eee"))
        dark_palette.setColor(QPalette.ColorRole.Base, QColor("#222"))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#333"))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#eee"))
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#eee"))
        dark_palette.setColor(QPalette.ColorRole.Text, QColor("#eee"))
        dark_palette.setColor(QPalette.ColorRole.Button, QColor("#222"))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor("#eee"))
        dark_palette.setColor(QPalette.ColorRole.BrightText, QColor("#fff"))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor("#444"))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#fff"))
        self.setPalette(dark_palette)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        main_vlayout = QVBoxLayout()
        main_vlayout.setSpacing(10)
        # --- Top: Drag/Drop area (scrollable) ---
        dragdrop_container = QWidget()
        dragdrop_hlayout = QHBoxLayout(dragdrop_container)
        dragdrop_hlayout.setContentsMargins(0, 0, 0, 0)
        dragdrop_hlayout.setSpacing(0)
        self.source_frame = AvailableItemsFrame()
        dragdrop_hlayout.addWidget(self.source_frame)
        buckets_layout = QHBoxLayout()
        buckets_layout.setSpacing(10)
        self.buckets = []
        bucket_names = ["Outputs", "Game", "Chat", "Media", "Aux"]
        for name in bucket_names:
            bucket = Bucket(name)
            self.buckets.append(bucket)
            buckets_layout.addWidget(bucket)
        dragdrop_hlayout.addLayout(buckets_layout, stretch=1)
        # Wrap dragdrop_container in a QScrollArea
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(dragdrop_container)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        main_vlayout.addWidget(scroll_area, stretch=2)
        # --- Bottom: PipeWire device/port list ---
        self.device_list_label = QLabel(
            "<b>Live PipeWire Devices/Ports</b> (drag labels above to buckets):")
        self.device_list_label.setStyleSheet("color: #b0b0b0; font-weight: bold;")
        main_vlayout.addWidget(self.device_list_label)
        self.device_list_widget = QListWidget()
        self.device_list_widget.setStyleSheet(
            "background-color: #232323; color: #e0e0e0; border: none;")
        main_vlayout.addWidget(self.device_list_widget, stretch=1)
        self.central_widget.setLayout(main_vlayout)
        # --- PipeWire integration ---
        self.pw_monitor = PipeWirePoller(interval_ms=1000, monitor_outputs=True)
        self.pw_monitor.app_name_map_updated.connect(self._refresh_pipewire)
        self._current_labels = []
        self._label_locations = self._load_label_locations()
        self._refresh_pipewire()

    def _save_label_locations(self):
        try:
            with open(self.STATE_FILE, 'w') as f:
                json.dump(self._label_locations, f)
        except Exception as e:
            print(f"[WARN] Could not save bucket state: {e}")

    def _load_label_locations(self):
        if os.path.exists(self.STATE_FILE):
            try:
                with open(self.STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARN] Could not load bucket state: {e}")
        return {}

    def _refresh_pipewire(self):
        # Build a mapping of device name to label
        label_map = {label.text(): label for label in self._current_labels}
        # Remove all DraggableLabel widgets from all parents (but don't delete them)
        for label in self._current_labels:
            parent = label.parent()
            if isinstance(parent, QFrame):
                layout = parent.layout()
                if layout is not None:
                    layout.removeWidget(label)
            label.setParent(None)
        self.source_frame.clear_labels()
        self.device_list_widget.clear()
        device_ports = self.pw_monitor.get_device_ports()
        # Rebuild _current_labels for all current devices
        self._current_labels = []
        # --- Set sync device metadata on buckets ---
        for bucket in getattr(self, 'buckets', []):
            if bucket.name in self.SYNC_DEVICES:
                device = self.SYNC_DEVICES[bucket.name]
                ports = device_ports.get(device)
                bucket.sync_metadata = ports if ports else None
                bucket.set_sync_bucket(True)
                bucket.set_sync_available(bool(ports))
                # Remove any DraggableLabel from this bucket (shouldn't be any, but just in case)
                for i in reversed(range(bucket._layout.count() - 1)):
                    item = bucket._layout.itemAt(i + 1)
                    if item is not None:
                        widget = item.widget()
                        if widget is not None and isinstance(widget, DraggableLabel):
                            widget.setParent(None)
            else:
                bucket.set_sync_bucket(False)
                bucket.setEnabled(True)
                bucket.setStyleSheet("")
        # --- Add all other devices to Available Items or Outputs bucket ---
        for device, ports in device_ports.items():
            if device in self.SYNC_DEVICES.values():
                continue  # Do not create a label for sync devices
            device_item = QListWidgetItem(f"Device: {device}")
            device_item.setBackground(QColor("#333333"))
            device_item.setForeground(QColor("#b0b0b0"))
            self.device_list_widget.addItem(device_item)
            for port_info in ports:
                port_id = port_info['id']
                port_name = port_info.get('port', '<missing>')
                port_type = port_info.get('type', '<missing>')
                text = f"  [{port_id}]  Port: {port_name}  |  Type: {port_type}"
                item = QListWidgetItem(text)
                item.setData(USER_ROLE, port_id)
                self.device_list_widget.addItem(item)
            label = label_map.get(device)
            if label is None:
                label = DraggableLabel(device, ports)
            else:
                label.ports_metadata = ports
                label.fixed = False
            self._current_labels.append(label)
            location = self._label_locations.get(device, 'available')
            if location == 'available':
                self.source_frame.add_label(label)
            else:
                for bucket in getattr(self, 'buckets', []):
                    if bucket.name == location:
                        bucket._layout.insertWidget(bucket._layout.count() - 1, label)
                        break

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = DragDropApp()
    ex.show()
    sys.exit(app.exec_())