from __future__ import annotations

import os
import time
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

from . import viewlink_types as T
from .camera_controller import CameraController, SOURCE_MOUSE, SOURCE_UI
from .joystick import DEFAULT_JOYSTICK_NAME, JoystickCommander, JoystickConfig, JoystickWorker
from .sdk import ConnectionState, TELEMETRY_STALE_TIMEOUT, TRACK_VIDEO_HEIGHT, TRACK_VIDEO_WIDTH, ViewLinkSDK
from .video import VIDEO_CONNECTING, VIDEO_LIVE, VIDEO_RECONNECTING, VIDEO_STOPPED, VideoWorker
from .dashboard_theme import CockpitBackground, CollapsibleSection, apply_style


TRACKER_LABELS = {
    T.VLK_TRACKER_STATUS_STOPPED: "Stopped",
    T.VLK_TRACKER_STATUS_SEARCHING: "Searching",
    T.VLK_TRACKER_STATUS_TRACKING: "Tracking",
    T.VLK_TRACKER_STATUS_LOST: "Lost",
}


class VideoLabel(QtWidgets.QLabel):
    target_selected = QtCore.pyqtSignal(int, int, int, int)
    stop_tracking_requested = QtCore.pyqtSignal()
    zoom_requested = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMouseTracking(True)
        self.setObjectName("mainVideo")
        self.setText("No signal")
        self._frame_w = 0
        self._frame_h = 0
        self._last_target: tuple[int, int] | None = None
        self._source = QtGui.QPixmap()

    def set_frame_dimensions(self, width: int, height: int) -> None:
        self._frame_w = width
        self._frame_h = height

    def set_frame(self, frame) -> None:
        self.set_frame_dimensions(frame.width(), frame.height())
        self._source = QtGui.QPixmap.fromImage(frame)
        self._render()

    def clear(self) -> None:
        self._source = QtGui.QPixmap()
        self._frame_w = self._frame_h = 0
        super().clear()

    def _render(self) -> None:
        if self._source.isNull():
            return
        pixmap = self._source.scaled(self.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.FastTransformation)
        painter = QtGui.QPainter(pixmap)
        cx, cy = pixmap.width() // 2, pixmap.height() // 2
        arm = max(24, min(pixmap.width(), pixmap.height()) // 14)
        for color, width in [(QtGui.QColor(0, 0, 0, 190), 4), (QtGui.QColor("#f7d84a"), 2)]:
            painter.setPen(QtGui.QPen(color, width))
            painter.drawLine(cx - arm, cy, cx - 8, cy)
            painter.drawLine(cx + 8, cy, cx + arm, cy)
            painter.drawLine(cx, cy - arm, cx, cy - 8)
            painter.drawLine(cx, cy + 8, cx, cy + arm)
            painter.drawEllipse(QtCore.QPoint(cx, cy), 3, 3)
        painter.end()
        self.setPixmap(pixmap)

    def resizeEvent(self, event) -> None:
        self._render()
        super().resizeEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == QtCore.Qt.LeftButton and self._frame_w and self._frame_h:
            mapped = self._map_widget_to_tracking_frame(event.pos())
            if mapped:
                x, y = mapped
                self._last_target = (x, y)
                self.target_selected.emit(x, y, TRACK_VIDEO_WIDTH, TRACK_VIDEO_HEIGHT)
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == QtCore.Qt.RightButton:
            self.stop_tracking_requested.emit()
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.zoom_requested.emit(1 if delta > 0 else -1)

    def _map_widget_to_frame(self, pos: QtCore.QPoint) -> tuple[int, int] | None:
        pixmap = self.pixmap()
        if not pixmap:
            return None
        scaled = pixmap.size()
        x0 = (self.width() - scaled.width()) / 2
        y0 = (self.height() - scaled.height()) / 2
        if pos.x() < x0 or pos.y() < y0 or pos.x() > x0 + scaled.width() or pos.y() > y0 + scaled.height():
            return None
        x = int((pos.x() - x0) / scaled.width() * self._frame_w)
        y = int((pos.y() - y0) / scaled.height() * self._frame_h)
        return max(0, min(self._frame_w - 1, x)), max(0, min(self._frame_h - 1, y))

    def _map_widget_to_tracking_frame(self, pos: QtCore.QPoint) -> tuple[int, int] | None:
        pixmap = self.pixmap()
        if not pixmap:
            return None
        scaled = pixmap.size()
        x0 = (self.width() - scaled.width()) / 2
        y0 = (self.height() - scaled.height()) / 2
        if pos.x() < x0 or pos.y() < y0 or pos.x() > x0 + scaled.width() or pos.y() > y0 + scaled.height():
            return None
        x_ratio = (pos.x() - x0) / scaled.width()
        y_ratio = (pos.y() - y0) / scaled.height()
        x = round(x_ratio * (TRACK_VIDEO_WIDTH - 1))
        y = round(y_ratio * (TRACK_VIDEO_HEIGHT - 1))
        return max(0, min(TRACK_VIDEO_WIDTH - 1, x)), max(0, min(TRACK_VIDEO_HEIGHT - 1, y))

class HoldButton(QtWidgets.QPushButton):
    pressed_changed = QtCore.pyqtSignal(bool)

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.pressed.connect(lambda: self.pressed_changed.emit(True))
        self.released.connect(lambda: self.pressed_changed.emit(False))


class MainWindow(QtWidgets.QMainWindow):
    sdk_status_signal = QtCore.pyqtSignal(str)
    telemetry_signal = QtCore.pyqtSignal(object)

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.sdk = ViewLinkSDK(root)
        self.sdk.initialize()
        self.controller = CameraController(self.sdk)
        self.video_worker: VideoWorker | None = None
        self.joystick_worker: JoystickWorker | None = None
        self._joystick_manual_disabled = False
        self.joystick_commander = JoystickCommander(self.controller, self)
        self.current_sensor = T.VLK_SENSOR_VISIBLE1
        self.current_image = T.VLK_IMAGE_TYPE_VISIBLE1
        self.current_ir_color = T.VLK_IR_COLOR_WHITEHOT
        self._wheel_zoom_timer = QtCore.QTimer(self)
        self._wheel_zoom_timer.setInterval(350)
        self._wheel_zoom_timer.setSingleShot(True)
        self._wheel_zoom_timer.timeout.connect(lambda: self.controller.stop_zoom(source=SOURCE_MOUSE))
        self._telemetry_timer = QtCore.QTimer(self)
        self._telemetry_timer.setInterval(500)
        self._telemetry_timer.timeout.connect(self._refresh_telemetry_status)

        self.setWindowTitle("VControl")
        self.resize(1440, 900)
        self._build_ui()
        self._connect_signals()
        self._apply_style()
        self.statusBar().showMessage(f"ViewLink SDK {self.sdk.version()} | {self.sdk.lib_path}")
        self.statusBar().hide()
        self._telemetry_timer.start()

    def _build_ui(self) -> None:
        central = CockpitBackground()
        self.setCentralWidget(central)
        shell = QtWidgets.QHBoxLayout(central)
        shell.setContentsMargins(20, 18, 20, 20)
        shell.setSpacing(14)
        column = QtWidgets.QVBoxLayout()
        column.setSpacing(12)
        toolbar = QtWidgets.QFrame()
        toolbar.setObjectName("toolbar")
        tools = QtWidgets.QHBoxLayout(toolbar)
        tools.setContentsMargins(12, 10, 12, 10)
        tools.setSpacing(10)
        tools.addWidget(QtWidgets.QLabel("Main"))
        self.image_combo = QtWidgets.QComboBox()
        for name, value in [
            ("Visible 1", T.VLK_IMAGE_TYPE_VISIBLE1),
            ("Visible 2", T.VLK_IMAGE_TYPE_VISIBLE2),
            ("Thermal 1", T.VLK_IMAGE_TYPE_IR1),
            ("Thermal 2", T.VLK_IMAGE_TYPE_IR2),
            ("Fusion", T.VLK_IMAGE_TYPE_FUSION),
        ]:
            self.image_combo.addItem(name, value)
        tools.addWidget(self.image_combo)
        self.pip_check = QtWidgets.QCheckBox("Picture in Picture")
        self.pip_check.setToolTip("Camera-generated PiP via ViewLink")
        tools.addWidget(self.pip_check)
        self.video_status = QtWidgets.QLabel("Idle")
        self.video_status.setObjectName("statusBadge")
        tools.addWidget(self.video_status)
        tools.addStretch(1)
        play = QtWidgets.QPushButton("Connect + Play")
        play.clicked.connect(self._connect_play)
        stop = QtWidgets.QPushButton("Stop")
        stop.clicked.connect(self._stop_video)
        tools.addWidget(play)
        tools.addWidget(stop)
        column.addWidget(toolbar)
        self.video_label = VideoLabel()
        stage = QtWidgets.QFrame()
        stage.setObjectName("videoStage")
        video_layout = QtWidgets.QVBoxLayout(stage)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.addWidget(self.video_label)
        column.addWidget(stage, 1)
        shell.addLayout(column, 1)
        shell.addWidget(self._side_panel())
        self.statusBar().messageChanged.connect(self._log_status)

    def _side_panel(self) -> QtWidgets.QWidget:
        self.control_wrapper = QtWidgets.QFrame()
        self.control_wrapper.setObjectName("controlWrapper")
        self.control_wrapper.setFixedWidth(470)
        wrapper = QtWidgets.QVBoxLayout(self.control_wrapper)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.setSpacing(8)
        row = QtWidgets.QHBoxLayout()
        self.sidebar_toggle = QtWidgets.QToolButton()
        self.sidebar_toggle.setObjectName("sidebarToggle")
        self.sidebar_toggle.setText("Controls  <")
        self.sidebar_toggle.setCheckable(True)
        self.sidebar_toggle.setChecked(True)
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        row.addStretch(1)
        row.addWidget(self.sidebar_toggle)
        wrapper.addLayout(row)
        self.control_scroll = QtWidgets.QScrollArea()
        self.control_scroll.setObjectName("controlScroll")
        self.control_scroll.setWidgetResizable(True)
        self.control_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.control_scroll.setFixedWidth(450)
        panel = QtWidgets.QFrame()
        panel.setObjectName("sidePanel")
        panel.setFixedWidth(430)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.speed_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.speed_slider.setRange(5, 100)
        self.speed_slider.setValue(35)
        layout.addWidget(self._group("Connection", self._connection_controls()))
        camera = self._camera_controls()
        quick = QtWidgets.QWidget()
        quick_layout = QtWidgets.QVBoxLayout(quick)
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(self.photo_btn)
        actions.addWidget(self.record_btn)
        focus = QtWidgets.QPushButton("Auto Focus")
        focus.clicked.connect(lambda: self._when_connected(self.sdk.VLK_SetFocusMode, T.VLK_FOCUS_MODE_AUTO))
        actions.addWidget(focus)
        quick_layout.addLayout(actions)
        self.record_indicator = QtWidgets.QLabel("RECORD STATUS UNKNOWN")
        self.record_indicator.setObjectName("recordIndicator")
        quick_layout.addWidget(self.record_indicator)
        layout.addWidget(self._group("Quick Actions", quick))
        layout.addWidget(self._group("Gimbal", self._gimbal_controls()))
        layout.addWidget(self._group("Camera", camera))
        layout.addWidget(self._group("AI Tracking", self._tracking_controls()))
        layout.addWidget(self._group("Laser Rangefinder", self._laser_controls()))
        layout.addWidget(self._group("Joystick", self._joystick_controls()))
        layout.addWidget(self._group("Advanced", self._advanced_controls()))
        status = QtWidgets.QWidget()
        metrics = QtWidgets.QGridLayout(status)
        for index, (attr, title) in enumerate([
            ("yaw_label", "Yaw"), ("pitch_label", "Pitch"),
            ("roll_label", "Roll"), ("zoom_label", "Zoom"),
            ("fov_label", "FOV"), ("laser_label", "Laser"),
            ("track_label", "Track"), ("telemetry_status_label", "Telemetry"),
            ("model_label", "Camera"),
        ]):
            label = QtWidgets.QLabel(title + " --")
            label.setObjectName("metricValue" if index < 4 else "metricLabel")
            label.setWordWrap(True)
            setattr(self, attr, label)
            metrics.addWidget(label, index // 2, index % 2)
        layout.addWidget(self._group("Status", status))
        self.log = QtWidgets.QTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setFixedHeight(120)
        self.log.document().setMaximumBlockCount(300)
        layout.addWidget(self.log)
        layout.addStretch(1)
        self.control_scroll.setWidget(panel)
        wrapper.addWidget(self.control_scroll, 1)
        return self.control_wrapper

    def _connection_controls(self):
        widget = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(widget)
        self.ip_edit = QtWidgets.QLineEdit("192.168.144.25")
        self.port_spin = QtWidgets.QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(2000)
        self.rtsp_edit = QtWidgets.QLineEdit("rtsp://192.168.144.25:554")
        self.connect_btn = QtWidgets.QPushButton("Connect TCP")
        self.video_btn = QtWidgets.QPushButton("Open Video")
        self.conn_status = QtWidgets.QLabel("Disconnected")
        self.conn_status.setWordWrap(True)
        grid.addWidget(QtWidgets.QLabel("Camera IP"), 0, 0)
        grid.addWidget(self.ip_edit, 0, 1, 1, 2)
        grid.addWidget(QtWidgets.QLabel("TCP Port"), 1, 0)
        grid.addWidget(self.port_spin, 1, 1)
        grid.addWidget(self.connect_btn, 1, 2)
        grid.addWidget(QtWidgets.QLabel("RTSP"), 2, 0)
        grid.addWidget(self.rtsp_edit, 2, 1, 1, 2)
        grid.addWidget(self.conn_status, 3, 0, 1, 2)
        grid.addWidget(self.video_btn, 3, 2)
        return widget

    def _laser_controls(self):
        widget = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(widget)
        self.laser_check = QtWidgets.QCheckBox("Laser")
        self.laser_single_btn = QtWidgets.QPushButton("Range")
        row.addWidget(self.laser_check)
        row.addWidget(self.laser_single_btn)
        return widget

    def _toggle_sidebar(self):
        expanded = self.sidebar_toggle.isChecked()
        self.control_scroll.setVisible(expanded)
        self.control_wrapper.setFixedWidth(470 if expanded else 48)
        self.sidebar_toggle.setText("Controls  <" if expanded else ">")

    def _log_status(self, text):
        if text:
            self.log.append(QtCore.QTime.currentTime().toString("HH:mm:ss") + "  " + text)

    def _connect_play(self):
        if not self.sdk.connected:
            self._toggle_connection()
        if self.video_worker is None:
            self._toggle_video()

    def _stop_video(self):
        if self.video_worker is not None:
            self._toggle_video()

    def _gimbal_controls(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(widget)
        grid.setSpacing(6)
        self.up_btn = HoldButton("Up")
        self.down_btn = HoldButton("Down")
        self.left_btn = HoldButton("Left")
        self.right_btn = HoldButton("Right")
        self.home_btn = QtWidgets.QPushButton("Center")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.follow_check = QtWidgets.QCheckBox("Follow mode")
        self.motor_check = QtWidgets.QCheckBox("Motor on")
        grid.addWidget(QtWidgets.QLabel("Speed"), 0, 0)
        grid.addWidget(self.speed_slider, 0, 1, 1, 2)
        grid.addWidget(self.up_btn, 1, 1)
        grid.addWidget(self.left_btn, 2, 0)
        grid.addWidget(self.home_btn, 2, 1)
        grid.addWidget(self.right_btn, 2, 2)
        grid.addWidget(self.down_btn, 3, 1)
        grid.addWidget(self.stop_btn, 4, 0, 1, 3)
        grid.addWidget(self.follow_check, 5, 0, 1, 2)
        grid.addWidget(self.motor_check, 5, 2)
        self.yaw_spin = QtWidgets.QDoubleSpinBox()
        self.yaw_spin.setRange(-180, 180)
        self.yaw_spin.setPrefix("Pan ")
        self.pitch_spin = QtWidgets.QDoubleSpinBox()
        self.pitch_spin.setRange(-90, 90)
        self.pitch_spin.setPrefix("Tilt ")
        angle = QtWidgets.QPushButton("Set Angle")
        angle.clicked.connect(lambda: self._when_connected(self.controller.turn_to, self.yaw_spin.value(), self.pitch_spin.value()))
        grid.addWidget(self.yaw_spin, 6, 0)
        grid.addWidget(self.pitch_spin, 6, 1)
        grid.addWidget(angle, 6, 2)
        self.speed_slider.valueChanged.connect(self._update_joystick_speed)
        self._update_joystick_speed()
        return widget

    def _camera_controls(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout(widget)
        self.ir_combo = QtWidgets.QComboBox()
        for name, value in [
            ("White hot", T.VLK_IR_COLOR_WHITEHOT),
            ("Black hot", T.VLK_IR_COLOR_BLACKHOT),
            ("Pseudo hot", T.VLK_IR_COLOR_PSEUDOHOT),
            ("Rusty", T.VLK_IR_COLOR_RUSTY),
        ]:
            self.ir_combo.addItem(name, value)
        self.zoom_in_btn = HoldButton("Zoom +")
        self.zoom_out_btn = HoldButton("Zoom -")
        self.focus_in_btn = HoldButton("Focus +")
        self.focus_out_btn = HoldButton("Focus -")
        self.focus_mode = QtWidgets.QComboBox()
        self.focus_mode.addItem("Auto focus", T.VLK_FOCUS_MODE_AUTO)
        self.focus_mode.addItem("Manual focus", T.VLK_FOCUS_MODE_MANU)
        self.photo_btn = QtWidgets.QPushButton("Photo")
        self.record_btn = QtWidgets.QPushButton("Start Record")
        layout.addWidget(QtWidgets.QLabel("Thermal"), 0, 0)
        layout.addWidget(self.ir_combo, 0, 1)
        layout.addWidget(self.zoom_in_btn, 2, 0)
        layout.addWidget(self.zoom_out_btn, 2, 1)
        layout.addWidget(self.focus_in_btn, 3, 0)
        layout.addWidget(self.focus_out_btn, 3, 1)
        layout.addWidget(self.focus_mode, 4, 0, 1, 2)
        self.zoom_spin = QtWidgets.QDoubleSpinBox()
        self.zoom_spin.setRange(1, 128)
        self.zoom_spin.setSuffix("x")
        set_zoom = QtWidgets.QPushButton("Set Zoom")
        set_zoom.clicked.connect(lambda: self._when_connected(self.sdk.VLK_ZoomTo, self.zoom_spin.value()))
        layout.addWidget(self.zoom_spin, 5, 0)
        layout.addWidget(set_zoom, 5, 1)
        return widget

    def _tracking_controls(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout(widget)
        self.ai_btn = QtWidgets.QPushButton("Start AI")
        self.stop_track_btn = QtWidgets.QPushButton("Stop Track")
        self.track_sensor = QtWidgets.QComboBox()
        self.track_sensor.addItem("Visible 1", T.VLK_SENSOR_VISIBLE1)
        self.track_sensor.addItem("Visible 2", T.VLK_SENSOR_VISIBLE2)
        self.track_sensor.addItem("IR", T.VLK_SENSOR_IR)
        self.track_template = QtWidgets.QComboBox()
        self.track_template.addItem("32x32", T.VLK_TRACK_TEMPLATE_SIZE_32)
        self.track_template.addItem("64x64", T.VLK_TRACK_TEMPLATE_SIZE_64)
        self.track_template.addItem("128x128", T.VLK_TRACK_TEMPLATE_SIZE_128)
        self.track_template.setCurrentIndex(1)
        layout.addWidget(self.ai_btn, 0, 0)
        layout.addWidget(self.stop_track_btn, 0, 1)
        layout.addWidget(QtWidgets.QLabel("Sensor"), 1, 0)
        layout.addWidget(self.track_sensor, 1, 1)
        layout.addWidget(QtWidgets.QLabel("Template"), 2, 0)
        layout.addWidget(self.track_template, 2, 1)
        return widget

    def _advanced_controls(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout(widget)
        self.defog_check = QtWidgets.QCheckBox("Defog")
        self.eo_dzoom_check = QtWidgets.QCheckBox("EO digital zoom")
        self.osd_check = QtWidgets.QCheckBox("OSD")
        self.cross_check = QtWidgets.QCheckBox("Cross")
        self.pitch_yaw_check = QtWidgets.QCheckBox("Pitch/Yaw")
        layout.addWidget(self.defog_check, 0, 0)
        layout.addWidget(self.eo_dzoom_check, 0, 1)
        layout.addWidget(self.osd_check, 1, 0)
        layout.addWidget(self.cross_check, 1, 1)
        layout.addWidget(self.pitch_yaw_check, 2, 0)
        return widget

    def _joystick_controls(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout(widget)
        self.js_device = QtWidgets.QLineEdit("/dev/input/js0")
        self.pan_channel = QtWidgets.QSpinBox()
        self.tilt_channel = QtWidgets.QSpinBox()
        self.zoom_channel = QtWidgets.QSpinBox()
        for spin, value in [(self.pan_channel, 0), (self.tilt_channel, 1), (self.zoom_channel, 2)]:
            spin.setRange(0, 31)
            spin.setValue(value)
        self.joystick_state = QtWidgets.QLabel("pan +0.00  tilt +0.00  zoom +0.00")
        layout.addWidget(self.js_device, 0, 0, 1, 4)
        layout.addWidget(QtWidgets.QLabel("Pan"), 1, 0)
        layout.addWidget(self.pan_channel, 1, 1)
        layout.addWidget(QtWidgets.QLabel("Tilt"), 1, 2)
        layout.addWidget(self.tilt_channel, 1, 3)
        layout.addWidget(QtWidgets.QLabel("Zoom"), 2, 0)
        layout.addWidget(self.zoom_channel, 2, 1)
        layout.addWidget(self.joystick_state, 3, 0, 1, 4)
        self.joystick_btn = QtWidgets.QPushButton("Enable Joystick")
        layout.addWidget(self.joystick_btn, 4, 0, 1, 4)
        return widget

    def _group(self, title: str, child: QtWidgets.QWidget) -> CollapsibleSection:
        group = CollapsibleSection(title, expanded=False)
        child.layout().setContentsMargins(0, 0, 0, 0)
        group.layout().addWidget(child)
        return group

    def _connect_signals(self) -> None:
        self.connect_btn.clicked.connect(self._toggle_connection)
        self.video_btn.clicked.connect(self._toggle_video)
        self.joystick_btn.clicked.connect(self._toggle_joystick)
        self.sdk_status_signal.connect(self._on_sdk_status)
        self.telemetry_signal.connect(self._on_telemetry)
        self.sdk.add_connection_listener(self.sdk_status_signal.emit)
        self.sdk.add_telemetry_listener(self.telemetry_signal.emit)

        self.up_btn.pressed_changed.connect(lambda active: self._move_hold(0, 1, active))
        self.down_btn.pressed_changed.connect(lambda active: self._move_hold(0, -1, active))
        self.left_btn.pressed_changed.connect(lambda active: self._move_hold(-1, 0, active))
        self.right_btn.pressed_changed.connect(lambda active: self._move_hold(1, 0, active))
        self.home_btn.clicked.connect(lambda: self._when_connected(self.controller.home))
        self.stop_btn.clicked.connect(self.controller.stop_all_motion)
        self.follow_check.toggled.connect(lambda on: self._when_connected(self.sdk.VLK_EnableFollowMode, 1 if on else 0))
        self.motor_check.toggled.connect(lambda on: self._when_connected(self.sdk.VLK_SwitchMotor, 1 if on else 0))

        self.image_combo.currentIndexChanged.connect(self._set_image_color)
        self.ir_combo.currentIndexChanged.connect(self._set_image_color)
        self.pip_check.toggled.connect(self._set_image_color)
        self.zoom_in_btn.pressed_changed.connect(lambda active: self._zoom_hold(1, active))
        self.zoom_out_btn.pressed_changed.connect(lambda active: self._zoom_hold(-1, active))
        self.focus_in_btn.pressed_changed.connect(lambda active: self._focus_hold(1, active))
        self.focus_out_btn.pressed_changed.connect(lambda active: self._focus_hold(-1, active))
        self.focus_mode.currentIndexChanged.connect(lambda: self._when_connected(self.sdk.VLK_SetFocusMode, self.focus_mode.currentData()))
        self.photo_btn.clicked.connect(lambda: self._when_connected(self.sdk.VLK_Photograph))
        self.record_btn.clicked.connect(self._toggle_recording)

        self.ai_btn.clicked.connect(self._toggle_ai)
        self.stop_track_btn.clicked.connect(self._stop_tracking)
        self.video_label.target_selected.connect(self._track_target)
        self.video_label.stop_tracking_requested.connect(self._stop_tracking)
        self.video_label.zoom_requested.connect(self._video_zoom)

        self.defog_check.toggled.connect(lambda on: self._when_connected(self.sdk.VLK_SwitchDefog, 1 if on else 0))
        self.eo_dzoom_check.toggled.connect(lambda on: self._when_connected(self.sdk.VLK_SwitchEODigitalZoom, 1 if on else 0))
        self.osd_check.toggled.connect(self._set_osd)
        self.cross_check.toggled.connect(self._set_osd)
        self.pitch_yaw_check.toggled.connect(self._set_osd)
        self.laser_check.toggled.connect(self._set_laser_enabled)
        self.laser_single_btn.clicked.connect(self._rangefinder_single)

    def _apply_style(self) -> None:
        apply_style()

    def _toggle_connection(self) -> None:
        try:
            if self.sdk.connected or self.sdk.connection_state == ConnectionState.CONNECTING:
                self.sdk.disconnect()
                self.connect_btn.setText("Connect")
                return
            self.sdk.connect_tcp(self.ip_edit.text().strip(), self.port_spin.value())
            self.connect_btn.setText("Disconnect")
        except Exception as exc:
            self.statusBar().showMessage(str(exc))
            self.conn_status.setText("Error")

    def _toggle_video(self) -> None:
        if self.video_worker:
            self.video_worker.stop()
            self.video_worker = None
            self.video_btn.setText("Open Video")
            self.video_label.clear()
            self.video_label.setText("No signal")
            self.video_status.setText("Idle")
            return
        self.video_worker = VideoWorker(self.rtsp_edit.text().strip(), self)
        self.video_worker.frame_ready.connect(self.video_label.set_frame)
        self.video_worker.status_changed.connect(self.statusBar().showMessage)
        self.video_worker.status_changed.connect(self._video_status_changed)
        self.video_worker.dimensions_changed.connect(self.video_label.set_frame_dimensions)
        self.video_worker.finished.connect(self._video_finished)
        self.video_worker.start()
        self.video_btn.setText("Close Video")

    def _video_status_changed(self, text):
        if text == VIDEO_LIVE:
            label = "VIDEO LIVE"
        elif text in (VIDEO_CONNECTING, VIDEO_RECONNECTING):
            label = text
        elif text == VIDEO_STOPPED:
            label = "VIDEO STOPPED"
        else:
            label = "VIDEO ERROR"
        self.video_status.setText(label)
        self.video_status.setToolTip(text)

    def _video_finished(self):
        worker = self.sender()
        if self.video_worker is worker:
            self.video_worker = None
            self.video_btn.setText("Open Video")
            self.video_label.clear()
            self.video_label.setText("No signal")
        worker.deleteLater()

    def _toggle_joystick(self) -> None:
        if self.joystick_worker:
            self.joystick_worker.stop()
            self.joystick_worker = None
            self.joystick_commander.stop()
            self._joystick_manual_disabled = True
            self.joystick_btn.setText("Enable Joystick")
            return
        if not self.sdk.connected:
            self.statusBar().showMessage("TCP not connected", 2000)
            return
        self._start_joystick()

    def _start_joystick(self) -> bool:
        if self.joystick_worker:
            return True
        config = JoystickConfig(
            device=self.js_device.text().strip(),
            name=DEFAULT_JOYSTICK_NAME,
            pan_channel=self.pan_channel.value(),
            tilt_channel=self.tilt_channel.value(),
            zoom_channel=self.zoom_channel.value(),
        )
        self.joystick_worker = JoystickWorker(config, self)
        self.joystick_worker.state_changed.connect(self._on_joystick_state)
        self.joystick_worker.status_changed.connect(self.statusBar().showMessage)
        self.joystick_worker.raw_event.connect(lambda text: self.statusBar().showMessage(text, 1200))
        self.joystick_worker.finished.connect(self._joystick_finished)
        self.joystick_commander.start()
        self.joystick_worker.start()
        self._joystick_manual_disabled = False
        self.joystick_btn.setText("Stop JS")
        return True

    def _auto_start_joystick_if_available(self) -> None:
        if self.joystick_worker or self._joystick_manual_disabled or not self.sdk.connected:
            return
        device = self.js_device.text().strip()
        if os.path.exists(device):
            self._start_joystick()
        else:
            self.statusBar().showMessage(f"Joystick not found: {device}", 2000)

    def _joystick_finished(self):
        worker = self.sender()
        if self.joystick_worker is worker:
            self.joystick_commander.stop()
            self.joystick_worker = None
            self.joystick_btn.setText("Enable Joystick")
        worker.deleteLater()

    def _update_joystick_speed(self):
        self.joystick_commander.max_yaw_speed = self._speed()
        self.joystick_commander.max_pitch_speed = int(T.VLK_MAX_PITCH_SPEED * self.speed_slider.value() / 100)

    def _on_sdk_status(self, text: str) -> None:
        self.conn_status.setText(text)
        if not self.sdk.connected:
            self.controller.reset()
            self.joystick_commander.reset_command_cache()
        if "TCP" in text or text == "Disconnected" or "Connecting" in text:
            self.connect_btn.setText("Disconnect" if self.sdk.connected else "Connect TCP")
        if self.sdk.connected and "connected" in text.lower():
            self.pip_check.setChecked(False)
            QtCore.QTimer.singleShot(150, self._set_image_color)
            QtCore.QTimer.singleShot(250, self._auto_start_joystick_if_available)
        self.statusBar().showMessage(text, 3000)
        self._refresh_telemetry_status()

    def _on_telemetry(self, telemetry: T.Telemetry) -> None:
        if not self._telemetry_is_fresh():
            self._show_stale_telemetry()
            return
        self.yaw_label.setText(f"Yaw {telemetry.yaw:.2f}")
        self.pitch_label.setText(f"Pitch {telemetry.pitch:.2f}")
        self.roll_label.setText(f"Roll {telemetry.roll:.2f}")
        self.zoom_label.setText(f"Zoom {telemetry.zoom_mag:.2f}x")
        self.fov_label.setText(f"FOV {telemetry.fov_h:.2f} / {telemetry.fov_v:.2f}")
        self.laser_label.setText(f"Laser {telemetry.laser_distance}m")
        self.track_label.setText(f"Track {TRACKER_LABELS.get(telemetry.tracker_status, telemetry.tracker_status)}")
        self.telemetry_status_label.setText("Telemetry OK")
        self.model_label.setText(self.sdk.model_label)
        self.record_btn.setText("Stop Rec" if telemetry.record_mode == T.VLK_RECORD_MODE_RECORD else "Record")
        recording = telemetry.record_mode == T.VLK_RECORD_MODE_RECORD
        self.record_indicator.setText("RECORDING" if recording else "NOT RECORDING")
        self.record_indicator.setProperty("recording", recording)
        self.record_indicator.style().unpolish(self.record_indicator)
        self.record_indicator.style().polish(self.record_indicator)

    def _on_joystick_state(self, state) -> None:
        self.joystick_state.setText(f"pan {state.pan:+.2f}  tilt {state.tilt:+.2f}  zoom {state.zoom:+.2f}")
        self.joystick_commander.set_state(state)

    def _when_connected(self, func, *args) -> None:
        if not self.sdk.connected:
            self.statusBar().showMessage("TCP not connected", 2000)
            return
        func(*args)

    def _speed(self) -> int:
        return int(T.VLK_MAX_YAW_SPEED * self.speed_slider.value() / self.speed_slider.maximum())

    def _move_hold(self, yaw_dir: int, pitch_dir: int, active: bool) -> None:
        if active:
            self.controller.move(yaw_dir * self._speed(), pitch_dir * self._speed(), source=SOURCE_UI)
        else:
            self.controller.stop_move(source=SOURCE_UI)

    def _zoom_hold(self, direction: int, active: bool) -> None:
        self.controller.zoom_continuous(direction if active else 0, 4, source=SOURCE_UI)

    def _focus_hold(self, direction: int, active: bool) -> None:
        if not self.sdk.connected:
            return
        if not active:
            self.sdk.VLK_StopFocus()
        elif direction > 0:
            self.sdk.VLK_FocusIn(4)
        else:
            self.sdk.VLK_FocusOut(4)

    def _set_image_color(self) -> None:
        self.current_image = self.image_combo.currentData()
        self.current_ir_color = self.ir_combo.currentData()
        if self.current_image in (T.VLK_IMAGE_TYPE_IR1, T.VLK_IMAGE_TYPE_IR2, T.VLK_IMAGE_TYPE_FUSION):
            self.current_sensor = T.VLK_SENSOR_IR
            idx = self.track_sensor.findData(T.VLK_SENSOR_IR)
            if idx >= 0:
                self.track_sensor.setCurrentIndex(idx)
        elif self.current_image == T.VLK_IMAGE_TYPE_VISIBLE2:
            self.current_sensor = T.VLK_SENSOR_VISIBLE2
            idx = self.track_sensor.findData(T.VLK_SENSOR_VISIBLE2)
            if idx >= 0:
                self.track_sensor.setCurrentIndex(idx)
        else:
            self.current_sensor = T.VLK_SENSOR_VISIBLE1
            idx = self.track_sensor.findData(T.VLK_SENSOR_VISIBLE1)
            if idx >= 0:
                self.track_sensor.setCurrentIndex(idx)
        self._when_connected(
            self.sdk.VLK_SetImageColor,
            self.current_image,
            1 if self.pip_check.isChecked() else 0,
            self.current_ir_color,
        )

    def _toggle_recording(self) -> None:
        if not self.sdk.connected:
            self.statusBar().showMessage("TCP not connected", 2000)
            return
        is_recording = bool(self.sdk.VLK_IsRecording())
        self.sdk.VLK_SwitchRecord(0 if is_recording else 1)
        self.record_btn.setText("Record" if is_recording else "Stop Rec")

    def _toggle_ai(self) -> None:
        if not self.sdk.connected:
            self.statusBar().showMessage("TCP not connected", 2000)
            return
        if self.ai_btn.text().startswith("Start"):
            self.sdk.VLK_OpenAiState()
            self.sdk.VLK_StartAI()
            self.ai_btn.setText("Stop AI")
        else:
            self._stop_tracking()

    def _stop_tracking(self):
        self.sdk.stop_tracking()
        self.ai_btn.setText("Start AI")

    def _track_target(self, x: int, y: int, video_w: int, video_h: int) -> None:
        if not self.sdk.connected:
            self.statusBar().showMessage("TCP not connected", 2000)
            return
        sensor = self.track_sensor.currentData()
        template = self.track_template.currentData()
        self.sdk.start_tracking(x, y, video_w, video_h, sensor, template)
        self.statusBar().showMessage(f"Tracking click {x},{y} template={template}", 3000)
        self.ai_btn.setText("Stop AI")

    def _video_zoom(self, direction: int) -> None:
        self.controller.zoom_continuous(direction, 4, source=SOURCE_MOUSE)
        self._wheel_zoom_timer.start()

    def _set_laser_enabled(self, enabled: bool) -> None:
        self._when_connected(self.sdk.VLK_SwitchLaser, 1 if enabled else 0)
        self.statusBar().showMessage("Laser on" if enabled else "Laser off", 2000)

    def _rangefinder_single(self) -> None:
        if not self.sdk.connected:
            self.statusBar().showMessage("TCP not connected", 2000)
            return
        if not self.laser_check.isChecked():
            self.laser_check.setChecked(True)
            QtCore.QTimer.singleShot(150, self._rangefinder_single)
            return
        self.sdk.VLK_LaserSingle()
        self.statusBar().showMessage("Laser range requested", 2000)

    def _telemetry_is_fresh(self) -> bool:
        try:
            return bool(self.sdk.telemetry_fresh(TELEMETRY_STALE_TIMEOUT))
        except AttributeError:
            return True

    def _refresh_telemetry_status(self) -> None:
        if self.sdk.connected and not self._telemetry_is_fresh():
            self._show_stale_telemetry()
        elif self.sdk.connected:
            self.telemetry_status_label.setText("Telemetry OK")
        else:
            self.telemetry_status_label.setText("Telemetry --")

    def _show_stale_telemetry(self) -> None:
        self.yaw_label.setText("Yaw --")
        self.pitch_label.setText("Pitch --")
        self.roll_label.setText("Roll --")
        self.zoom_label.setText("Zoom --")
        self.fov_label.setText("FOV --")
        self.laser_label.setText("Laser --")
        self.track_label.setText("Track --")
        self.telemetry_status_label.setText("Telemetry LOST")

    def _set_osd(self) -> None:
        mask = 0
        if self.osd_check.isChecked():
            mask |= T.VLK_OSD_MASK_ENABLE_OSD
        if self.cross_check.isChecked():
            mask |= T.VLK_OSD_MASK_CROSS
        if self.pitch_yaw_check.isChecked():
            mask |= T.VLK_OSD_MASK_PITCH_YAW
        input_mask = T.VLK_OSD_INPUT_MASK_PERMANENT_SAVE
        self.sdk.set_osd(mask, input_mask)

    def closeEvent(self, event) -> None:
        self._wheel_zoom_timer.stop()
        self._telemetry_timer.stop()
        if self.video_worker:
            self.video_worker.stop()
        if self.joystick_worker:
            self.joystick_worker.stop()
        self.joystick_commander.stop()
        self.sdk.shutdown()
        time.sleep(0.05)
        event.accept()


def run(root: Path) -> int:
    app = QtWidgets.QApplication([])
    app.setApplicationName("VControl")
    app.setFont(QtGui.QFont("Inter", 10))
    window = MainWindow(root)
    window.show()
    return app.exec_()
