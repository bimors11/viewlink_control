# VControl

Desktop control UI for Viewpro gimbals using the bundled ViewLink SDK.
The dashboard uses the layout, colors, typography, and collapsible controls from
the local `zt30sdk` Qt dashboard. All runtime files are inside `viewpro_app`;
the application does not import or require `zt30sdk`.

## Default connection

- Gimbal control: `192.168.144.25:2000`
- Video stream: `rtsp://192.168.144.25:554`
- Joystick: EdgeTX Radiomaster Pocket Joystick at `/dev/input/js0`
- Joystick mapping: pan axis 0, tilt axis 1, zoom axis 2

## Run

```bash
python3 -m viewpro_app
```

## Setup and AppImage

```bash
./setup.sh
./install.sh
```

The AppImage is written to `build/`.

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

Joystick axes are zero-based Linux axes. The gimbal Speed slider also controls
joystick pan/tilt speed. Enable Joystick in its section after connecting. Actual
command support, zoom limits, and AI tracking depend on the attached Viewpro
model and firmware.
