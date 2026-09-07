from __future__ import annotations

import os
import select
import shutil
import subprocess
import threading
import time
from collections import deque

from PyQt5 import QtCore, QtGui


VIDEO_LIVE = "VIDEO LIVE"
VIDEO_CONNECTING = "VIDEO CONNECTING"
VIDEO_RECONNECTING = "VIDEO RECONNECTING"
VIDEO_ERROR = "VIDEO ERROR"
VIDEO_STOPPED = "VIDEO STOPPED"


class VideoWorker(QtCore.QThread):
    frame_ready = QtCore.pyqtSignal(object)
    status_changed = QtCore.pyqtSignal(str)
    dimensions_changed = QtCore.pyqtSignal(int, int)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.retry_delays = [1, 2, 3, 5]
        self._manual_stop = False

    def run(self) -> None:
        if not shutil.which("ffmpeg"):
            self.status_changed.emit(f"{VIDEO_ERROR}: FFmpeg not found")
            return
        attempt = 0
        while not self.isInterruptionRequested():
            status = VIDEO_CONNECTING if attempt == 0 else VIDEO_RECONNECTING
            self.status_changed.emit(status)
            error = self._stream_once()
            if self._manual_stop or self.isInterruptionRequested():
                break
            detail = f": {error}" if error else ""
            self.status_changed.emit(f"{VIDEO_ERROR}{detail}")
            delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
            attempt += 1
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                if self._manual_stop or self.isInterruptionRequested():
                    break
                self.msleep(50)
        self.status_changed.emit(VIDEO_STOPPED)

    def _stream_once(self) -> str:
        process = None
        stderr_lines = deque(maxlen=8)
        stderr_thread = None
        try:
            process = self._start_process()
            if process.stdout is None:
                return "FFmpeg stdout unavailable"
            stderr_thread = self._start_stderr_reader(process, stderr_lines)
            buffer = bytearray()
            deadline = time.monotonic() + 10
            live = False
            frame_size = None
            width = height = 0
            while not self.isInterruptionRequested():
                if time.monotonic() > deadline:
                    return self._error_text("RTSP timeout", stderr_lines)
                ready, _, _ = select.select([process.stdout], [], [], 0.1)
                if not ready:
                    if process.poll() is not None:
                        return self._error_text("RTSP stream ended", stderr_lines)
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    return self._error_text("RTSP stream ended", stderr_lines)
                buffer.extend(chunk)
                while True:
                    if frame_size is None:
                        header = buffer.split(b"\n", 3)
                        if len(header) < 4:
                            break
                        if header[0] != b"P6" or header[2] != b"255":
                            return self._error_text("Invalid FFmpeg frame", stderr_lines)
                        width, height = map(int, header[1].split())
                        if not (0 < width <= 4096 and 0 < height <= 4096):
                            return self._error_text("Invalid video dimensions", stderr_lines)
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
                        self.status_changed.emit(VIDEO_LIVE)
                        self.dimensions_changed.emit(width, height)
                        live = True
                    self.frame_ready.emit(image)
        except Exception as exc:
            return self._error_text(str(exc), stderr_lines)
        finally:
            self._cleanup_process(process)
            if stderr_thread is not None:
                stderr_thread.join(timeout=0.5)
        return ""

    def _start_process(self):
        # PPM retains the stream aspect ratio and carries each frame's dimensions.
        return subprocess.Popen([
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-rtsp_transport", "tcp", "-i", self.url, "-an",
            "-vf", "fps=15,scale=960:-2", "-pix_fmt", "rgb24",
            "-vcodec", "ppm", "-f", "image2pipe", "pipe:1",
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)

    def _start_stderr_reader(self, process, stderr_lines) -> threading.Thread | None:
        if process.stderr is None:
            return None

        def read_stderr() -> None:
            try:
                for raw in iter(process.stderr.readline, b""):
                    text = raw.decode("utf-8", errors="ignore").strip()
                    if text:
                        stderr_lines.append(text)
            except Exception:
                pass

        thread = threading.Thread(target=read_stderr, daemon=True)
        thread.start()
        return thread

    def _cleanup_process(self, process) -> None:
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass

    def _error_text(self, fallback: str, stderr_lines) -> str:
        useful = list(stderr_lines)[-3:]
        return " | ".join(useful) if useful else fallback

    def stop(self) -> None:
        self._manual_stop = True
        self.requestInterruption()
        self.wait()
