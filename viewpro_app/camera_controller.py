from __future__ import annotations

from dataclasses import dataclass

from . import viewlink_types as T


SOURCE_JOYSTICK = "joystick"
SOURCE_MOUSE = "mouse"
SOURCE_UI = "ui"


_ZOOM_PRIORITY = {
    SOURCE_UI: 10,
    SOURCE_JOYSTICK: 20,
    SOURCE_MOUSE: 30,
}

_MOVE_PRIORITY = {
    SOURCE_UI: 10,
    SOURCE_MOUSE: 20,
    SOURCE_JOYSTICK: 30,
}


@dataclass(frozen=True)
class _ZoomIntent:
    direction: int
    speed: int


@dataclass(frozen=True)
class _MoveIntent:
    yaw: int
    pitch: int


class CameraController:
    """Central command surface for gimbal/camera commands that can conflict."""

    def __init__(self, sdk):
        self.sdk = sdk
        self._zoom_intents: dict[str, _ZoomIntent] = {}
        self._move_intents: dict[str, _MoveIntent] = {}
        self._effective_zoom: _ZoomIntent | None = None
        self._effective_move: _MoveIntent | None = None

    @property
    def connected(self) -> bool:
        return bool(getattr(self.sdk, "connected", False))

    def reset(self) -> None:
        self._zoom_intents.clear()
        self._move_intents.clear()
        self._effective_zoom = None
        self._effective_move = None

    def move(self, yaw: int, pitch: int, source: str = SOURCE_UI) -> None:
        self._move_intents[source] = _MoveIntent(
            self._clamp(yaw, T.VLK_MAX_YAW_SPEED),
            self._clamp(pitch, T.VLK_MAX_PITCH_SPEED),
        )
        self._apply_move()

    def stop_move(self, source: str = SOURCE_UI) -> None:
        self._move_intents.pop(source, None)
        self._apply_move()

    def zoom_in(self, speed: int = 4, source: str = SOURCE_UI) -> None:
        self._zoom_intents[source] = _ZoomIntent(1, self._zoom_speed(speed))
        self._apply_zoom()

    def zoom_out(self, speed: int = 4, source: str = SOURCE_UI) -> None:
        self._zoom_intents[source] = _ZoomIntent(-1, self._zoom_speed(speed))
        self._apply_zoom()

    def stop_zoom(self, source: str = SOURCE_UI) -> None:
        self._zoom_intents.pop(source, None)
        self._apply_zoom()

    def zoom_continuous(self, amount: float, speed: int = 4, source: str = SOURCE_UI) -> None:
        if amount > 0:
            self.zoom_in(speed, source)
        elif amount < 0:
            self.zoom_out(speed, source)
        else:
            self.stop_zoom(source)

    def home(self) -> None:
        if self.connected:
            self.sdk.VLK_Home()

    def turn_to(self, yaw: float, pitch: float) -> None:
        if self.connected:
            self.sdk.VLK_TurnTo(yaw, pitch)

    def stop_all_motion(self) -> None:
        self.reset()
        if self.connected:
            self.sdk.stop_all_motion()

    def _apply_move(self) -> None:
        desired = self._highest_priority(self._move_intents, _MOVE_PRIORITY)
        if not self.connected:
            self._effective_move = None
            return
        if desired is None:
            if self._effective_move is not None:
                self.sdk.VLK_Stop()
            self._effective_move = None
            return
        if desired != self._effective_move:
            self.sdk.move(desired.yaw, desired.pitch)
            self._effective_move = desired

    def _apply_zoom(self) -> None:
        desired = self._highest_priority(self._zoom_intents, _ZOOM_PRIORITY)
        if not self.connected:
            self._effective_zoom = None
            return
        if desired is None:
            if self._effective_zoom is not None:
                self.sdk.VLK_StopZoom()
            self._effective_zoom = None
            return
        if desired != self._effective_zoom:
            if desired.direction > 0:
                self.sdk.VLK_ZoomIn(desired.speed)
            else:
                self.sdk.VLK_ZoomOut(desired.speed)
            self._effective_zoom = desired

    @staticmethod
    def _highest_priority(intents: dict, priorities: dict[str, int]):
        if not intents:
            return None
        return max(intents.items(), key=lambda item: priorities.get(item[0], 0))[1]

    @staticmethod
    def _clamp(value: int, limit: int) -> int:
        return max(-limit, min(limit, int(value)))

    @staticmethod
    def _zoom_speed(speed: int) -> int:
        return max(T.VLK_MIN_ZOOM_SPEED, min(T.VLK_MAX_ZOOM_SPEED, abs(int(speed))))
