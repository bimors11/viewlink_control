from __future__ import annotations

import os
import select
import shutil
import subprocess
import time

from PyQt5 import QtCore, QtGui


class VideoWorker(QtCore.QThread):
    frame_ready = QtCore.pyqtSignal(object)
    status_changed = QtCore.pyqtSignal(str)
    dimensions_changed = QtCore.pyqtSignal(int, int)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self) -> None:
        if not shutil.which("ffmpeg"):
            self.status_changed.emit("FFmpeg not found")
            return
        process = None
        self.status_changed.emit("Connecting")
        try:
            # PPM retains the stream aspect ratio and carries each frame's dimensions.
            process = subprocess.Popen([
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-rtsp_transport", "tcp", "-i", self.url, "-an",
                "-vf", "fps=15,scale=960:-2", "-pix_fmt", "rgb24",
                "-vcodec", "ppm", "-f", "image2pipe", "pipe:1",
            ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            buffer = bytearray()
            deadline = time.monotonic() + 10
            live = False
            frame_size = None
            while not self.isInterruptionRequested():
                if time.monotonic() > deadline:
                    raise RuntimeError("RTSP timeout")
                ready, _, _ = select.select([process.stdout], [], [], 0.1)
                if not ready:
                    if process.poll() is not None:
                        raise RuntimeError("RTSP stream ended")
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("RTSP stream ended")
                buffer.extend(chunk)
                while True:
                    if frame_size is None:
                        header = buffer.split(b"\n", 3)
                        if len(header) < 4:
                            break
                        if header[0] != b"P6" or header[2] != b"255":
                            raise RuntimeError("Invalid FFmpeg frame")
                        width, height = map(int, header[1].split())
                        if not (0 < width <= 4096 and 0 < height <= 4096):
                            raise RuntimeError("Invalid video dimensions")
                        del buffer[:sum(len(line) + 1 for line in header[:3])]
                        frame_size = width * height * 3
                    if len(buffer) < frame_size:
                        break
                    image = QtGui.QImage(bytes(buffer[:frame_size]), width, height,
                                         width * 3, QtGui.QImage.Format_RGB888).copy()
                    del buffer[:frame_size]
                    frame_size = None
                    deadline = time.monotonic() + 10
                    if not live:
                        self.status_changed.emit("Live")
                        self.dimensions_changed.emit(width, height)
                        live = True
                    self.frame_ready.emit(image)
        except Exception as exc:
            self.status_changed.emit(str(exc))
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                process.stdout.close()

    def stop(self) -> None:
        self.requestInterruption()
        self.wait()
