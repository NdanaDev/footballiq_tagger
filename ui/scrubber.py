from PyQt5.QtWidgets import QWidget, QHBoxLayout, QSlider, QLabel, QPushButton
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot


class VideoScrubber(QWidget):
    """
    Horizontal timeline bar placed below the video widget.

    Signals emitted to the outside world:
      seek_requested(float)   – seconds, emitted on slider release
      play_pause_clicked()    – user pressed the ▶/⏸ button
    """

    seek_requested     = pyqtSignal(float)
    play_pause_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total_frames = 0
        self._fps          = 25.0
        self._dragging     = False

        self.setFixedHeight(44)
        self.setStyleSheet("background-color: #1a1a1a;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        # ── Play / pause button ──────────────────────────────────────────
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(30, 30)
        self._play_btn.setFocusPolicy(Qt.NoFocus)
        self._play_btn.setStyleSheet(
            "QPushButton {"
            "  background:#2e2e2e; color:#e0e0e0; border:none;"
            "  border-radius:4px; font-size:13px; }"
            "QPushButton:hover { background:#3e3e3e; }"
            "QPushButton:pressed { background:#1e1e1e; }"
        )
        self._play_btn.clicked.connect(self.play_pause_clicked)
        layout.addWidget(self._play_btn)

        # ── Timeline slider ──────────────────────────────────────────────
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setValue(0)
        self._slider.setFocusPolicy(Qt.NoFocus)
        self._slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #3a3a3a;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #00BCD4;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                background: #e0e0e0;
                border-radius: 7px;
                margin: -5px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #ffffff;
            }
        """)
        self._slider.sliderPressed.connect(self._on_pressed)
        self._slider.sliderReleased.connect(self._on_released)
        self._slider.sliderMoved.connect(self._on_moved)
        layout.addWidget(self._slider, stretch=1)

        # ── Time label ───────────────────────────────────────────────────
        self._time_label = QLabel("00:00:00 / 00:00:00")
        self._time_label.setStyleSheet(
            "color: #888888; font-size: 11px; font-family: monospace;"
        )
        self._time_label.setFixedWidth(148)
        self._time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._time_label)

    # ── Public slots ────────────────────────────────────────────────────────

    @pyqtSlot(float, int)
    def set_duration(self, duration_seconds: float, total_frames: int):
        """Called once when a video is loaded."""
        self._total_frames = total_frames
        self._fps = total_frames / duration_seconds if duration_seconds > 0 else 25.0
        self._slider.setRange(0, max(0, total_frames - 1))
        self._slider.setValue(0)
        self._update_label(0.0, duration_seconds)

    @pyqtSlot(int)
    def set_position(self, frame_number: int):
        """Called on every frame tick; ignored while the user is dragging."""
        if self._dragging:
            return
        self._slider.blockSignals(True)
        self._slider.setValue(frame_number)
        self._slider.blockSignals(False)
        self._update_label(
            self._to_seconds(frame_number),
            self._to_seconds(self._total_frames),
        )

    @pyqtSlot(bool)
    def set_paused(self, paused: bool):
        self._play_btn.setText("▶" if paused else "⏸")

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_pressed(self):
        self._dragging = True

    def _on_released(self):
        self._dragging = False
        self.seek_requested.emit(self._to_seconds(self._slider.value()))

    def _on_moved(self, frame: int):
        """Update the label in real-time while dragging."""
        self._update_label(
            self._to_seconds(frame),
            self._to_seconds(self._total_frames),
        )

    def _to_seconds(self, frames: int) -> float:
        return frames / self._fps if self._fps else 0.0

    @staticmethod
    def _fmt(seconds: float) -> str:
        s = int(seconds)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def _update_label(self, current: float, total: float):
        self._time_label.setText(f"{self._fmt(current)} / {self._fmt(total)}")
