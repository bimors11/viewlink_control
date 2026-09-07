from __future__ import annotations

import ctypes as C
import os
import platform
import shutil
import threading
from pathlib import Path
from typing import Callable, Optional

from . import viewlink_types as T


class ViewLinkSDK:
    def __init__(self, root: Path):
        self.root = root
        self.lib_path = self._find_library(root)
        self._lib = C.CDLL(str(self.lib_path), mode=os.RTLD_GLOBAL)
        self._lock = threading.RLock()
        self._initialized = False
        self._connected = False
        self._model_name = ""
        self._model_code = 0
        self._firmware = ""
        self._device_id = ""
        self._serial_no = ""
        self._telemetry = T.Telemetry()
        self._status_text = "Idle"
        self._conn_listeners: list[Callable[[str], None]] = []
        self._telemetry_listeners: list[Callable[[T.Telemetry], None]] = []
        self._bind_functions()
        self._conn_cb = T.ConnStatusCB(self._on_connection_status)
        self._dev_cb = T.DevStatusCB(self._on_device_status)

    @staticmethod
    def _find_library(root: Path) -> Path:
        arch = platform.machine().lower()
        if arch in ("x86_64", "amd64"):
            rel_dir = "linux-x86_64"
        elif arch in ("aarch64", "arm64"):
            rel_dir = "linux-aarch64"
        else:
            raise RuntimeError(f"Unsupported architecture for bundled ViewLink SDK: {arch}")
        candidates = [
            root / "viewpro_app" / "lib" / rel_dir / "libViewLink.so",
            Path(__file__).resolve().parent / "lib" / rel_dir / "libViewLink.so",
            root / "ViewlinkSDK" / "bin" / rel_dir / "libViewLink.so",
        ]
        for lib in candidates:
            if lib.exists():
                return lib
        tried = "\n  ".join(str(path) for path in candidates)
        raise RuntimeError(f"ViewLink library not found. Tried:\n  {tried}")

    def _bind(self, name: str, argtypes: list, restype=None):
        fn = getattr(self._lib, name)
        fn.argtypes = argtypes
        fn.restype = restype
        return fn

    def _bind_functions(self) -> None:
        self.GetSDKVersion = self._bind("GetSDKVersion", [], C.c_char_p)
        self.VLK_Init = self._bind("VLK_Init", [], C.c_int)
        self.VLK_UnInit = self._bind("VLK_UnInit", [], None)
        self.VLK_Connect = self._bind("VLK_Connect", [C.POINTER(T.VLK_CONN_PARAM), T.ConnStatusCB, C.c_void_p], C.c_int)
        self.VLK_Disconnect = self._bind("VLK_Disconnect", [], None)
        self.VLK_DisconnectTCP = self._bind("VLK_DisconnectTCP", [], None)
        self.VLK_IsConnected = self._bind("VLK_IsConnected", [], C.c_int)
        self.VLK_IsTCPConnected = self._bind("VLK_IsTCPConnected", [], C.c_int)
        self.VLK_SetKeepAliveInterval = self._bind("VLK_SetKeepAliveInterval", [C.c_int], None)
        self.VLK_RegisterDevStatusCB = self._bind("VLK_RegisterDevStatusCB", [T.DevStatusCB, C.c_void_p], None)
        self.VLK_QueryDevConfiguration = self._bind("VLK_QueryDevConfiguration", [], None)

        self.VLK_Move = self._bind("VLK_Move", [C.c_short, C.c_short], None)
        self.VLK_Stop = self._bind("VLK_Stop", [], None)
        self.VLK_Home = self._bind("VLK_Home", [], None)
        self.VLK_TurnTo = self._bind("VLK_TurnTo", [C.c_double, C.c_double], None)
        self.VLK_SwitchMotor = self._bind("VLK_SwitchMotor", [C.c_int], None)
        self.VLK_IsMotorOn = self._bind("VLK_IsMotorOn", [], C.c_int)
        self.VLK_EnableFollowMode = self._bind("VLK_EnableFollowMode", [C.c_int], None)
        self.VLK_IsFollowMode = self._bind("VLK_IsFollowMode", [], C.c_int)

        self.VLK_ZoomIn = self._bind("VLK_ZoomIn", [C.c_short], None)
        self.VLK_ZoomOut = self._bind("VLK_ZoomOut", [C.c_short], None)
        self.VLK_StopZoom = self._bind("VLK_StopZoom", [], None)
        self.VLK_ZoomTo = self._bind("VLK_ZoomTo", [C.c_float], None)
        self.VLK_FocusIn = self._bind("VLK_FocusIn", [C.c_short], None)
        self.VLK_FocusOut = self._bind("VLK_FocusOut", [C.c_short], None)
        self.VLK_StopFocus = self._bind("VLK_StopFocus", [], None)
        self.VLK_SetFocusMode = self._bind("VLK_SetFocusMode", [C.c_int], None)
        self.VLK_GetFocusMode = self._bind("VLK_GetFocusMode", [], C.c_int)

        self.VLK_SetImageColor = self._bind("VLK_SetImageColor", [C.c_int, C.c_int, C.c_int], None)
        self.VLK_Photograph = self._bind("VLK_Photograph", [], None)
        self.VLK_SwitchRecord = self._bind("VLK_SwitchRecord", [C.c_int], None)
        self.VLK_IsRecording = self._bind("VLK_IsRecording", [], C.c_int)
        self.VLK_SetRecordMode = self._bind("VLK_SetRecordMode", [C.c_int], None)
        self.VLK_GetRecordMode = self._bind("VLK_GetRecordMode", [], C.c_int)
        self.VLK_SwitchDefog = self._bind("VLK_SwitchDefog", [C.c_int], None)
        self.VLK_IsDefogOn = self._bind("VLK_IsDefogOn", [], C.c_int)
        self.VLK_SwitchEODigitalZoom = self._bind("VLK_SwitchEODigitalZoom", [C.c_int], None)
        self.VLK_IRDigitalZoomIn = self._bind("VLK_IRDigitalZoomIn", [C.c_short], None)
        self.VLK_IRDigitalZoomOut = self._bind("VLK_IRDigitalZoomOut", [C.c_short], None)

        self.VLK_OpenAiState = self._bind("VLK_OpenAiState", [], None)
        self.VLK_CloseAiState = self._bind("VLK_CloseAiState", [], None)
        self.VLK_StartAI = self._bind("VLK_StartAI", [], None)
        self.VLK_StopAI = self._bind("VLK_StopAI", [], None)
        self.VLK_OpenTrackXY = self._bind("VLK_OpenTrackXY", [], None)
        self.VLK_CloseTrackXY = self._bind("VLK_CloseTrackXY", [], None)
        self.VLK_EnableTrackMode = self._bind("VLK_EnableTrackMode", [C.POINTER(T.VLK_TRACK_MODE_PARAM)], None)
        self.VLK_DisableTrackMode = self._bind("VLK_DisableTrackMode", [], None)
        self.VLK_TrackTargetPositionEx = self._bind(
            "VLK_TrackTargetPositionEx",
            [C.POINTER(T.VLK_TRACK_MODE_PARAM), C.c_int, C.c_int, C.c_int, C.c_int],
            None,
        )
        self.VLK_StartTrack = self._bind("VLK_StartTrack", [], None)
        self.VLK_StopTrack = self._bind("VLK_StopTrack", [], None)
        self.VLK_IsTracking = self._bind("VLK_IsTracking", [], C.c_int)

        self.VLK_SetOSD = self._bind("VLK_SetOSD", [C.POINTER(T.VLK_OSD_PARAM)], None)
        self.VLK_SwitchLaser = self._bind("VLK_SwitchLaser", [C.c_int], None)
        self.VLK_LaserSingle = self._bind("VLK_LaserSingle", [], None)
        self.VLK_LaserZoomIn = self._bind("VLK_LaserZoomIn", [C.c_short], None)
        self.VLK_LaserZoomOut = self._bind("VLK_LaserZoomOut", [C.c_short], None)
        self.VLK_LaserStopZoom = self._bind("VLK_LaserStopZoom", [], None)
        self.VLK_SetLaserZoomMode = self._bind("VLK_SetLaserZoomMode", [C.c_int], None)

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self._prepare_log_dir()
            ret = self.VLK_Init()
            if ret != T.VLK_ERROR_NO_ERROR:
                raise RuntimeError(f"VLK_Init failed: {ret}")
            self.VLK_SetKeepAliveInterval(300)
            self.VLK_RegisterDevStatusCB(self._dev_cb, None)
            self._initialized = True

    def _prepare_log_dir(self) -> None:
        log_path = self.root / "VLKLog"
        if log_path.is_dir():
            shutil.rmtree(log_path)
        elif log_path.exists():
            log_path.unlink()

    def shutdown(self) -> None:
        with self._lock:
            if self._initialized:
                try:
                    self.stop_all_motion()
                    self.stop_tracking()
                    self.VLK_Disconnect()
                finally:
                    self.VLK_UnInit()
                    self._initialized = False
                    self._connected = False

    def version(self) -> str:
        raw = self.GetSDKVersion()
        return raw.decode("utf-8", errors="ignore") if raw else "unknown"

    def connect_tcp(self, ip: str, port: int) -> None:
        self.initialize()
        param = T.VLK_CONN_PARAM()
        C.memset(C.byref(param), 0, C.sizeof(param))
        param.emType = T.VLK_CONN_TYPE_TCP
        ip_bytes = ip.encode("ascii", errors="ignore")[:15]
        param.ConnParam.IPAddr.szIPV4 = ip_bytes
        param.ConnParam.IPAddr.iPort = int(port)
        ret = self.VLK_Connect(C.byref(param), self._conn_cb, None)
        if ret != T.VLK_ERROR_NO_ERROR:
            raise RuntimeError(f"VLK_Connect failed: {ret}")
        self._set_status(f"Connecting {ip}:{port}")

    def disconnect(self) -> None:
        self.stop_all_motion()
        self.stop_tracking()
        self.VLK_DisconnectTCP()
        self._connected = False
        self._set_status("Disconnected")

    @property
    def connected(self) -> bool:
        return bool(self.VLK_IsTCPConnected()) if self._initialized else False

    @property
    def telemetry(self) -> T.Telemetry:
        return self._telemetry

    @property
    def model_label(self) -> str:
        if self._model_name:
            return f"{self._model_name}  firmware {self._firmware or '-'}"
        return "Unknown model"

    def add_connection_listener(self, callback: Callable[[str], None]) -> None:
        self._conn_listeners.append(callback)

    def add_telemetry_listener(self, callback: Callable[[T.Telemetry], None]) -> None:
        self._telemetry_listeners.append(callback)

    def move(self, yaw_speed: int, pitch_speed: int) -> None:
        if not self.connected:
            return
        self.VLK_Move(self._clamp_short(yaw_speed, T.VLK_MAX_YAW_SPEED), self._clamp_short(pitch_speed, T.VLK_MAX_PITCH_SPEED))

    def stop_all_motion(self) -> None:
        if not self._initialized:
            return
        self.VLK_Stop()
        self.VLK_StopZoom()
        self.VLK_StopFocus()
        self.VLK_LaserStopZoom()

    def zoom_continuous(self, amount: float, speed: int = 4) -> None:
        if not self.connected:
            return
        speed = max(T.VLK_MIN_ZOOM_SPEED, min(T.VLK_MAX_ZOOM_SPEED, abs(int(speed))))
        if amount > 0:
            self.VLK_ZoomIn(speed)
        elif amount < 0:
            self.VLK_ZoomOut(speed)
        else:
            self.VLK_StopZoom()

    def start_tracking(self, x: int, y: int, video_w: int, video_h: int, sensor: int, template_size: int) -> None:
        if not self.connected:
            self._set_status("Tracking ignored: TCP not connected")
            return
        param = T.VLK_TRACK_MODE_PARAM(template_size, sensor)
        self.VLK_OpenAiState()
        self.VLK_StartAI()
        self.VLK_OpenTrackXY()
        self.VLK_EnableTrackMode(C.byref(param))
        self.VLK_TrackTargetPositionEx(C.byref(param), int(x), int(y), int(video_w), int(video_h))
        self.VLK_StartTrack()
        self._set_status(f"Tracking target {x},{y}")

    def stop_tracking(self) -> None:
        if not self._initialized:
            return
        self.VLK_StopTrack()
        self.VLK_DisableTrackMode()
        self.VLK_CloseTrackXY()
        self.VLK_StopAI()
        self.VLK_CloseAiState()
        self._set_status("Tracking stopped")

    def set_osd(self, osd_mask: int, input_mask: int) -> None:
        if not self.connected:
            return
        param = T.VLK_OSD_PARAM(bytes([osd_mask & 0xFF]), bytes([input_mask & 0xFF]))
        self.VLK_SetOSD(C.byref(param))

    @staticmethod
    def _clamp_short(value: int, limit: int) -> int:
        return max(-limit, min(limit, int(value)))

    def _set_status(self, text: str) -> None:
        self._status_text = text
        for cb in list(self._conn_listeners):
            cb(text)

    def _on_connection_status(self, status: int, msg: Optional[bytes], msg_len: int, user: int) -> int:
        del user
        if status == T.VLK_CONN_STATUS_TCP_CONNECTED:
            self._connected = True
            self._set_status("TCP connected")
            try:
                self.VLK_QueryDevConfiguration()
            except Exception:
                pass
        elif status == T.VLK_CONN_STATUS_TCP_DISCONNECTED:
            self._connected = False
            self._set_status("TCP disconnected")
        else:
            detail = msg[:msg_len].decode("utf-8", errors="ignore") if msg else ""
            self._set_status(f"Connection status {status} {detail}".strip())
        return 0

    def _on_device_status(self, status_type: int, buffer: bytes, buf_len: int, user: int) -> int:
        del user
        if not buffer:
            return 0
        try:
            if status_type == T.VLK_DEV_STATUS_TYPE_MODEL and buf_len >= C.sizeof(T.VLK_DEV_MODEL):
                model = C.cast(buffer, C.POINTER(T.VLK_DEV_MODEL)).contents
                self._model_code = model.cModelCode[0] if isinstance(model.cModelCode, bytes) else int(model.cModelCode)
                self._model_name = T.bytes_to_text(model.szModelName)
            elif status_type == T.VLK_DEV_STATUS_TYPE_CONFIG and buf_len >= C.sizeof(T.VLK_DEV_CONFIG):
                config = C.cast(buffer, C.POINTER(T.VLK_DEV_CONFIG)).contents
                self._firmware = T.bytes_to_text(config.cVersionNO)
                self._device_id = T.bytes_to_text(config.cDeviceID)
                self._serial_no = T.bytes_to_text(config.cSerialNO)
            elif status_type == T.VLK_DEV_STATUS_TYPE_TELEMETRY and buf_len >= C.sizeof(T.VLK_DEV_TELEMETRY):
                src = C.cast(buffer, C.POINTER(T.VLK_DEV_TELEMETRY)).contents
                self._telemetry = T.Telemetry(
                    yaw=src.dYaw,
                    pitch=src.dPitch,
                    roll=src.dRoll,
                    sensor_type=src.emSensorType,
                    tracker_status=src.emTrackerStatus,
                    target_lat=src.dTargetLat,
                    target_lng=src.dTargetLng,
                    target_alt=src.dTargetAlt,
                    drone_lat=src.dDroneLat,
                    drone_lng=src.dDroneLng,
                    drone_alt=src.dDroneAlt,
                    fov_h=src.dFov,
                    fov_v=src.dVertical,
                    eo_digital_zoom=src.iEODigitalZoom,
                    ir_digital_zoom=src.iIRDigitalZoom,
                    zoom_mag=src.dZoomMagTimes,
                    laser_distance=src.sLaserDistance,
                    ir_color=src.emIRColor,
                    record_mode=src.emRecordMode,
                )
                for cb in list(self._telemetry_listeners):
                    cb(self._telemetry)
        except Exception as exc:
            self._set_status(f"Status callback error: {exc}")
        return 0
