import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QFileDialog,
    QMenuBar, QAction, QInputDialog, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QLabel
)
from PyQt5.QtCore import Qt, pyqtSlot

from core.video_player  import VideoPlayer
from core.pitch_mapper  import PitchMapper
from core.event_tagger  import EventTagger
from data.database      import Database
from ui.video_widget    import VideoWidget
from ui.sidebar         import Sidebar


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

        self._current_match_id = None

        # ── UI ───────────────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video_widget = VideoWidget()
        self.sidebar      = Sidebar()
        layout.addWidget(self.video_widget, stretch=1)
        layout.addWidget(self.sidebar)

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

        act_open = QAction("Open Video...", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._open_video_dialog)
        file_menu.addAction(act_open)

        file_menu.addSeparator()

        act_export = QAction("Export CSV (E)", self)
        act_export.triggered.connect(self._export_csv)
        file_menu.addAction(act_export)

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

        # VideoWidget → EventTagger (click coordinates)
        self.video_widget.click_coords.connect(self.event_tagger.set_click_coords)

        # EventTagger → Sidebar (new event / undo)
        self.event_tagger.event_tagged.connect(self.sidebar.add_event)
        self.event_tagger.event_untagged.connect(self.sidebar.remove_event)

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

        # Ctrl+C — start pitch calibration (placeholder message for now)
        if key == Qt.Key_C and mods & Qt.ControlModifier:
            QMessageBox.information(
                self, "Calibration",
                "Pitch calibration will be available in the next update.\n"
                "Click the 4 corner points of the pitch to calibrate."
            )
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

        # Number keys 1–11 — select player by number
        if Qt.Key_1 <= key <= Qt.Key_9:
            num = key - Qt.Key_0
            self._select_player_by_number(num)
            return

        # H — heatmap
        if key == Qt.Key_H and not mods:
            self._show_heatmap()
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
            self.event_tagger.tag_event(KEY_EVENT_MAP[key])
            return

        super().keyPressEvent(event)

    # ── Dialogs & actions ─────────────────────────────────────────────────

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
            self.video_player.load_video(path)
            self.setWindowTitle(f"FootballIQ Tagger — {os.path.basename(path)}")
        self.setFocus()

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

    def _show_heatmap(self):
        if self._current_match_id is None:
            QMessageBox.warning(self, "No Match", "No active match.")
            return
        try:
            from data.heatmap import HeatmapGenerator
            player_id = self.event_tagger._active_player_id
            gen = HeatmapGenerator(self.database)
            gen.show_heatmap(self._current_match_id, player_id)
        except Exception as e:
            QMessageBox.critical(self, "Heatmap Error", str(e))
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
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def values(self):
        return self._name.text(), self._home.text(), self._away.text()


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
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def values(self):
        try:
            number = int(self._number.text())
        except ValueError:
            number = 0
        return self._name.text(), number, self._team.text()
