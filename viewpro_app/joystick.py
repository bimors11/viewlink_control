from __future__ import annotations

import os
import select
import struct
import time
from dataclasses import dataclass

from PyQt5 import QtCore

from .camera_controller import SOURCE_JOYSTICK


JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80
JS_EVENT_FORMAT = "IhBB"
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FORMAT)
DEFAULT_JOYSTICK_NAME = "EdgeTX Radiomaster Pocket Joystick"


@dataclass
class JoystickConfig:
    device: str = "/dev/input/js0"
    name: str = DEFAULT_JOYSTICK_NAME
    pan_channel: int = 0
    tilt_channel: int = 1
    zoom_channel: int = 2
    deadzone: float = 0.08
    invert_pan: bool = False
    invert_tilt: bool = False
    invert_zoom: bool = False


@dataclass
class JoystickState:
    pan: float = 0.0
    tilt: float = 0.0
    zoom: float = 0.0


class JoystickWorker(QtCore.QThread):
    state_changed = QtCore.pyqtSignal(object)
    raw_event = QtCore.pyqtSignal(str)
    status_changed = QtCore.pyqtSignal(str)

    def __init__(self, config: JoystickConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._running = False
        self._fd: int | None = None
        self._axis_values: dict[int, float] = {}

    def run(self) -> None:
        self._running = True
        try:
            self._fd = os.open(self.config.device, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as exc:
            self.status_changed.emit(f"Joystick unavailable: {exc}")
            self._running = False
            return
        self.status_changed.emit(f"Joystick connected: {self.config.name} ({self.config.device})")
        while self._running:
            readable, _, _ = select.select([self._fd], [], [], 0.1)
            if not readable:
                continue
            try:
                data = os.read(self._fd, JS_EVENT_SIZE)
            except BlockingIOError:
                continue
            except OSError as exc:
                self.status_changed.emit(f"Joystick read error: {exc}")
                break
            if len(data) != JS_EVENT_SIZE:
                break
            event_time, value, event_type, number = struct.unpack(JS_EVENT_FORMAT, data)
            clean_type = event_type & ~JS_EVENT_INIT
            if clean_type == JS_EVENT_AXIS:
                normalized = max(-1.0, min(1.0, value / 32767.0))
                if abs(normalized) < self.config.deadzone:
                    normalized = 0.0
                self._axis_values[number] = normalized
                self.raw_event.emit(f"axis {number}: {normalized:+.2f}")
                self.state_changed.emit(self._mapped_state())
            elif clean_type == JS_EVENT_BUTTON:
                self.raw_event.emit(f"button {number + 1}: {value}")
            del event_time
        self._close()
        self.status_changed.emit("Joystick stopped")

    def stop(self) -> None:
        self._running = False
        self.wait(1000)
        self._close()

    def _close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def _mapped_state(self) -> JoystickState:
        pan = self._axis_values.get(self.config.pan_channel, 0.0)
        tilt = self._axis_values.get(self.config.tilt_channel, 0.0)
        zoom = self._axis_values.get(self.config.zoom_channel, 0.0)
        if self.config.invert_pan:
            pan *= -1
        if self.config.invert_tilt:
            tilt *= -1
        if self.config.invert_zoom:
            zoom *= -1
        return JoystickState(pan=pan, tilt=tilt, zoom=zoom)


class JoystickCommander(QtCore.QObject):
    status_changed = QtCore.pyqtSignal(str)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.state = JoystickState()
        self.max_yaw_speed = 1200
        self.max_pitch_speed = 1200
        self.zoom_speed = 4
        self._last_move = (0, 0)
        self._last_zoom_dir = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self.state = JoystickState()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.state = JoystickState()
        self._send_neutral()

    def set_state(self, state: JoystickState) -> None:
        self.state = state

    def _tick(self) -> None:
        if not self.controller.connected:
            self.controller.reset()
            self.reset_command_cache()
            return
        yaw = int(self.state.pan * self.max_yaw_speed)
        pitch = int(-self.state.tilt * self.max_pitch_speed)
        zoom_dir = 1 if self.state.zoom > 0.2 else -1 if self.state.zoom < -0.2 else 0
        if (yaw, pitch) != self._last_move:
            if yaw or pitch:
                self.controller.move(yaw, pitch, source=SOURCE_JOYSTICK)
            else:
                self.controller.stop_move(source=SOURCE_JOYSTICK)
            self._last_move = (yaw, pitch)
        if zoom_dir != self._last_zoom_dir:
            self.controller.zoom_continuous(zoom_dir, self.zoom_speed, source=SOURCE_JOYSTICK)
            self._last_zoom_dir = zoom_dir

    def _send_neutral(self) -> None:
        self.controller.stop_move(source=SOURCE_JOYSTICK)
        self.controller.stop_zoom(source=SOURCE_JOYSTICK)
        self.reset_command_cache()

    def reset_command_cache(self) -> None:
        self._last_move = (0, 0)
        self._last_zoom_dir = 0
