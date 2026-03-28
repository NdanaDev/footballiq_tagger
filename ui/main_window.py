import os
import numpy as np
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFileDialog,
    QMenuBar, QAction, QInputDialog, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QLabel,
    QListWidget, QListWidgetItem, QComboBox, QPushButton
)
from PyQt5.QtCore import Qt, pyqtSlot

from core.video_player   import VideoPlayer
from core.pitch_mapper   import PitchMapper
from core.event_tagger   import EventTagger
from core.player_tracker import PlayerTracker
from core.auto_tagger    import AutoTagger
from data.database       import Database
from ui.video_widget     import VideoWidget
from ui.sidebar          import Sidebar
from ui.scrubber         import VideoScrubber


KEY_EVENT_MAP = {
    Qt.Key_P: "pass",
    Qt.Key_S: "shot",
    Qt.Key_T: "tackle",
    Qt.Key_D: "dribble",
    Qt.Key_G: "goal",
    Qt.Key_C: "cross",
    Qt.Key_F: "foul",
}


class MainWindow(QMainWindow):
    """
    Top-level application window.

    Owns all core objects (VideoPlayer, EventTagger, Database, etc.) and wires
    their signals together.  The layout is a horizontal split: video+scrubber on
    the left, Sidebar on the right.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FootballIQ Tagger")
        self.setMinimumSize(1100, 650)
        self.setStyleSheet("background-color: #121212; color: #e0e0e0;")

        # ── Core objects ─────────────────────────────────────────────────
        self.database     = Database()
        self.pitch_mapper = PitchMapper()
        self.video_player = VideoPlayer()
        self.event_tagger = EventTagger(self.pitch_mapper, self.database)

        self._current_match_id    = None
        self._video_path          = None
        self._calib_points        = []   # accumulates (frame_x, frame_y) during calibration
        self.player_tracker       = PlayerTracker()
        self.auto_tagger          = AutoTagger()
        self._last_frame          = None
        self._tracking_labels     = {}
        self._tracking_frame_count = 0

        # ── UI ───────────────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Left column: video + scrubber stacked vertically
        video_panel = QWidget()
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)

        self.video_widget = VideoWidget()
        self.scrubber     = VideoScrubber()
        video_layout.addWidget(self.video_widget, stretch=1)
        video_layout.addWidget(self.scrubber)

        self.sidebar = Sidebar()
        root_layout.addWidget(video_panel, stretch=1)
        root_layout.addWidget(self.sidebar)

        self._build_menu()
        self._connect_signals()
        self.setFocus()

    # ── Menu ──────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self.menuBar()
        mb.setStyleSheet("background-color: #1e1e1e; color: #e0e0e0;")

        file_menu = mb.addMenu("File")

        act_new = QAction("New Match", self)
        act_new.setShortcut("Ctrl+N")
        act_new.triggered.connect(self._new_match_dialog)
        file_menu.addAction(act_new)

        act_load = QAction("Load Match...", self)
        act_load.setShortcut("Ctrl+L")
        act_load.triggered.connect(self._load_match_dialog)
        file_menu.addAction(act_load)

        act_open = QAction("Open Video...", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._open_video_dialog)
        file_menu.addAction(act_open)

        file_menu.addSeparator()

        act_export = QAction("Export CSV (E)", self)
        act_export.triggered.connect(self._export_csv)
        file_menu.addAction(act_export)

        act_export_json = QAction("Export JSON (Ctrl+J)", self)
        act_export_json.setShortcut("Ctrl+J")
        act_export_json.triggered.connect(self._export_json)
        file_menu.addAction(act_export_json)

        file_menu.addSeparator()

        analytics_menu = mb.addMenu("Analytics")

        act_heatmap = QAction("Position Heatmap (H)", self)
        act_heatmap.triggered.connect(self._show_heatmap)
        analytics_menu.addAction(act_heatmap)

        act_passmap = QAction("Pass Map (M)", self)
        act_passmap.triggered.connect(self._show_pass_map)
        analytics_menu.addAction(act_passmap)

        act_shotmap = QAction("Shot Map (N)", self)
        act_shotmap.triggered.connect(self._show_shot_map)
        analytics_menu.addAction(act_shotmap)

        act_stats = QAction("Player Stats (R)", self)
        act_stats.triggered.connect(self._show_stats)
        analytics_menu.addAction(act_stats)

        analytics_menu.addSeparator()

        act_ai = QAction("AI Detect Players/Ball (Ctrl+A)", self)
        act_ai.setShortcut("Ctrl+A")
        act_ai.triggered.connect(self._run_auto_detect)
        analytics_menu.addAction(act_ai)

        file_menu.addSeparator()

        act_quit = QAction("Quit", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        player_menu = mb.addMenu("Players")
        act_add_player = QAction("Add Player...", self)
        act_add_player.triggered.connect(self._add_player_dialog)
        player_menu.addAction(act_add_player)

    # ── Signal wiring ──────────────────────────────────────────────────────

    def _connect_signals(self):
        # VideoPlayer → VideoWidget + Sidebar + EventTagger
        self.video_player.frame_changed.connect(self.video_widget.display_frame)
        self.video_player.timestamp_changed.connect(self.sidebar.update_timestamp)
        self.video_player.timestamp_changed.connect(self.event_tagger.update_timestamp)
        self.video_player.frame_number_changed.connect(self.event_tagger.update_frame_number)

        # VideoPlayer → Scrubber
        self.video_player.video_loaded.connect(self.scrubber.set_duration)
        self.video_player.frame_number_changed.connect(self.scrubber.set_position)
        self.video_player.video_playing.connect(lambda: self.scrubber.set_paused(False))
        self.video_player.video_paused.connect(lambda: self.scrubber.set_paused(True))

        # Scrubber → VideoPlayer
        self.scrubber.seek_requested.connect(self.video_player.seek)
        self.scrubber.play_pause_clicked.connect(self.video_player.toggle_pause)

        # VideoWidget → EventTagger / calibration / tracking
        self.video_widget.click_coords.connect(self.event_tagger.set_click_coords)
        self.video_widget.calibration_point.connect(self._on_calibration_point)
        self.video_widget.bbox_drawn.connect(self._on_bbox_drawn)

        # VideoPlayer → frame cache + tracker update
        self.video_player.frame_changed.connect(self._on_frame_changed)

        # EventTagger → Sidebar (new event / undo / destination)
        self.event_tagger.event_tagged.connect(self.sidebar.add_event)
        self.event_tagger.event_tagged.connect(lambda _: self.video_widget.clear_detections())
        self.event_tagger.event_untagged.connect(self.sidebar.remove_event)
        self.event_tagger.destination_awaiting.connect(self._on_destination_awaiting)
        self.event_tagger.destination_set.connect(self._on_destination_set)

        # Sidebar → EventTagger (player selection)
        self.sidebar.player_selected.connect(self.event_tagger.set_active_player)

    # ── Keyboard handling ─────────────────────────────────────────────────

    def keyPressEvent(self, event):
        key  = event.key()
        mods = event.modifiers()

        # Ctrl+Z — undo
        if key == Qt.Key_Z and mods & Qt.ControlModifier:
            self.event_tagger.undo_last()
            return

        # Ctrl+C — start pitch calibration
        if key == Qt.Key_C and mods & Qt.ControlModifier:
            self._start_calibration()
            return

        # Ctrl+Shift+T — stop all tracking
        if key == Qt.Key_T and mods == (Qt.ControlModifier | Qt.ShiftModifier):
            self.player_tracker.clear()
            self.video_widget.update_tracking_boxes({})
            self.sidebar.set_tracking_status([])
            self.statusBar().showMessage("Tracking stopped.")
            return

        # Ctrl+T — track active player (draw bounding box)
        if key == Qt.Key_T and mods == Qt.ControlModifier:
            self._start_bbox_draw()
            return

        # Esc — cancel calibration, bbox draw, or destination tagging
        if key == Qt.Key_Escape:
            if self.video_widget.calibration_mode:
                self.video_widget.set_calibration_mode(False)
                self._calib_points = []
                self.statusBar().showMessage("Calibration cancelled.")
                return
            if self.video_widget.bbox_mode:
                self.video_widget.set_bbox_mode(False)
                self.statusBar().showMessage("Tracking cancelled.")
                return
            if self.event_tagger.awaiting_destination:
                self.event_tagger.cancel_destination()
                self.statusBar().showMessage("Destination tagging cancelled.")
                return

        # SPACE — play / pause
        if key == Qt.Key_Space:
            self.video_player.toggle_pause()
            return

        # Arrow keys — seek ±5 seconds or step frame
        if key == Qt.Key_Left:
            if mods & Qt.ShiftModifier:
                self.video_player.step_backward()
            else:
                self.video_player.seek_relative(-5.0)
            return
        if key == Qt.Key_Right:
            if mods & Qt.ShiftModifier:
                self.video_player.step_forward()
            else:
                self.video_player.seek_relative(5.0)
            return

        # Number keys 1–9 — select player by number
        if Qt.Key_1 <= key <= Qt.Key_9:
            num = key - Qt.Key_0
            self._select_player_by_number(num)
            return

        # Ctrl+A — AI detect
        if key == Qt.Key_A and mods & Qt.ControlModifier:
            self._run_auto_detect()
            return

        # H — heatmap
        if key == Qt.Key_H and not mods:
            self._show_heatmap()
            return

        # M — pass map
        if key == Qt.Key_M and not mods:
            self._show_pass_map()
            return

        # N — shot map
        if key == Qt.Key_N and not mods:
            self._show_shot_map()
            return

        # R — player stats
        if key == Qt.Key_R and not mods:
            self._show_stats()
            return

        # E — export CSV
        if key == Qt.Key_E and not mods:
            self._export_csv()
            return

        # Q — quit
        if key == Qt.Key_Q and not mods:
            self.close()
            return

        # Event tagging keys (P, S, T, D, G, C, F) — only without modifiers
        if key in KEY_EVENT_MAP and not mods:
            if self._current_match_id is None:
                QMessageBox.warning(self, "No Match", "Create a match first (File → New Match).")
                return
            if self.pitch_mapper.is_calibrated and not self.event_tagger.has_click_location:
                self.statusBar().showMessage(
                    "⚠  No pitch location — click on the video first, then press the key.", 4000
                )
                return
            event_type = KEY_EVENT_MAP[key]
            outcome = None
            if event_type in ("pass", "shot", "cross"):
                outcome = self._ask_outcome(event_type)
            self.event_tagger.tag_event(event_type, outcome)
            return

        super().keyPressEvent(event)

    # ── Dialogs & actions ─────────────────────────────────────────────────

    def _load_match_dialog(self):
        matches = self.database.get_matches()
        if not matches:
            QMessageBox.information(self, "No Matches", "No saved matches found. Create one first.")
            return
        dlg = LoadMatchDialog(matches, self)
        if dlg.exec_() == QDialog.Accepted:
            match = dlg.selected_match()
            if match:
                self._current_match_id = match["id"]
                self.event_tagger.set_active_match(match["id"])
                self.sidebar.set_match_info(match["name"], match["home_team"], match["away_team"])
                players = self.database.get_players(match["id"])
                self.sidebar.load_players(players)
                self.sidebar.clear_events()
                events = self.database.get_all_events(match["id"])
                for e in events:
                    self.sidebar.add_event(e)
                self.statusBar().showMessage(f"Loaded: {match['name']}")
        self.setFocus()

    def _new_match_dialog(self):
        dlg = NewMatchDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            name, home, away = dlg.values()
            match_id = self.database.create_match(name, home, away)
            self._current_match_id = match_id
            self.event_tagger.set_active_match(match_id)
            self.sidebar.set_match_info(name, home, away)
            self.sidebar.load_players([])
            self.setFocus()

    def _open_video_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv);;All Files (*)"
        )
        if path:
            self._video_path = path
            self.video_player.load_video(path)
            self.setWindowTitle(f"FootballIQ Tagger — {os.path.basename(path)}")
            self._restore_calibration(path)
        self.setFocus()

    def _restore_calibration(self, video_path: str):
        """Re-apply saved calibration points for this video file, if any exist."""
        points = self.database.get_calibration(video_path)
        if points:
            self.pitch_mapper.calibrate(points)
            self.sidebar.set_calibration_status(True)
            self.statusBar().showMessage(
                "Calibration restored from previous session.", 4000
            )

    def _add_player_dialog(self):
        if self._current_match_id is None:
            QMessageBox.warning(self, "No Match", "Create a match first (File → New Match).")
            return
        dlg = AddPlayerDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            name, number, team = dlg.values()
            self.database.add_player(self._current_match_id, name, number, team)
            players = self.database.get_players(self._current_match_id)
            self.sidebar.load_players(players)
        self.setFocus()

    def _select_player_by_number(self, number: int):
        if self._current_match_id is None:
            return
        players = self.database.get_players(self._current_match_id)
        for p in players:
            if p["number"] == number:
                self.event_tagger.set_active_player(p["id"])
                # Also update the combo box
                combo = self.sidebar.player_combo
                for i in range(combo.count()):
                    if combo.itemData(i) == p["id"]:
                        combo.setCurrentIndex(i)
                        break
                return

    def _export_csv(self):
        if self._current_match_id is None:
            QMessageBox.warning(self, "No Match", "No active match to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "events.csv", "CSV Files (*.csv)"
        )
        if path:
            try:
                import pandas as pd
                events = self.database.get_all_events(self._current_match_id)
                if not events:
                    QMessageBox.information(self, "Export", "No events to export.")
                    return
                df = pd.DataFrame(events)
                df.to_csv(path, index=False)
                QMessageBox.information(self, "Export", f"Exported {len(df)} events to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))
        self.setFocus()

    def _export_json(self):
        if self._current_match_id is None:
            QMessageBox.warning(self, "No Match", "No active match to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export JSON", "events.json", "JSON Files (*.json)"
        )
        if path:
            try:
                import json
                events = self.database.get_all_events(self._current_match_id)
                if not events:
                    QMessageBox.information(self, "Export", "No events to export.")
                    return
                with open(path, "w") as f:
                    json.dump(events, f, indent=2, default=str)
                QMessageBox.information(self, "Export", f"Exported {len(events)} events to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))
        self.setFocus()

    def _show_pass_map(self):
        if self._current_match_id is None:
            QMessageBox.warning(self, "No Match", "No active match.")
            return
        try:
            from data.heatmap import HeatmapGenerator
            player_id = self.event_tagger.active_player_id
            gen = HeatmapGenerator(self.database)
            gen.show_pass_map(self._current_match_id, player_id)
        except Exception as e:
            QMessageBox.critical(self, "Pass Map Error", str(e))
        self.setFocus()

    def _ask_outcome(self, event_type: str):
        """Prompt for an outcome label (e.g. 'complete'/'incomplete') for events that support it."""
        outcomes = {
            "pass":  ["complete", "incomplete"],
            "shot":  ["on target", "off target", "blocked"],
            "cross": ["complete", "incomplete"],
        }
        choices = outcomes.get(event_type, [])
        if not choices:
            return None
        item, ok = QInputDialog.getItem(
            self, f"{event_type.title()} Outcome", "Outcome:", choices, 0, False
        )
        return item if ok else None

    def _show_shot_map(self):
        if self._current_match_id is None:
            QMessageBox.warning(self, "No Match", "No active match.")
            return
        try:
            from data.heatmap import HeatmapGenerator
            player_id = self.event_tagger.active_player_id
            gen = HeatmapGenerator(self.database)
            gen.show_shot_map(self._current_match_id, player_id)
        except Exception as e:
            QMessageBox.critical(self, "Shot Map Error", str(e))
        self.setFocus()

    def _show_stats(self):
        if self._current_match_id is None:
            QMessageBox.warning(self, "No Match", "No active match.")
            return
        try:
            from ui.stats_dialog import StatsDialog
            players = self.database.get_players(self._current_match_id)
            dlg = StatsDialog(
                self.database,
                self._current_match_id,
                players,
                initial_player_id=self.event_tagger.active_player_id,
                parent=self,
            )
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Stats Error", str(e))
        self.setFocus()

    def _show_heatmap(self):
        if self._current_match_id is None:
            QMessageBox.warning(self, "No Match", "No active match.")
            return
        try:
            from data.heatmap import HeatmapGenerator
            player_id = self.event_tagger.active_player_id
            gen = HeatmapGenerator(self.database)
            gen.show_heatmap(self._current_match_id, player_id)
        except Exception as e:
            QMessageBox.critical(self, "Heatmap Error", str(e))
        self.setFocus()

    @pyqtSlot(np.ndarray)
    def _on_frame_changed(self, frame):
        self._last_frame = frame
        if not self.player_tracker.is_empty:
            try:
                boxes = self.player_tracker.update(frame)
            except Exception as e:
                self.statusBar().showMessage(f"Tracking error: {e}", 3000)
                return
            self.video_widget.update_tracking_boxes(boxes, self._tracking_labels)
            self._tracking_frame_count += 1
            if self._tracking_frame_count % 5 == 0:
                self._save_tracking_positions(boxes)

    def _save_tracking_positions(self, boxes: dict):
        """
        Persist the current bounding-box centres to the tracking table.
        Called every 5 frames to reduce write frequency without losing resolution.
        Silently skips players whose pitch transform fails (e.g. not calibrated).
        """
        if self._current_match_id is None:
            return
        for player_id, (x, y, w, h) in boxes.items():
            try:
                pitch_x, pitch_y = self.pitch_mapper.transform_bbox_center(x, y, w, h)
                self.database.save_tracking_point(
                    player_id=player_id,
                    pitch_x=pitch_x,
                    pitch_y=pitch_y,
                    match_id=self._current_match_id,
                    frame_number=self.video_player.current_frame_number,
                    timestamp=self.video_player.current_timestamp,
                    video_x=x + w / 2,
                    video_y=y + h / 2,
                )
            except Exception as e:
                import warnings
                warnings.warn(f"Tracking position save failed for player {player_id}: {e}")

    def _start_bbox_draw(self):
        player_id = self.event_tagger.active_player_id
        if player_id is None:
            QMessageBox.warning(self, "No Player", "Select a player first.")
            return
        if self._last_frame is None:
            QMessageBox.warning(self, "No Video", "Load a video first.")
            return
        self.video_player.pause()
        self.video_widget.set_bbox_mode(True)
        self.statusBar().showMessage(
            "TRACKING: Click and drag a box around the player  —  Esc to cancel"
        )

    @pyqtSlot(int, int, int, int)
    def _on_bbox_drawn(self, x: int, y: int, w: int, h: int):
        player_id = self.event_tagger.active_player_id
        if player_id is None or self._last_frame is None:
            return
        self.player_tracker.add(player_id, self._last_frame, (x, y, w, h))
        self._rebuild_tracking_labels()
        self.video_widget.update_tracking_boxes(
            {pid: self.player_tracker.get_box(pid) for pid in self.player_tracker.active_ids},
            self._tracking_labels,
        )
        self.sidebar.set_tracking_status(self.player_tracker.active_ids)
        self.statusBar().showMessage(
            f"Tracking player — press Space to play"
        )

    def _rebuild_tracking_labels(self):
        """Refresh the player_id → display-label mapping used by the video overlay."""
        if self._current_match_id is None:
            return
        players = self.database.get_players(self._current_match_id)
        self._tracking_labels = {p["id"]: f"#{p['number']} {p['name']}" for p in players}

    def _start_calibration(self):
        self._calib_points = []
        self.video_player.pause()
        self.video_widget.set_calibration_mode(True)
        self.sidebar.set_calibration_status(False)
        self.statusBar().showMessage(
            "CALIBRATION: Click the Top-Left corner of the pitch  (1/4)  —  Esc to cancel"
        )

    @pyqtSlot(int, float, float)
    def _on_calibration_point(self, idx: int, x: float, y: float):
        self._calib_points.append((x, y))
        if len(self._calib_points) < 4:
            next_label = ["Top-Left", "Top-Right", "Bottom-Right", "Bottom-Left"][len(self._calib_points)]
            self.statusBar().showMessage(
                f"CALIBRATION: Click the {next_label} corner  "
                f"({len(self._calib_points) + 1}/4)  —  Esc to cancel"
            )
        else:
            self.video_widget.set_calibration_mode(False)
            try:
                self.pitch_mapper.calibrate(self._calib_points)
            except ValueError as e:
                self._calib_points = []
                self.sidebar.set_calibration_status(False)
                QMessageBox.warning(self, "Calibration Failed", str(e))
                return
            if self._video_path:
                self.database.save_calibration(self._video_path, self._calib_points)
            self._calib_points = []
            self.sidebar.set_calibration_status(True)
            self.statusBar().showMessage(
                "Calibration complete — pitch coordinates are now active."
            )

    @pyqtSlot(str)
    def _on_destination_awaiting(self, event_type: str):
        self.statusBar().showMessage(
            f"DESTINATION: Click where the {event_type} was received  —  Esc to skip"
        )

    @pyqtSlot(dict)
    def _on_destination_set(self, event: dict):
        self.statusBar().showMessage(
            f"{event.get('event_type', 'Event').title()} destination recorded."
        )

    def _run_auto_detect(self):
        if self._last_frame is None:
            QMessageBox.warning(self, "No Video", "Load a video first.")
            return
        self.statusBar().showMessage("AI detection running…")
        try:
            result = self.auto_tagger.detect(self._last_frame)
        except RuntimeError as e:
            QMessageBox.critical(self, "AI Detection Error", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "AI Detection Error", str(e))
            return

        players = result["players"]
        ball    = result["ball"]
        self.video_widget.update_detections(players, ball)

        # Auto-set click location to ball centre if detected
        if ball is not None:
            bx, by, bw, bh, _ = ball
            self.event_tagger.set_click_coords(bx + bw / 2, by + bh / 2)
            msg = f"Detected {len(players)} player(s) + ball — click location set to ball. Press a tag key to record."
        else:
            msg = f"Detected {len(players)} player(s). No ball found."

        self.statusBar().showMessage(msg, 6000)
        self.setFocus()

    def closeEvent(self, event):
        self.video_player.release()
        self.database.close()
        event.accept()


# ── Small dialogs ─────────────────────────────────────────────────────────────

class NewMatchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Match")
        layout = QFormLayout(self)
        self._name  = QLineEdit("Match 1")
        self._home  = QLineEdit("Home Team")
        self._away  = QLineEdit("Away Team")
        layout.addRow("Match Name:", self._name)
        layout.addRow("Home Team:",  self._home)
        layout.addRow("Away Team:",  self._away)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _validate(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Invalid Input", "Match name cannot be empty.")
            self._name.setFocus()
            return
        self.accept()

    def values(self):
        return self._name.text().strip(), self._home.text().strip(), self._away.text().strip()


class LoadMatchDialog(QDialog):
    def __init__(self, matches: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Load Match")
        self.setMinimumWidth(400)
        self._matches = matches
        layout = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.setStyleSheet("font-size: 13px;")
        for m in matches:
            item = QListWidgetItem(f"{m['name']}  —  {m['home_team']} vs {m['away_team']}  ({m['date']})")
            item.setData(Qt.UserRole, m)
            self._list.addItem(item)
        self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self._list)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_match(self):
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else None


class AddPlayerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Player")
        layout = QFormLayout(self)
        self._name   = QLineEdit()
        self._number = QLineEdit()
        self._team   = QLineEdit()
        layout.addRow("Name:",   self._name)
        layout.addRow("Number:", self._number)
        layout.addRow("Team:",   self._team)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _validate(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Invalid Input", "Player name cannot be empty.")
            self._name.setFocus()
            return
        try:
            int(self._number.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Jersey number must be a whole number.")
            self._number.setFocus()
            return
        self.accept()

    def values(self):
        return self._name.text().strip(), int(self._number.text()), self._team.text().strip()
