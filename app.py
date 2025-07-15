import sys
import json
import subprocess
import re
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QFrame, QListWidget, QListWidgetItem, QScrollArea, QGridLayout, QPushButton)
from PyQt5.QtCore import Qt, QMimeData, QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QDrag, QFont, QColor, QPalette, QFontMetrics
import os

def ensure_pipewire_syncs_exist():
    """
    Ensure the four sync sinks (Game, Chat, Media, Aux) exist using pactl.
    If a sink does not exist, create it using module-null-sink.
    """
    sync_names = ["Game", "Chat", "Media", "Aux"]
    try:
        # Get the list of current sinks
        sinks_output = subprocess.check_output(["pactl", "list", "short", "sinks"], text=True)
        existing_sinks = set()
        for line in sinks_output.splitlines():
            parts = line.split('\t')
            if len(parts) > 1:
                existing_sinks.add(parts[1])
        for name in sync_names:
            if name not in existing_sinks:
                # Create the sink if it doesn't exist
                cmd = [
                    "pactl", "load-module", "module-null-sink",
                    f"media.class=Audio/Sink", f"sink_name={name}", "channel_map=stereo"
                ]
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"[INFO] Created sync sink: {name}")
                except Exception as e:
                    print(f"[WARN] Could not create sync sink {name}: {e}")
    except Exception as e:
        print(f"[WARN] Could not check or create sync sinks: {e}")

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
        self.full_name = name  # Store the full name for eliding
        self._hidden = False  # Track hidden state
        # self.setToolTip(name)  # Remove default tooltip
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
        # Set initial elided text
        self._update_elided_text()

    def contextMenuEvent(self, event):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        if not self._hidden:
            hide_action = menu.addAction("Hide")
        else:
            hide_action = menu.addAction("Unhide")
        main_window = self.window()
        if main_window and hasattr(main_window, '_set_context_menu_open'):
            main_window._set_context_menu_open(True)
        # Use self.mapToGlobal(event.pos()) for correct positioning
        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action == hide_action:
            if main_window and hasattr(main_window, 'toggle_label_hidden'):
                main_window.toggle_label_hidden(self)
        if main_window and hasattr(main_window, '_set_context_menu_open'):
            main_window._set_context_menu_open(False)

    def set_hidden(self, hidden):
        self._hidden = hidden
        self.setVisible(not hidden)

    def is_hidden(self):
        return self._hidden

    def _update_elided_text(self):
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self.full_name, Qt.TextElideMode.ElideRight, self.width() - 10)
        super().setText(elided)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided_text()

    def setText(self, text):
        # Override setText to update full_name and elided text
        self.full_name = text
        # self.setToolTip(text)  # Remove default tooltip
        self._update_elided_text()

    def enterEvent(self, event):
        from PyQt5.QtWidgets import QToolTip
        # Show tooltip just below the label, or above if near the bottom of the screen
        label_rect = self.rect()
        global_pos = self.mapToGlobal(label_rect.bottomLeft())
        offset = 8  # pixels downward
        from PyQt5.QtCore import QPoint
        tooltip_pos = global_pos + QPoint(0, offset)
        tooltip_text = f"<p style='white-space:pre-wrap; max-width:300px'>{self.full_name}</p>"
        QToolTip.showText(tooltip_pos, tooltip_text, self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        from PyQt5.QtWidgets import QToolTip
        QToolTip.hideText()
        super().leaveEvent(event)

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
                'name': self.full_name,
                'ports': self.ports_metadata
            }
            
            # Serialize the dictionary to a JSON string and store in the MIME data
            mime_data.setData(self.MIME_TYPE, json.dumps(metadata).encode('utf-8'))

            drag = QDrag(self)
            drag.setMimeData(mime_data)
            drag.setPixmap(self.grab())
            
            drag.exec_(Qt.DropAction.MoveAction)

    def get_device_name(self):
        return self.full_name

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
                # --- Custom: trigger relinking if this is the Outputs bucket ---
                if self.name == 'Outputs':
                    main_window = self.window()
                    if main_window is not None and hasattr(main_window, 'relink_outputs_to_syncs'):
                        main_window.relink_outputs_to_syncs()
                # --- Custom: trigger sync bucket linking if this is a sync bucket ---
                elif hasattr(self, '_is_sync_bucket') and self._is_sync_bucket:
                    if main_window is not None and hasattr(main_window, 'link_item_to_sync_bucket'):
                        main_window.link_item_to_sync_bucket(self, source_widget)
        else:
            event.ignore()

    def get_draggable_labels(self):
        """Return all DraggableLabel widgets in this bucket (excluding the title and info labels)."""
        labels = []
        for i in range(2, self._layout.count() - 1):  # skip title and info label, and stretch
            item = self._layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if widget is not None and isinstance(widget, DraggableLabel):
                    labels.append(widget)
        return labels

    def get_device_names(self):
        return [label.get_device_name() for label in self.get_draggable_labels()]

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
                # --- Remove links if label was previously in Outputs ---
                main_window = self.window()
                if main_window is not None and hasattr(main_window, '_label_locations') and hasattr(main_window, 'remove_output_links_for_label'):
                    prev_location = main_window._label_locations.get(metadata['name'], None)
                    if prev_location == 'Outputs':
                        main_window.remove_output_links_for_label(source_widget)
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
        'Game': 'Game',
        'Chat': 'Chat',
        'Media': 'Media',
        'Aux': 'Aux',
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
        # --- Add direct event-based relinking ---
        self.pw_monitor.stream_added.connect(self._on_port_event)
        self.pw_monitor.stream_removed.connect(self._on_port_event)
        self._current_labels = []
        self._label_locations = self._load_label_locations()
        self._hidden_labels = {}  # name -> DraggableLabel
        self._label_map = {}  # device name -> DraggableLabel (persistent)
        # Add Show Hidden Items button
        self.show_hidden_btn = QPushButton("Show Hidden Items")
        self.show_hidden_btn.setStyleSheet("background-color: #444; color: #fff; font-weight: bold;")
        self.show_hidden_btn.clicked.connect(self.show_hidden_items_dialog)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.show_hidden_btn)
        btn_layout.addStretch(1)
        main_vlayout.insertLayout(0, btn_layout)
        self._refresh_pipewire()
        self._context_menu_open = False

    def _set_context_menu_open(self, is_open):
        self._context_menu_open = is_open

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
        if getattr(self, '_context_menu_open', False):
            print("[DEBUG] Skipping refresh: context menu open")
            return
        # --- Debug output ---
        print("[DEBUG] _label_locations:", self._label_locations)
        device_ports = self.pw_monitor.get_device_ports()
        print("[DEBUG] device_ports keys:", list(device_ports.keys()))
        outputs_bucket = None
        for bucket in getattr(self, 'buckets', []):
            if bucket.name == 'Outputs':
                outputs_bucket = bucket
                break
        if outputs_bucket:
            output_labels = [label.get_device_name() for label in outputs_bucket.get_draggable_labels()]
            print("[DEBUG] Labels in Outputs bucket:", output_labels)
        # --- Remove links for labels that disappeared from Outputs ---
        prev_outputs = set()
        for name, location in self._label_locations.items():
            if location == 'Outputs':
                prev_outputs.add(name)
        current_outputs = set()
        if outputs_bucket:
            for label in outputs_bucket.get_draggable_labels():
                current_outputs.add(label.get_device_name())
        removed_outputs = prev_outputs - current_outputs
        if removed_outputs:
            print(f"[DEBUG] Labels removed from Outputs: {removed_outputs}")
            for label_name in removed_outputs:
                # Find the label object by name in _label_map
                label = self._label_map.get(label_name)
                if label:
                    self.remove_output_links_for_label(label)
        # --- New logic: Only create/remove labels as needed ---
        # Build a set of current device names
        current_device_names = set(device_ports.keys())
        # Remove labels for devices that disappeared
        for device in list(self._label_map.keys()):
            if device not in current_device_names and device not in self.SYNC_DEVICES.values():
                label = self._label_map[device]
                # Remove from parent layout
                parent = label.parent()
                if isinstance(parent, QFrame):
                    layout = parent.layout()
                    if layout is not None:
                        layout.removeWidget(label)
                label.setParent(None)
                # Remove from hidden if present
                if device in self._hidden_labels:
                    del self._hidden_labels[device]
                del self._label_map[device]
                # Do NOT delete from self._label_locations so we remember the last location
        # Update or create labels for current devices
        for device, ports in device_ports.items():
            if device in self.SYNC_DEVICES.values():
                continue  # Do not create a label for sync devices
            if device in self._label_map:
                label = self._label_map[device]
                label.ports_metadata = ports
                label.fixed = False
            else:
                label = DraggableLabel(device, ports)
                self._label_map[device] = label
        # --- UI placement logic ---
        self.source_frame.clear_labels()
        self.device_list_widget.clear()
        self._current_labels = []
        # --- Set sync device metadata on buckets ---
        for bucket in getattr(self, 'buckets', []):
            if bucket.name in self.SYNC_DEVICES:
                device = self.SYNC_DEVICES[bucket.name]
                ports = device_ports.get(device)
                bucket.sync_metadata = ports if ports else None
                bucket.set_sync_bucket(True)
                bucket.set_sync_available(bool(ports))
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
            label = self._label_map[device]
            self._current_labels.append(label)
            location = self._label_locations.get(device, 'available')
            # Only move label if its location has changed or if not in a parent
            if location == 'hidden':
                label.set_hidden(True)
                self._hidden_labels[device] = label
                # Remove from parent if needed
                parent = label.parent()
                if isinstance(parent, QFrame):
                    layout = parent.layout()
                    if layout is not None:
                        layout.removeWidget(label)
                label.setParent(None)
            elif location == 'available':
                label.set_hidden(False)
                self.source_frame.add_label(label)
                if device in self._hidden_labels:
                    del self._hidden_labels[device]
            else:
                label.set_hidden(False)
                # Only add to bucket if not already present
                already_in_bucket = False
                for bucket in getattr(self, 'buckets', []):
                    if bucket.name == location:
                        for l in bucket.get_draggable_labels():
                            if l is label:
                                already_in_bucket = True
                                break
                        if not already_in_bucket:
                            bucket._layout.insertWidget(bucket._layout.count() - 1, label)
                        break
        # --- Auto-refresh all links after port changes ---
        self.relink_outputs_to_syncs()
        for bucket in self.buckets:
            if hasattr(bucket, '_is_sync_bucket') and bucket._is_sync_bucket:
                for i in range(2, bucket._layout.count() - 1):  # skip title/info/stretch
                    item = bucket._layout.itemAt(i)
                    if item is not None:
                        widget = item.widget()
                        if widget is not None and isinstance(widget, DraggableLabel):
                            self.link_item_to_sync_bucket(bucket, widget)

    def _on_port_event(self, *args, **kwargs):
        """
        Called immediately when a port is added or removed. Triggers a refresh and relinking.
        """
        print("[DEBUG] Port event detected, refreshing and relinking.")
        self._refresh_pipewire()

    def relink_outputs_to_syncs(self):
        """
        For each sync bucket (Game, Chat, Media, Aux), use its sync_metadata to find monitor ports.
        For each DraggableLabel in Outputs, use its ports_metadata to find playback ports.
        Use device:port as the unique identifier to match metadata to live port objects from pipewire_python.
        Link each sync monitor port to each output device playback port using the connect method, matching _FL to _FL, _FR to _FR, etc.
        """
        if link is None:
            print("[WARN] pipewire_python not available, cannot relink outputs.")
            return
        # Get all live outputs and inputs from pipewire_python
        outputs = link.list_outputs(pair_stereo=False)
        inputs = link.list_inputs(pair_stereo=False)
        # Build a lookup: device:port -> port object
        port_lookup = {}
        for p in outputs + inputs:
            key = f"{getattr(p, 'device', '')}:{getattr(p, 'name', '')}"
            port_lookup[key] = p
        # Find the Outputs bucket
        outputs_bucket = None
        for bucket in self.buckets:
            if bucket.name == 'Outputs':
                outputs_bucket = bucket
                break
        if outputs_bucket is None:
            print("[WARN] Outputs bucket not found.")
            return
        # For each sync bucket
        for bucket in self.buckets:
            if not hasattr(bucket, 'sync_metadata') or not bucket.sync_metadata:
                continue
            sync_name = bucket.name
            sync_ports = bucket.sync_metadata
            # Find monitor ports for this sync
            monitor_ports = [p for p in sync_ports if p.get('type') == 'output' and p.get('port', '').startswith('monitor_')]
            # For each DraggableLabel in Outputs
            for label in outputs_bucket.get_draggable_labels():
                device_name = label.get_device_name()
                device_ports = label.ports_metadata or []
                # Find playback ports for this device
                playback_ports = [p for p in device_ports if p.get('type') == 'input' and p.get('port', '').startswith('playback_')]
                # Only link matching suffixes (_FL to _FL, _FR to _FR, etc)
                for mon in monitor_ports:
                    mon_suffix = mon['port'].split('_')[-1] if '_' in mon['port'] else mon['port']
                    mon_key = f"{sync_name}:{mon['port']}"
                    out_port = port_lookup.get(mon_key)
                    for pb in playback_ports:
                        pb_suffix = pb['port'].split('_')[-1] if '_' in pb['port'] else pb['port']
                        if mon_suffix != pb_suffix:
                            continue  # Only link matching suffixes
                        pb_key = f"{device_name}:{pb['port']}"
                        in_port = port_lookup.get(pb_key)
                        if out_port and in_port:
                            try:
                                out_port.connect(in_port)
                                print(f"[INFO] Linked {mon_key} -> {pb_key}")
                            except Exception as e:
                                print(f"[WARN] Could not link {mon_key} -> {pb_key}: {e}")

    def link_item_to_sync_bucket(self, bucket, label):
        """
        When an item is dropped in a sync bucket, remove all existing links from its output_ ports, then link its output_ ports to the playback_ ports of the sync sink, matching suffixes, using metadata.
        Only remove links that are not the correct/desired ones.
        """
        print(f"[DEBUG] link_item_to_sync_bucket called for bucket {bucket.name} and label {label.text()}")
        if link is None:
            print("[WARN] pipewire_python not available, cannot link item to sync bucket.")
            return
        # Get all live outputs and inputs from pipewire_python
        outputs = link.list_outputs(pair_stereo=False)
        inputs = link.list_inputs(pair_stereo=False)
        # Build a lookup: device:port -> port object
        port_lookup = {}
        for p in outputs + inputs:
            key = f"{getattr(p, 'device', '')}:{getattr(p, 'name', '')}"
            port_lookup[key] = p
        # Get sync sink metadata
        sync_name = bucket.name
        sync_ports = getattr(bucket, 'sync_metadata', None)
        if not sync_ports:
            print(f"[WARN] No sync_metadata for bucket {sync_name}")
            return
        # Find playback ports for this sync sink
        playback_ports = [p for p in sync_ports if p.get('type') == 'input' and p.get('port', '').startswith('playback_')]
        print(f"[DEBUG] {sync_name} playback ports:", playback_ports)
        # Get label metadata
        device_name = label.text()
        device_ports = getattr(label, 'ports_metadata', [])
        # Find output_ ports for this device
        output_ports = [p for p in device_ports if p.get('type') == 'output' and p.get('port', '').startswith('output_')]
        print(f"[DEBUG] {device_name} output ports:", output_ports)
        # --- Remove existing links from output_ ports that are not the desired ones ---
        try:
            pw_link_output = subprocess.check_output(["pw-link", "-l"], text=True)
        except Exception as e:
            print(f"[WARN] Could not list links: {e}")
            pw_link_output = ""
        # Build set of desired links (source_key, dest_key)
        desired_links = set()
        for out in output_ports:
            out_suffix = out['port'].split('_')[-1] if '_' in out['port'] else out['port']
            out_key = f"{device_name}:{out['port']}"
            for pb in playback_ports:
                pb_suffix = pb['port'].split('_')[-1] if '_' in pb['port'] else pb['port']
                if out_suffix != pb_suffix:
                    continue
                pb_key = f"{sync_name}:{pb['port']}"
                desired_links.add((out_key, pb_key))
        print(f"[DEBUG] Desired links for {device_name}: {desired_links}")
        # Parse pw-link -l output and remove undesired links from these output_ ports
        current_src = None
        for line in pw_link_output.splitlines():
            line = line.rstrip()
            if not line:
                continue
            if not line.startswith('  '):
                # Source header line
                current_src = line.strip()
            elif line.strip().startswith('|->') and current_src:
                dst = line.strip()[3:].strip()
                src_key = current_src
                dst_key = dst
                # Only consider links from our output_ ports
                if src_key in [f"{device_name}:{p['port']}" for p in output_ports]:
                    print(f"[DEBUG] Found link: {src_key} -> {dst_key}")
                    if (src_key, dst_key) not in desired_links:
                        print(f"[DEBUG] Removing undesired link: {src_key} -> {dst_key}")
                        try:
                            subprocess.run(["pw-link", "-d", src_key, dst_key], check=True)
                            print(f"[INFO] Removed old link: {src_key} -> {dst_key}")
                        except Exception as e:
                            print(f"[WARN] Could not remove link: {src_key} -> {dst_key}: {e}")
                    else:
                        print(f"[DEBUG] Link {src_key} -> {dst_key} is desired, keeping.")
        # --- Now create the desired links (if not already present) ---
        for out in output_ports:
            out_suffix = out['port'].split('_')[-1] if '_' in out['port'] else out['port']
            out_key = f"{device_name}:{out['port']}"
            out_port = port_lookup.get(out_key)
            for pb in playback_ports:
                pb_suffix = pb['port'].split('_')[-1] if '_' in pb['port'] else pb['port']
                if out_suffix != pb_suffix:
                    continue  # Only link matching suffixes
                pb_key = f"{sync_name}:{pb['port']}"
                in_port = port_lookup.get(pb_key)
                if out_port and in_port:
                    try:
                        out_port.connect(in_port)
                        print(f"[INFO] Linked {out_key} -> {pb_key}")
                    except Exception as e:
                        print(f"[WARN] Could not link {out_key} -> {pb_key}: {e}")
                else:
                    print(f"[DEBUG] Port not found for {out_key} or {pb_key}")

    def remove_output_links_for_label(self, label):
        """
        Remove all links from sync sinks' monitor_ ports to the playback_ ports of this label/device.
        """
        print("CALLED remove_output_links_for_label")
        print(f"[DEBUG] remove_output_links_for_label called for label: {getattr(label, 'get_device_name', lambda: str(label))()}")
        if link is None:
            print("[WARN] pipewire_python not available, cannot remove output links.")
            return
        device_name = label.get_device_name()
        device_ports = getattr(label, 'ports_metadata', [])
        print(f"[DEBUG] Device: {device_name}, Ports: {device_ports}")
        # Find playback_ ports for this device
        playback_ports = [p for p in device_ports if p.get('type') == 'input' and p.get('port', '').startswith('playback_')]
        print(f"[DEBUG] Playback ports for removal: {playback_ports}")
        # Get all sync sink names
        sync_names = list(self.SYNC_DEVICES.keys())
        # For each sync, get monitor_ ports from its bucket's sync_metadata
        monitor_ports = []
        for bucket in self.buckets:
            if bucket.name in sync_names and getattr(bucket, 'sync_metadata', None):
                for p in bucket.sync_metadata:
                    if p.get('type') == 'output' and p.get('port', '').startswith('monitor_'):
                        monitor_ports.append((bucket.name, p['port']))
        # Build set of possible links to remove
        links_to_remove = set()
        for sync_name, mon_port in monitor_ports:
            mon_key = f"{sync_name}:{mon_port}"
            for pb in playback_ports:
                pb_key = f"{device_name}:{pb['port']}"
                links_to_remove.add((mon_key, pb_key))
        print(f"[DEBUG] links_to_remove: {links_to_remove}")
        # Parse pw-link -l output and remove these links
        try:
            pw_link_output = subprocess.check_output(["pw-link", "-l"], text=True)
        except Exception as e:
            print(f"[WARN] Could not list links: {e}")
            pw_link_output = ""
        current_src = None
        for line in pw_link_output.splitlines():
            line = line.rstrip()
            if not line:
                continue
            if not line.startswith('  '):
                current_src = line.strip()
            elif line.strip().startswith('|->') and current_src:
                dst = line.strip()[3:].strip()
                src_key = current_src
                dst_key = dst
                print(f"[DEBUG] Found pw-link: {src_key} -> {dst_key}")
                if (src_key, dst_key) in links_to_remove:
                    print(f"[DEBUG] Removing output link: {src_key} -> {dst_key}")
                    try:
                        subprocess.run(["pw-link", "-d", src_key, dst_key], check=True)
                        print(f"[INFO] Removed output link: {src_key} -> {dst_key}")
                    except Exception as e:
                        print(f"[WARN] Could not remove output link: {src_key} -> {dst_key}: {e}")

    def toggle_label_hidden(self, label):
        """
        Hide or unhide a label. If hiding, remove from UI and add to _hidden_labels. If unhiding, restore to AvailableItemsFrame.
        """
        name = label.get_device_name()
        if not label.is_hidden():
            label.set_hidden(True)
            self._hidden_labels[name] = label
            # Remove from parent layout
            parent = label.parent()
            if isinstance(parent, QFrame):
                layout = parent.layout()
                if layout is not None:
                    layout.removeWidget(label)
            label.setParent(None)
            self._label_locations[name] = 'hidden'
            self._save_label_locations()
        else:
            label.set_hidden(False)
            if name in self._hidden_labels:
                del self._hidden_labels[name]
            self._label_locations[name] = 'available'
            self.source_frame.add_label(label)
            self._save_label_locations()

    def show_hidden_items_dialog(self):
        """
        Show a dialog listing hidden items, allowing the user to unhide them.
        """
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout, QListWidgetItem
        dialog = QDialog(self)
        dialog.setWindowTitle("Hidden Items")
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        for name, label in self._hidden_labels.items():
            item = QListWidgetItem(name)
            list_widget.addItem(item)
        layout.addWidget(list_widget)
        btn_layout = QHBoxLayout()
        unhide_btn = QPushButton("Unhide Selected")
        close_btn = QPushButton("Close")
        btn_layout.addWidget(unhide_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        def unhide_selected():
            selected = list_widget.selectedItems()
            for item in selected:
                name = item.text()
                label = self._hidden_labels.get(name)
                if label:
                    self.toggle_label_hidden(label)
                    list_widget.takeItem(list_widget.row(item))
        unhide_btn.clicked.connect(unhide_selected)
        close_btn.clicked.connect(dialog.accept)
        dialog.exec_()

if __name__ == '__main__':
    ensure_pipewire_syncs_exist()
    app = QApplication(sys.argv)
    ex = DragDropApp()
    ex.show()
    sys.exit(app.exec_())
