from __future__ import annotations

import ctypes as C
from dataclasses import dataclass


VLK_ERROR_NO_ERROR = 0

VLK_CONN_TYPE_SERIAL_PORT = 0x00
VLK_CONN_TYPE_TCP = 0x01
VLK_CONN_TYPE_UDP = 0x02

VLK_CONN_STATUS_TCP_CONNECTED = 0x02
VLK_CONN_STATUS_TCP_DISCONNECTED = 0x03
VLK_CONN_STATUS_SERIAL_PORT_CONNECTED = 0x04
VLK_CONN_STATUS_SERIAL_PORT_DISCONNECTED = 0x05

VLK_TRACK_TEMPLATE_SIZE_AUTO = 0
VLK_TRACK_TEMPLATE_SIZE_32 = 32
VLK_TRACK_TEMPLATE_SIZE_64 = 64
VLK_TRACK_TEMPLATE_SIZE_128 = 128

VLK_SENSOR_VISIBLE1 = 0
VLK_SENSOR_IR = 1
VLK_SENSOR_VISIBLE_IR = 2
VLK_SENSOR_IR_VISIBLE = 3
VLK_SENSOR_VISIBLE2 = 4

VLK_IMAGE_TYPE_VISIBLE1 = 0
VLK_IMAGE_TYPE_VISIBLE2 = 1
VLK_IMAGE_TYPE_IR1 = 2
VLK_IMAGE_TYPE_IR2 = 3
VLK_IMAGE_TYPE_FUSION = 4

VLK_IR_COLOR_WHITEHOT = 0
VLK_IR_COLOR_BLACKHOT = 1
VLK_IR_COLOR_PSEUDOHOT = 2
VLK_IR_COLOR_RUSTY = 3

VLK_RECORD_MODE_NONE = 0
VLK_RECORD_MODE_PHOTO = 1
VLK_RECORD_MODE_RECORD = 2

VLK_FOCUS_MODE_AUTO = 0
VLK_FOCUS_MODE_MANU = 1

VLK_LASER_ZOOM_MODE_FOLLOW_EO = 0
VLK_LASER_ZOOM_MODE_MANU = 1

VLK_TRACKER_STATUS_STOPPED = 0
VLK_TRACKER_STATUS_SEARCHING = 1
VLK_TRACKER_STATUS_TRACKING = 2
VLK_TRACKER_STATUS_LOST = 3

VLK_DEV_STATUS_TYPE_MODEL = 0
VLK_DEV_STATUS_TYPE_CONFIG = 1
VLK_DEV_STATUS_TYPE_TELEMETRY = 2
VLK_DEV_STATUS_TYPE_AISTATE = 3
VLK_DEV_STATUS_TYPE_TRACKXY = 5

VLK_OSD_MASK_ENABLE_OSD = 0x1
VLK_OSD_MASK_CROSS = 0x2
VLK_OSD_MASK_PITCH_YAW = 0x4
VLK_OSD_MASK_XYSHIFT = 0x8
VLK_OSD_MASK_GPS = 0x10
VLK_OSD_MASK_TIME = 0x20
VLK_OSD_MASK_VL_MAG = 0x40
VLK_OSD_MASK_BIG_FONT = 0x80

VLK_OSD_INPUT_MASK_PERMANENT_SAVE = 0x1
VLK_OSD_INPUT_MASK_TIME = 0x2
VLK_OSD_INPUT_MASK_GPS = 0x4
VLK_OSD_INPUT_MASK_MGRS = 0x8
VLK_OSD_INPUT_MASK_PITCH_YAW = 0x10
VLK_OSD_INPUT_MASK_VL_MAG = 0x20
VLK_OSD_INPUT_MASK_ZOOM_TIMES_OR_FOV = 0x40
VLK_OSD_INPUT_MASK_CHAR_BLACK_BORDER = 0x80

VLK_MAX_YAW_SPEED = 2000
VLK_MAX_PITCH_SPEED = 2000
VLK_MIN_ZOOM_SPEED = 1
VLK_MAX_ZOOM_SPEED = 8


class VLK_DEV_IPADDR(C.Structure):
    _fields_ = [("szIPV4", C.c_char * 16), ("iPort", C.c_int)]


class VLK_DEV_SERIAL_PORT(C.Structure):
    _fields_ = [("szSerialPortName", C.c_char * 16), ("iBaudRate", C.c_int)]


class VLK_CONN_PARAM_UNION(C.Union):
    _fields_ = [("IPAddr", VLK_DEV_IPADDR), ("SerialPort", VLK_DEV_SERIAL_PORT)]


class VLK_CONN_PARAM(C.Structure):
    _fields_ = [("emType", C.c_int), ("ConnParam", VLK_CONN_PARAM_UNION)]


class VLK_TRACK_MODE_PARAM(C.Structure):
    _fields_ = [("emTrackTempSize", C.c_int), ("emTrackSensor", C.c_int)]


class VLK_CHANNELS_MAP(C.Structure):
    _fields_ = [
        ("cYW", C.c_char),
        ("cPT", C.c_char),
        ("cMO", C.c_char),
        ("cZM", C.c_char),
        ("cFC", C.c_char),
        ("cRP", C.c_char),
        ("cMU", C.c_char),
    ]


class VLK_DEV_CONFIG(C.Structure):
    _fields_ = [
        ("cTimeZone", C.c_char),
        ("cOSDCfg", C.c_char),
        ("cMagneticVariation", C.c_char),
        ("cOSDInput", C.c_char),
        ("cBaudRate", C.c_char),
        ("cEODigitalZoom", C.c_char),
        ("sTemperatureAlarmLine", C.c_short),
        ("cTrack", C.c_char),
        ("cLaser", C.c_char),
        ("cRecordDefinition", C.c_char),
        ("cOSDGPS", C.c_char),
        ("cSBUSChnlMap", C.c_char),
        ("ChnlsMap", VLK_CHANNELS_MAP),
        ("cFocusHoldSet", C.c_char),
        ("cCameraType", C.c_char),
        ("cReserved1", C.c_char * 5),
        ("cRestoreIP", C.c_char),
        ("cReserved2", C.c_char * 5),
        ("cReserved3", C.c_char * 43),
        ("cVersionNO", C.c_char * 20),
        ("cDeviceID", C.c_char * 10),
        ("cSerialNO", C.c_char * 22),
    ]


class VLK_DEV_MODEL(C.Structure):
    _fields_ = [("cModelCode", C.c_char), ("szModelName", C.c_char * 32)]


class VLK_DEV_TRACKXY(C.Structure):
    _fields_ = [("iTrackX", C.c_char), ("iTrackY", C.c_char)]


class VLK_DEV_TELEMETRY(C.Structure):
    _fields_ = [
        ("dYaw", C.c_double),
        ("dPitch", C.c_double),
        ("dRoll", C.c_double),
        ("emSensorType", C.c_int),
        ("emTrackerStatus", C.c_int),
        ("dTargetLat", C.c_double),
        ("dTargetLng", C.c_double),
        ("dTargetAlt", C.c_double),
        ("dDroneLat", C.c_double),
        ("dDroneLng", C.c_double),
        ("dDroneAlt", C.c_double),
        ("dFov", C.c_double),
        ("dVertical", C.c_double),
        ("iEODigitalZoom", C.c_int),
        ("iIRDigitalZoom", C.c_int),
        ("dZoomMagTimes", C.c_double),
        ("sLaserDistance", C.c_short),
        ("emIRColor", C.c_int),
        ("emRecordMode", C.c_int),
    ]


class VLK_OSD_PARAM(C.Structure):
    _fields_ = [("cOSD", C.c_char), ("cOSDInput", C.c_char)]


ConnStatusCB = C.CFUNCTYPE(C.c_int, C.c_int, C.c_char_p, C.c_int, C.c_void_p)
DevStatusCB = C.CFUNCTYPE(C.c_int, C.c_int, C.c_void_p, C.c_int, C.c_void_p)


@dataclass
class Telemetry:
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    sensor_type: int = VLK_SENSOR_VISIBLE1
    tracker_status: int = VLK_TRACKER_STATUS_STOPPED
    target_lat: float = 0.0
    target_lng: float = 0.0
    target_alt: float = 0.0
    drone_lat: float = 0.0
    drone_lng: float = 0.0
    drone_alt: float = 0.0
    fov_h: float = 0.0
    fov_v: float = 0.0
    eo_digital_zoom: int = 0
    ir_digital_zoom: int = 0
    zoom_mag: float = 0.0
    laser_distance: int = 0
    ir_color: int = VLK_IR_COLOR_WHITEHOT
    record_mode: int = VLK_RECORD_MODE_NONE


def bytes_to_text(value: bytes) -> str:
    return value.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
