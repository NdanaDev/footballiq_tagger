import cv2
import numpy as np
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QMessageBox


class VideoPlayer(QObject):
    frame_changed     = pyqtSignal(np.ndarray)   # current BGR frame
    timestamp_changed = pyqtSignal(float)         # seconds elapsed
    video_paused      = pyqtSignal()
    video_loaded      = pyqtSignal(float, int)    # duration_seconds, total_frames

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cap = None
        self.fps = 25.0
        self.total_frames = 0
        self.current_frame_number = 0
        self._is_paused = True

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._read_next_frame)

    # ── Loading ────────────────────────────────────────────────────────────

    def load_video(self, path: str):
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            QMessageBox.critical(None, "Error", f"Cannot open video:\n{path}")
            self.cap = None
            return False

        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._is_paused = True
        self.current_frame_number = 0

        # Emit the first frame immediately so the UI shows a preview
        self._emit_current_frame()
        duration = self.total_frames / self.fps
        self.video_loaded.emit(duration, self.total_frames)
        return True

    # ── Playback controls ──────────────────────────────────────────────────

    def play(self):
        if self.cap and self._is_paused:
            self._is_paused = False
            interval = max(1, int(1000 / self.fps))
            self.timer.start(interval)

    def pause(self):
        if not self._is_paused:
            self._is_paused = True
            self.timer.stop()
            self.video_paused.emit()

    def toggle_pause(self):
        if self._is_paused:
            self.play()
        else:
            self.pause()

    @pyqtSlot()
    def step_forward(self):
        self.pause()
        if self.cap:
            self.current_frame_number = min(
                self.current_frame_number + 1, self.total_frames - 1
            )
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame_number)
            self._emit_current_frame()

    @pyqtSlot()
    def step_backward(self):
        self.pause()
        if self.cap:
            self.current_frame_number = max(self.current_frame_number - 1, 0)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame_number)
            self._emit_current_frame()

    def seek(self, seconds: float):
        if self.cap:
            frame_num = int(seconds * self.fps)
            frame_num = max(0, min(frame_num, self.total_frames - 1))
            self.current_frame_number = frame_num
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            self._emit_current_frame()

    def seek_relative(self, delta_seconds: float):
        if self.cap:
            current_seconds = self.current_frame_number / self.fps
            self.seek(current_seconds + delta_seconds)

    # ── Internal ───────────────────────────────────────────────────────────

    def _read_next_frame(self):
        if not self.cap:
            return
        ret, frame = self.cap.read()
        if not ret:
            self.pause()
            return
        self.current_frame_number = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        timestamp = self.current_frame_number / self.fps
        self.frame_changed.emit(frame)
        self.timestamp_changed.emit(timestamp)

    def _emit_current_frame(self):
        if not self.cap:
            return
        ret, frame = self.cap.read()
        if ret:
            timestamp = self.current_frame_number / self.fps
            self.frame_changed.emit(frame)
            self.timestamp_changed.emit(timestamp)
            # Seek back so the frame isn't consumed
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame_number)

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def is_paused(self):
        return self._is_paused

    @property
    def current_timestamp(self):
        return self.current_frame_number / self.fps if self.fps else 0.0

    def release(self):
        self.timer.stop()
        if self.cap:
            self.cap.release()
