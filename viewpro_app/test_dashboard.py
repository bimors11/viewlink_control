"""Offline dashboard checks: python3 -m unittest viewpro_app.test_dashboard."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import subprocess
import time
import unittest
from unittest.mock import MagicMock, patch

from PyQt5 import QtCore, QtGui, QtTest, QtWidgets

from .dashboard_theme import CollapsibleSection
from .joystick import JoystickConfig, JoystickState, JoystickWorker
from .ui import MainWindow
from .video import VideoWorker


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.sdk = MagicMock(connected=True)
        self.sdk.version.return_value = "test"
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
        self.assertEqual([w.pan_channel.value(), w.tilt_channel.value(), w.zoom_channel.value()], [1, 2, 3])
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
        self.sdk.move.assert_called_with(w._speed() // 2, w.joystick_commander.max_pitch_speed // 2)
        self.sdk.zoom_continuous.assert_called_with(1, 4)
        w.joystick_commander.stop()
        self.assertEqual(w.joystick_commander.state, JoystickState())

    def test_video_click_mapping_and_resize(self):
        w = self.window
        image = QtGui.QImage(960, 540, QtGui.QImage.Format_RGB888)
        image.fill(QtGui.QColor("#25804a"))
        w.video_label.set_frame(image)
        center = w.video_label.rect().center()
        QtTest.QTest.mouseClick(w.video_label, QtCore.Qt.LeftButton, pos=center)
        args = self.sdk.start_tracking.call_args.args
        self.assertAlmostEqual(args[0], 480, delta=2)
        self.assertAlmostEqual(args[1], 270, delta=2)
        self.assertEqual(args[2:4], (960, 540))
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


if __name__ == "__main__":
    unittest.main()
