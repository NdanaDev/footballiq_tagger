import cv2
import numpy as np
from PyQt5.QtWidgets import QLabel, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QFont, QColor


CALIB_LABELS  = ["Top-Left", "Top-Right", "Bottom-Right", "Bottom-Left"]
CALIB_COLORS  = [
    QColor("#FF5722"), QColor("#4CAF50"),
    QColor("#2196F3"), QColor("#FF9800"),
]

TRACKER_COLORS = [
    QColor("#00E5FF"), QColor("#E040FB"), QColor("#69F0AE"),
    QColor("#FFEA00"), QColor("#FF6D00"), QColor("#F06292"),
    QColor("#80D8FF"), QColor("#B9F6CA"), QColor("#FFD180"),
    QColor("#FF9E80"), QColor("#EA80FC"),
]


class VideoWidget(QLabel):
    """
    Displays video frames and captures mouse clicks.
    Emits click_coords with frame-space coordinates (not widget-space).
    In calibration mode emits calibration_point instead.
    In bbox mode emits bbox_drawn after the user drags a rectangle.
    """
    click_coords      = pyqtSignal(float, float)        # frame_x, frame_y
    calibration_point = pyqtSignal(int, float, float)   # index, frame_x, frame_y
    bbox_drawn        = pyqtSignal(int, int, int, int)  # x, y, w, h  (frame coords)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(640, 360)

        self._frame_width      = 1
        self._frame_height     = 1

        # Calibration state
        self._calibration_mode = False
        self._calib_widget_pts = []   # (wx, wy) for overlay drawing

        # Bbox draw state
        self._bbox_mode    = False
        self._bbox_start   = None   # (wx, wy) widget coords
        self._bbox_current = None   # (wx, wy) widget coords

        # Tracking overlay
        self._tracking_boxes  = {}   # {player_id: (x, y, w, h)} frame coords
        self._tracking_labels = {}   # {player_id: str}

        # YOLO detection overlay
        self._detection_players = []  # [(x, y, w, h, conf), ...]
        self._detection_ball    = None  # (x, y, w, h, conf) or None

        self.setText("No video loaded\nFile → Open Video")
        self.setStyleSheet(
            "background-color: #1a1a1a; color: #555555; font-size: 16px;"
        )

    # ── Frame display ──────────────────────────────────────────────────────

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

    # ── Calibration mode ───────────────────────────────────────────────────

    def set_calibration_mode(self, active: bool):
        self._calibration_mode = active
        self._calib_widget_pts = []
        self.update()

    # ── Bbox draw mode ─────────────────────────────────────────────────────

    def set_bbox_mode(self, active: bool):
        self._bbox_mode    = active
        self._bbox_start   = None
        self._bbox_current = None
        self.setCursor(Qt.CrossCursor if active else Qt.ArrowCursor)
        self.update()

    def update_tracking_boxes(self, boxes: dict, labels: dict = None):
        """boxes: {player_id: (x, y, w, h)} in frame coords."""
        self._tracking_boxes  = boxes
        self._tracking_labels = labels or {}
        self.update()

    def update_detections(self, players: list, ball):
        """Show YOLO detection overlay. Pass empty list / None to clear."""
        self._detection_players = players or []
        self._detection_ball    = ball
        self.update()

    def clear_detections(self):
        self._detection_players = []
        self._detection_ball    = None
        self.update()

    # ── Mouse events ───────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._calibration_mode:
                frame_x, frame_y = self._widget_to_frame(event.x(), event.y())
                if frame_x is not None:
                    idx = len(self._calib_widget_pts)
                    self._calib_widget_pts.append((event.x(), event.y()))
                    self.calibration_point.emit(idx, frame_x, frame_y)
                    self.update()
                return

            if self._bbox_mode:
                self._bbox_start   = (event.x(), event.y())
                self._bbox_current = (event.x(), event.y())
                self.update()
                return

            if self.pixmap():
                frame_x, frame_y = self._widget_to_frame(event.x(), event.y())
                if frame_x is not None:
                    self.click_coords.emit(frame_x, frame_y)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._bbox_mode and self._bbox_start:
            self._bbox_current = (event.x(), event.y())
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._bbox_mode and self._bbox_start:
            x0, y0 = self._bbox_start
            x1, y1 = event.x(), event.y()
            fx0, fy0 = self._widget_to_frame(x0, y0)
            fx1, fy1 = self._widget_to_frame(x1, y1)
            if None not in (fx0, fy0, fx1, fy1):
                x = int(min(fx0, fx1))
                y = int(min(fy0, fy1))
                w = int(abs(fx1 - fx0))
                h = int(abs(fy1 - fy0))
                if w > 5 and h > 5:
                    self.bbox_drawn.emit(x, y, w, h)
            self.set_bbox_mode(False)
        super().mouseReleaseEvent(event)

    # ── Paint ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._calibration_mode:
            self._draw_calibration_overlay(painter)
        self._draw_tracking_overlay(painter)
        self._draw_detection_overlay(painter)
        painter.end()

    def _draw_calibration_overlay(self, painter):
        next_idx = len(self._calib_widget_pts)
        if next_idx < 4:
            painter.fillRect(0, 0, self.width(), 44, QColor(0, 0, 0, 180))
            painter.setPen(QColor("#FFD700"))
            font = QFont()
            font.setPixelSize(14)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                0, 0, self.width(), 44, Qt.AlignCenter,
                f"CALIBRATION  •  Click {CALIB_LABELS[next_idx]} corner  "
                f"({next_idx + 1}/4)  —  Press Esc to cancel",
            )

        label_font = QFont()
        label_font.setPixelSize(12)
        label_font.setBold(True)
        for i, (wx, wy) in enumerate(self._calib_widget_pts):
            color = CALIB_COLORS[i]
            painter.setPen(QPen(color, 2))
            painter.setBrush(color)
            painter.drawEllipse(wx - 7, wy - 7, 14, 14)
            painter.setFont(label_font)
            painter.setPen(QColor("white"))
            painter.drawText(wx + 12, wy + 5, f"{i + 1}: {CALIB_LABELS[i]}")

    def _draw_tracking_overlay(self, painter):
        label_font = QFont()
        label_font.setPixelSize(12)
        label_font.setBold(True)
        painter.setFont(label_font)

        # Draw bbox instruction banner
        if self._bbox_mode:
            painter.fillRect(0, 0, self.width(), 44, QColor(0, 0, 0, 180))
            painter.setPen(QColor("#00E5FF"))
            font = QFont()
            font.setPixelSize(14)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                0, 0, self.width(), 44, Qt.AlignCenter,
                "TRACKING  •  Click and drag a box around the player  —  Esc to cancel",
            )
            painter.setFont(label_font)

        # Draw live bbox during drag
        if self._bbox_mode and self._bbox_start and self._bbox_current:
            x0, y0 = self._bbox_start
            x1, y1 = self._bbox_current
            pen = QPen(QColor("#FFD700"), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))

        # Draw confirmed tracking boxes
        for player_id, (fx, fy, fw, fh) in self._tracking_boxes.items():
            color = TRACKER_COLORS[player_id % len(TRACKER_COLORS)]
            wx, wy = self._frame_to_widget(fx, fy)
            if wx is None:
                continue
            pw = self.pixmap().width()
            ph = self.pixmap().height()
            ww = fw * pw / self._frame_width
            wh = fh * ph / self._frame_height
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(wx), int(wy), int(ww), int(wh))
            label = self._tracking_labels.get(player_id, f"P{player_id}")
            painter.setPen(color)
            painter.drawText(int(wx) + 2, int(wy) - 5, label)

    def _draw_detection_overlay(self, painter):
        if not self._detection_players and self._detection_ball is None:
            return

        label_font = QFont()
        label_font.setPixelSize(11)
        painter.setFont(label_font)

        # Player boxes — green dashed
        player_color = QColor("#69F0AE")
        pen = QPen(player_color, 2, Qt.DashLine)
        for x, y, w, h, conf in self._detection_players:
            wx, wy = self._frame_to_widget(x, y)
            if wx is None:
                continue
            pw = self.pixmap().width()
            ph = self.pixmap().height()
            ww = w * pw / self._frame_width
            wh = h * ph / self._frame_height
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(wx), int(wy), int(ww), int(wh))
            painter.setPen(player_color)
            painter.drawText(int(wx) + 2, int(wy) - 4, f"{conf:.0%}")

        # Ball — yellow filled circle
        if self._detection_ball is not None:
            bx, by, bw, bh, conf = self._detection_ball
            cx, cy = bx + bw / 2, by + bh / 2
            wx, wy = self._frame_to_widget(cx, cy)
            if wx is not None:
                ball_color = QColor("#FFD700")
                painter.setPen(QPen(ball_color, 2))
                painter.setBrush(ball_color)
                painter.drawEllipse(int(wx) - 8, int(wy) - 8, 16, 16)
                painter.setPen(QColor("black"))
                painter.setFont(label_font)
                painter.drawText(int(wx) + 12, int(wy) + 4, f"ball {conf:.0%}")

    # ── Coordinate helpers ─────────────────────────────────────────────────

    def _widget_to_frame(self, wx: int, wy: int):
        """Convert widget pixel coords to original frame pixel coords."""
        if not self.pixmap():
            return None, None
        pw = self.pixmap().width()
        ph = self.pixmap().height()
        if pw == 0 or ph == 0:
            return None, None
        offset_x = (self.width()  - pw) / 2
        offset_y = (self.height() - ph) / 2
        px = wx - offset_x
        py = wy - offset_y
        if px < 0 or py < 0 or px > pw or py > ph:
            return None, None
        return px * self._frame_width / pw, py * self._frame_height / ph

    def _frame_to_widget(self, fx, fy):
        """Convert frame pixel coords to widget pixel coords."""
        if not self.pixmap():
            return None, None
        pw = self.pixmap().width()
        ph = self.pixmap().height()
        if pw == 0 or ph == 0:
            return None, None
        offset_x = (self.width()  - pw) / 2
        offset_y = (self.height() - ph) / 2
        return fx * pw / self._frame_width + offset_x, fy * ph / self._frame_height + offset_y
