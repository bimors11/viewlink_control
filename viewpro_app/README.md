# Viewpro ViewLink UI

Desktop control UI for Viewpro gimbals using the bundled ViewLink SDK.
The dashboard uses the layout, colors, typography, and collapsible controls from
the local `zt30sdk` Qt dashboard. All runtime files are inside `viewpro_app`;
the application does not import or require `zt30sdk`.

## Default connection

- Gimbal control: `192.168.144.25:2000`
- Video stream: `rtsp://192.168.144.25:554`
- Joystick: `/dev/input/js0`
- Joystick mapping: pan channel 1, tilt channel 2, zoom channel 3

## Run

```bash
python3 -m viewpro_app
```

Requirements:

- `PyQt5`
- FFmpeg executable on PATH (system package `ffmpeg`)

The video decoder uses FFmpeg directly, avoiding OpenCV's Qt plugin conflicts.
The main source selector and Picture in Picture control change the camera output
through ViewLink. PiP is composed by the camera, not by a second SIYI stream.
SIYI-specific media browsing and AI module network settings are not applicable.
Use Connect + Play for control and video, or Open Video for RTSP only.

## Video interactions

- Mouse wheel: zoom in/out
- Click on video: start AI tracking at target point
- Right click on video: stop tracking

Joystick channels are one-based Linux axes (channels 1/2/3 correspond to axes
0/1/2). The gimbal Speed slider also controls joystick pan/tilt speed. Enable
Joystick in its section after connecting. Actual command support, zoom limits,
and AI tracking depend on the attached Viewpro model and firmware.
