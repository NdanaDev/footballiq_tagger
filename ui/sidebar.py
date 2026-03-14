from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QComboBox,
    QPushButton, QGroupBox, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor


EVENT_COLORS = {
    "pass":    "#4CAF50",
    "shot":    "#F44336",
    "tackle":  "#2196F3",
    "dribble": "#FF9800",
    "goal":    "#9C27B0",
    "cross":   "#00BCD4",
    "foul":    "#FF5722",
}


class Sidebar(QWidget):
    player_selected = pyqtSignal(object)   # player_id or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._event_id_map = {}   # list row index → db event id (for undo highlight)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Match info ──────────────────────────────────────────────────
        self.match_label = QLabel("No match loaded")
        self.match_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.match_label.setWordWrap(True)
        layout.addWidget(self.match_label)

        # ── Player selector ─────────────────────────────────────────────
        player_group = QGroupBox("Active Player")
        pg_layout = QVBoxLayout(player_group)
        self.player_combo = QComboBox()
        self.player_combo.addItem("None", None)
        self.player_combo.currentIndexChanged.connect(self._on_player_changed)
        self.player_combo.setFocusPolicy(Qt.NoFocus)
        pg_layout.addWidget(self.player_combo)
        layout.addWidget(player_group)

        # ── Timestamp display ───────────────────────────────────────────
        self.time_label = QLabel("00:00:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet(
            "font-size: 22px; font-family: monospace; font-weight: bold;"
        )
        layout.addWidget(self.time_label)

        # ── Event log ───────────────────────────────────────────────────
        log_group = QGroupBox("Event Log")
        lg_layout = QVBoxLayout(log_group)
        self.event_list = QListWidget()
        self.event_list.setFocusPolicy(Qt.NoFocus)
        self.event_list.setAlternatingRowColors(True)
        lg_layout.addWidget(self.event_list)
        layout.addWidget(log_group, stretch=1)

        # ── Tracking status ─────────────────────────────────────────────
        self.tracking_label = QLabel("Tracking: None")
        self.tracking_label.setAlignment(Qt.AlignCenter)
        self.tracking_label.setStyleSheet(
            "font-size: 11px; color: #888888; "
            "border: 1px solid #444444; border-radius: 3px; padding: 2px 4px;"
        )
        layout.addWidget(self.tracking_label)

        # ── Calibration status ──────────────────────────────────────────
        self.calib_label = QLabel("Pitch: Not calibrated")
        self.calib_label.setAlignment(Qt.AlignCenter)
        self.calib_label.setStyleSheet(
            "font-size: 11px; color: #FF5722; "
            "border: 1px solid #FF5722; border-radius: 3px; padding: 2px 4px;"
        )
        layout.addWidget(self.calib_label)

        # ── Shortcut hint ───────────────────────────────────────────────
        hints = QLabel(
            "P Pass  S Shot  T Tackle\n"
            "D Dribble  G Goal  C Cross  F Foul\n"
            "SPACE Play/Pause  ←/→ Seek 5s\n"
            "Ctrl+C Calibrate  Ctrl+T Track player\n"
            "Ctrl+Shift+T Stop tracking\n"
            "H Heatmap  E Export  Ctrl+Z Undo"
        )
        hints.setStyleSheet("font-size: 10px; color: #888888;")
        hints.setAlignment(Qt.AlignCenter)
        layout.addWidget(hints)

    # ── Public slots ───────────────────────────────────────────────────────

    @pyqtSlot(float)
    def update_timestamp(self, seconds: float):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        self.time_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    @pyqtSlot(dict)
    def add_event(self, event: dict):
        etype  = event.get("event_type", "?").upper()
        ts     = event.get("timestamp", 0.0)
        pid    = event.get("player_id")
        db_id  = event.get("id")
        h = int(ts // 3600)
        m = int((ts % 3600) // 60)
        s = int(ts % 60)
        player_str = f" P{pid}" if pid else ""
        text = f"[{h:02d}:{m:02d}:{s:02d}]{player_str}  {etype}"

        item = QListWidgetItem(text)
        color = EVENT_COLORS.get(event.get("event_type", ""), "#ffffff")
        item.setForeground(QColor(color))
        item.setData(Qt.UserRole, db_id)
        self.event_list.insertItem(0, item)   # newest at top

    @pyqtSlot(int)
    def remove_event(self, db_id: int):
        for i in range(self.event_list.count()):
            item = self.event_list.item(i)
            if item and item.data(Qt.UserRole) == db_id:
                self.event_list.takeItem(i)
                break

    def set_match_info(self, name, home, away):
        self.match_label.setText(f"{name}\n{home} vs {away}")

    def load_players(self, players: list):
        self.player_combo.clear()
        self.player_combo.addItem("None", None)
        for p in players:
            label = f"#{p['number']} {p['name']} ({p['team']})"
            self.player_combo.addItem(label, p["id"])

    def set_tracking_status(self, player_ids: list):
        if not player_ids:
            self.tracking_label.setText("Tracking: None")
            self.tracking_label.setStyleSheet(
                "font-size: 11px; color: #888888; "
                "border: 1px solid #444444; border-radius: 3px; padding: 2px 4px;"
            )
        else:
            ids_str = ", ".join(f"ID {pid}" for pid in player_ids)
            self.tracking_label.setText(f"Tracking: {ids_str}")
            self.tracking_label.setStyleSheet(
                "font-size: 11px; color: #00E5FF; "
                "border: 1px solid #00E5FF; border-radius: 3px; padding: 2px 4px;"
            )

    def set_calibration_status(self, calibrated: bool):
        if calibrated:
            self.calib_label.setText("Pitch: Calibrated")
            self.calib_label.setStyleSheet(
                "font-size: 11px; color: #4CAF50; "
                "border: 1px solid #4CAF50; border-radius: 3px; padding: 2px 4px;"
            )
        else:
            self.calib_label.setText("Pitch: Not calibrated")
            self.calib_label.setStyleSheet(
                "font-size: 11px; color: #FF5722; "
                "border: 1px solid #FF5722; border-radius: 3px; padding: 2px 4px;"
            )

    # ── Internal ───────────────────────────────────────────────────────────

    def _on_player_changed(self, index):
        player_id = self.player_combo.currentData()
        self.player_selected.emit(player_id)
