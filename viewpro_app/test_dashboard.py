"""Offline dashboard checks: python3 -m unittest viewpro_app.test_dashboard."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import subprocess
import time
import unittest
from unittest.mock import MagicMock, patch

from PyQt5 import QtCore, QtGui, QtTest, QtWidgets

from . import viewlink_types as T
from .camera_controller import CameraController, SOURCE_JOYSTICK, SOURCE_MOUSE
from .dashboard_theme import CollapsibleSection
from .joystick import JoystickConfig, JoystickState, JoystickWorker
from .sdk import ConnectionState, TELEMETRY_STALE_TIMEOUT, TRACK_VIDEO_HEIGHT, TRACK_VIDEO_WIDTH, ViewLinkSDK
from .ui import MainWindow
from .video import VIDEO_ERROR, VIDEO_RECONNECTING, VIDEO_STOPPED, VideoWorker


class FakeSDK:
    def __init__(self):
        self.connected = True
        self.calls = []

    def move(self, yaw, pitch):
        self.calls.append(("move", yaw, pitch))

    def VLK_Stop(self):
        self.calls.append(("stop_move",))

    def VLK_ZoomIn(self, speed):
        self.calls.append(("zoom_in", speed))

    def VLK_ZoomOut(self, speed):
        self.calls.append(("zoom_out", speed))

    def VLK_StopZoom(self):
        self.calls.append(("stop_zoom",))

    def VLK_Home(self):
        self.calls.append(("home",))

    def VLK_TurnTo(self, yaw, pitch):
        self.calls.append(("turn_to", yaw, pitch))

    def stop_all_motion(self):
        self.calls.append(("stop_all",))


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.sdk = MagicMock(connected=True)
        self.sdk.connection_state = ConnectionState.CONNECTED
        self.sdk.version.return_value = "test"
        self.sdk.telemetry_fresh.return_value = True
        with patch("viewpro_app.ui.ViewLinkSDK", return_value=self.sdk):
            self.window = MainWindow(Path.cwd())
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_layout_and_collapse(self):
        w = self.window
        self.assertEqual(w.ip_edit.text(), "192.168.144.25")
        self.assertEqual([w.pan_channel.value(), w.tilt_channel.value(), w.zoom_channel.value()], [0, 1, 2])
        removed_label = "Track" + " Center"
        self.assertNotIn(removed_label, [button.text() for button in w.findChildren(QtWidgets.QPushButton)])
        for section in w.findChildren(CollapsibleSection):
            self.assertFalse(section.header.isChecked())
            section.set_expanded(True)
        self.app.processEvents()
        self.assertGreater(w.control_scroll.verticalScrollBar().maximum(), 0)
        for size in [(1440, 900), (1280, 720)]:
            w.resize(*size)
            self.app.processEvents()
            self.assertEqual((w.width(), w.height()), size)
            self.assertEqual(w.control_scroll.horizontalScrollBar().maximum(), 0)
        previous = w.video_label.width()
        w.sidebar_toggle.click()
        self.app.processEvents()
        self.assertGreater(w.video_label.width(), previous)
        self.assertFalse(w.control_scroll.isVisible())

    def test_gimbal_and_joystick_mapping(self):
        w = self.window
        w.speed_slider.setValue(50)
        w.up_btn.pressed_changed.emit(True)
        self.sdk.move.assert_called_with(0, w._speed())
        w.up_btn.pressed_changed.emit(False)
        self.sdk.VLK_Stop.assert_called()
        worker = JoystickWorker(JoystickConfig())
        worker._axis_values = {0: 0.5, 1: -0.5, 2: 1}
        state = worker._mapped_state()
        self.assertEqual(state, JoystickState(0.5, -0.5, 1))
        w.joystick_commander.set_state(state)
        w.joystick_commander._tick()
        self.sdk.move.assert_called_with(w._speed() // 2, -w.joystick_commander.max_pitch_speed // 2)
        self.sdk.VLK_ZoomIn.assert_called_with(4)
        w.joystick_commander.stop()
        self.assertEqual(w.joystick_commander.state, JoystickState())

    def test_tracking_does_not_disable_active_joystick(self):
        w = self.window
        w.joystick_worker = object()
        try:
            with patch.object(w, "_toggle_joystick") as toggle:
                w._track_target(321, 222, TRACK_VIDEO_WIDTH, TRACK_VIDEO_HEIGHT)
            toggle.assert_not_called()
            self.assertIsNotNone(w.joystick_worker)
        finally:
            w.joystick_worker = None

    def test_auto_start_joystick_when_device_exists(self):
        w = self.window
        with patch("viewpro_app.ui.os.path.exists", return_value=True), patch.object(w, "_start_joystick", return_value=True) as start:
            w._auto_start_joystick_if_available()
        start.assert_called_once()

    def test_tcp_connected_forces_pip_off(self):
        w = self.window
        w.pip_check.setChecked(True)
        self.sdk.VLK_SetImageColor.reset_mock()
        w._on_sdk_status("TCP connected")
        QtTest.QTest.qWait(250)
        self.assertFalse(w.pip_check.isChecked())
        self.sdk.VLK_SetImageColor.assert_called_with(w.current_image, 0, w.current_ir_color)

    def test_joystick_reconnect_resends_cached_position(self):
        sdk = FakeSDK()
        controller = CameraController(sdk)
        commander = self.window.joystick_commander
        commander.controller = controller
        commander.set_state(JoystickState(pan=0.5, tilt=0.0, zoom=0.0))
        commander._tick()
        self.assertEqual(sdk.calls[-1], ("move", commander.max_yaw_speed // 2, 0))
        first_count = len(sdk.calls)
        sdk.connected = False
        commander._tick()
        sdk.connected = True
        commander._tick()
        self.assertGreater(len(sdk.calls), first_count)
        self.assertEqual(sdk.calls[-1], ("move", commander.max_yaw_speed // 2, 0))

    def test_zoom_arbitration_restores_joystick_after_mouse_stop(self):
        sdk = FakeSDK()
        controller = CameraController(sdk)
        controller.zoom_in(4, source=SOURCE_JOYSTICK)
        controller.zoom_out(4, source=SOURCE_MOUSE)
        controller.stop_zoom(source=SOURCE_MOUSE)
        self.assertEqual(sdk.calls, [("zoom_in", 4), ("zoom_out", 4), ("zoom_in", 4)])

    def test_connection_state_transitions(self):
        sdk = ViewLinkSDK.__new__(ViewLinkSDK)
        sdk._connection_state = ConnectionState.DISCONNECTED
        sdk._connected = False
        sdk._conn_listeners = []
        sdk._set_connection_state(ConnectionState.CONNECTING, "Connecting 192.0.2.1:2000")
        self.assertEqual(sdk.connection_state, ConnectionState.CONNECTING)
        with patch.object(sdk, "VLK_QueryDevConfiguration", create=True):
            sdk._on_connection_status(T.VLK_CONN_STATUS_TCP_CONNECTED, None, 0, 0)
        self.assertEqual(sdk.connection_state, ConnectionState.CONNECTED)
        self.assertTrue(sdk._connected)
        sdk._on_connection_status(T.VLK_CONN_STATUS_TCP_DISCONNECTED, None, 0, 0)
        self.assertEqual(sdk.connection_state, ConnectionState.DISCONNECTED)
        self.assertFalse(sdk._connected)

    def test_sdk_click_tracking_does_not_start_center_track(self):
        sdk = ViewLinkSDK.__new__(ViewLinkSDK)
        sdk._initialized = True
        sdk._conn_listeners = []
        calls = []
        sdk.VLK_IsTCPConnected = lambda: 1
        sdk.VLK_OpenAiState = lambda: calls.append(("open_ai",))
        sdk.VLK_StartAI = lambda: calls.append(("start_ai",))
        sdk.VLK_StartTrack = lambda: calls.append(("start_track",))
        sdk.VLK_EnableTrackMode = lambda param: calls.append(("enable_track_mode",))
        sdk.VLK_TrackTargetPositionEx = lambda param, x, y, w, h: calls.append(("track_target", x, y, w, h))
        sdk.start_tracking(321, 222, TRACK_VIDEO_WIDTH, TRACK_VIDEO_HEIGHT, T.VLK_SENSOR_VISIBLE1, T.VLK_TRACK_TEMPLATE_SIZE_64)
        self.assertIn(("track_target", 321, 222, TRACK_VIDEO_WIDTH, TRACK_VIDEO_HEIGHT), calls)
        self.assertNotIn(("start_track",), calls)
        self.assertNotIn(("enable_track_mode",), calls)

    def test_telemetry_stale_detection(self):
        sdk = ViewLinkSDK.__new__(ViewLinkSDK)
        sdk._last_telemetry_rx = time.monotonic()
        self.assertTrue(sdk.telemetry_fresh(TELEMETRY_STALE_TIMEOUT))
        sdk._last_telemetry_rx = time.monotonic() - TELEMETRY_STALE_TIMEOUT - 0.1
        self.assertFalse(sdk.telemetry_fresh(TELEMETRY_STALE_TIMEOUT))
        sdk._last_telemetry_rx = time.monotonic()
        self.assertTrue(sdk.telemetry_fresh(TELEMETRY_STALE_TIMEOUT))

    def test_video_click_mapping_and_resize(self):
        w = self.window
        image = QtGui.QImage(960, 540, QtGui.QImage.Format_RGB888)
        image.fill(QtGui.QColor("#25804a"))
        w.video_label.set_frame(image)
        center = w.video_label.rect().center()
        QtTest.QTest.mouseClick(w.video_label, QtCore.Qt.LeftButton, pos=center)
        args = self.sdk.start_tracking.call_args.args
        self.assertAlmostEqual(args[0], TRACK_VIDEO_WIDTH // 2, delta=3)
        self.assertAlmostEqual(args[1], TRACK_VIDEO_HEIGHT // 2, delta=3)
        self.assertEqual(args[2:4], (TRACK_VIDEO_WIDTH, TRACK_VIDEO_HEIGHT))
        self.assertEqual(args[5], T.VLK_TRACK_TEMPLATE_SIZE_64)
        self.sdk.start_tracking.reset_mock()
        target_pos = center + QtCore.QPoint(160, -90)
        expected = w.video_label._map_widget_to_tracking_frame(target_pos)
        w.track_template.setCurrentIndex(w.track_template.findData(T.VLK_TRACK_TEMPLATE_SIZE_128))
        QtTest.QTest.mouseClick(w.video_label, QtCore.Qt.LeftButton, pos=target_pos)
        args = self.sdk.start_tracking.call_args.args
        self.assertEqual(args[0:2], expected)
        self.assertNotAlmostEqual(args[0], TRACK_VIDEO_WIDTH // 2, delta=10)
        self.assertEqual(args[2:4], (TRACK_VIDEO_WIDTH, TRACK_VIDEO_HEIGHT))
        self.assertEqual(args[5], T.VLK_TRACK_TEMPLATE_SIZE_128)
        self.sdk.start_tracking.reset_mock()
        QtTest.QTest.mouseClick(w.video_label, QtCore.Qt.LeftButton, pos=QtCore.QPoint(2, 2))
        self.sdk.start_tracking.assert_not_called()
        QtTest.QTest.mouseClick(w.video_label, QtCore.Qt.RightButton, pos=center)
        self.sdk.stop_tracking.assert_called()
        w.resize(1280, 720)
        self.app.processEvents()
        self.assertEqual(w.video_label._source.size(), image.size())
        w.video_label.clear()
        self.assertIsNone(w.video_label._map_widget_to_frame(center))

    def test_video_drag_release_tracks_release_point(self):
        w = self.window
        image = QtGui.QImage(960, 540, QtGui.QImage.Format_RGB888)
        image.fill(QtGui.QColor("#25804a"))
        w.video_label.set_frame(image)
        start = w.video_label.rect().center() - QtCore.QPoint(120, 80)
        end = w.video_label.rect().center() + QtCore.QPoint(120, 80)
        expected = w.video_label._map_widget_to_tracking_frame(end)
        QtTest.QTest.mousePress(w.video_label, QtCore.Qt.LeftButton, pos=start)
        QtTest.QTest.mouseMove(w.video_label, end)
        QtTest.QTest.mouseRelease(w.video_label, QtCore.Qt.LeftButton, pos=end)
        args = self.sdk.start_tracking.call_args.args
        self.assertEqual(args[0:2], expected)
        self.assertEqual(args[2:4], (TRACK_VIDEO_WIDTH, TRACK_VIDEO_HEIGHT))
        self.assertEqual(args[5], T.VLK_TRACK_TEMPLATE_SIZE_64)

    def test_visible2_tracking_uses_visible2_sensor(self):
        w = self.window
        visible2_idx = w.image_combo.findData(T.VLK_IMAGE_TYPE_VISIBLE2)
        w.image_combo.setCurrentIndex(visible2_idx)
        self.assertEqual(w.track_sensor.currentData(), T.VLK_SENSOR_VISIBLE2)
        w._track_target(480, 270, 960, 540)
        args = self.sdk.start_tracking.call_args.args
        self.assertEqual(args[4], T.VLK_SENSOR_VISIBLE2)

    def test_rangefinder_auto_enables_laser_before_range(self):
        w = self.window
        w.laser_check.setChecked(False)
        self.sdk.VLK_SwitchLaser.reset_mock()
        self.sdk.VLK_LaserSingle.reset_mock()
        w._rangefinder_single()
        QtTest.QTest.qWait(250)
        self.sdk.VLK_SwitchLaser.assert_called_with(1)
        self.sdk.VLK_LaserSingle.assert_called()

    def test_ffmpeg_frames_and_stop(self):
        import shutil
        if not shutil.which("ffmpeg"):
            self.skipTest("FFmpeg is not installed")
        spawn = subprocess.Popen
        processes = []

        def synthetic_stream(*args, **kwargs):
            process = spawn([
                "ffmpeg", "-loglevel", "error", "-re", "-f", "lavfi",
                "-i", "testsrc2=size=640x480:rate=15", "-threads", "1",
                "-pix_fmt", "rgb24", "-vcodec", "ppm", "-f", "image2pipe", "pipe:1",
            ], **kwargs)
            processes.append(process)
            return process

        worker = VideoWorker("rtsp://test")
        frames = []
        worker.frame_ready.connect(frames.append)
        with patch("viewpro_app.video.subprocess.Popen", side_effect=synthetic_stream):
            worker.start()
            try:
                deadline = time.monotonic() + 5
                while not frames and time.monotonic() < deadline:
                    QtTest.QTest.qWait(20)
            finally:
                worker.stop()
        self.assertTrue(frames, "No FFmpeg frame decoded")
        self.assertEqual((frames[0].width(), frames[0].height()), (640, 480))
        self.assertNotEqual(frames[0].pixelColor(20, 20), frames[0].pixelColor(400, 200))
        self.assertFalse(worker.isRunning())
        self.assertIsNotNone(processes[0].poll())

    def test_video_retry_and_manual_stop(self):
        class RetryWorker(VideoWorker):
            def __init__(self):
                super().__init__("rtsp://test")
                self.retry_delays = [0.05]
                self.stream_calls = 0

            def _stream_once(self):
                self.stream_calls += 1
                if self.stream_calls == 1:
                    return "Connection refused"
                while not self.isInterruptionRequested():
                    self.msleep(10)
                return ""

        worker = RetryWorker()
        statuses = []
        worker.status_changed.connect(statuses.append)
        with patch("viewpro_app.video.shutil.which", return_value="/usr/bin/ffmpeg"):
            worker.start()
            deadline = time.monotonic() + 2
            while (worker.stream_calls < 2 or VIDEO_RECONNECTING not in statuses) and time.monotonic() < deadline:
                QtTest.QTest.qWait(20)
            worker.stop()
        self.assertGreaterEqual(worker.stream_calls, 2)
        self.assertTrue(any(status.startswith(VIDEO_ERROR) for status in statuses))
        self.assertIn(VIDEO_RECONNECTING, statuses)
        stopped_calls = worker.stream_calls
        QtTest.QTest.qWait(100)
        self.assertEqual(worker.stream_calls, stopped_calls)
        self.assertIn(VIDEO_STOPPED, statuses)


if __name__ == "__main__":
    unittest.main()
