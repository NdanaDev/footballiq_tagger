import cv2
import numpy as np
from PyQt5.QtWidgets import QLabel, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QImage, QPixmap


class VideoWidget(QLabel):
    """
    Displays video frames and captures mouse clicks.
    Emits click_coords with frame-space coordinates (not widget-space).
    """
    click_coords = pyqtSignal(float, float)   # frame_x, frame_y

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #1a1a1a;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(640, 360)
        self._frame_width  = 1
        self._frame_height = 1
        self.setText("No video loaded\nFile → Open Video")
        self.setStyleSheet(
            "background-color: #1a1a1a; color: #555555; font-size: 16px;"
        )

    def display_frame(self, frame: np.ndarray):
        """Slot: receive a BGR numpy frame and render it."""
        self._frame_height, self._frame_width = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qt_image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        scaled = pixmap.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(scaled)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.pixmap():
            frame_x, frame_y = self._widget_to_frame(event.x(), event.y())
            if frame_x is not None:
                self.click_coords.emit(frame_x, frame_y)
        super().mousePressEvent(event)

    def _widget_to_frame(self, wx: int, wy: int):
        """Convert widget pixel coords to original frame pixel coords."""
        if not self.pixmap():
            return None, None
        pw = self.pixmap().width()
        ph = self.pixmap().height()
        if pw == 0 or ph == 0:
            return None, None

        # The pixmap is centred inside the label; find its top-left offset
        offset_x = (self.width()  - pw) / 2
        offset_y = (self.height() - ph) / 2

        px = wx - offset_x
        py = wy - offset_y

        if px < 0 or py < 0 or px > pw or py > ph:
            return None, None

        # Scale from displayed pixmap size to original frame size
        scale_x = self._frame_width  / pw
        scale_y = self._frame_height / ph
        return px * scale_x, py * scale_y
