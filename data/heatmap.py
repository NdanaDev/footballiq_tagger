import numpy as np
import matplotlib.pyplot as plt
from mplsoccer import Pitch
from PyQt5.QtWidgets import QDialog, QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas


class HeatmapGenerator:
    def __init__(self, database):
        self.db = database

    def show_heatmap(self, match_id, player_id=None):
        if player_id:
            positions = self.db.get_player_positions(player_id, match_id)
            title = f"Player {player_id} — Position Heatmap"
        else:
            # All tracking data for the match
            positions = []
            players = self.db.get_players(match_id)
            for p in players:
                positions.extend(self.db.get_player_positions(p["id"], match_id))
            title = "All Players — Position Heatmap"

        fig = self._render(positions, title)

        dlg = QDialog()
        dlg.setWindowTitle(title)
        dlg.resize(800, 520)
        layout = QVBoxLayout(dlg)
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        dlg.exec_()
        plt.close(fig)

    def _render(self, positions, title="Heatmap"):
        pitch = Pitch(
            pitch_type="custom",
            pitch_length=120,
            pitch_width=80,
            pitch_color="#1a1a1a",
            line_color="#cccccc",
        )
        fig, ax = pitch.draw(figsize=(10, 6.5))
        fig.patch.set_facecolor("#1a1a1a")

        if positions:
            xs = np.array([p[0] for p in positions if p[0] is not None])
            ys = np.array([p[1] for p in positions if p[1] is not None])
            if len(xs) >= 3:
                pitch.kdeplot(xs, ys, ax=ax, cmap="hot", fill=True, levels=100, alpha=0.7)

        ax.set_title(title, color="white", fontsize=13, pad=10)
        return fig

    def generate_pass_map(self, match_id, player_id=None):
        """Render pass origin → destination arrows (requires video_x/y pairs)."""
        if player_id:
            events = [e for e in self.db.get_all_events(match_id)
                      if e["event_type"] == "pass" and e["player_id"] == player_id]
        else:
            events = [e for e in self.db.get_all_events(match_id)
                      if e["event_type"] == "pass"]

        pitch = Pitch(
            pitch_type="custom",
            pitch_length=120, pitch_width=80,
            pitch_color="#1a1a1a", line_color="#cccccc",
        )
        fig, ax = pitch.draw(figsize=(10, 6.5))
        fig.patch.set_facecolor("#1a1a1a")

        # Simple: plot pass origin dots (destination tagging not yet implemented)
        xs = [e["pitch_x"] for e in events if e.get("pitch_x") is not None]
        ys = [e["pitch_y"] for e in events if e.get("pitch_y") is not None]
        if xs:
            pitch.scatter(xs, ys, ax=ax, s=80, color="cyan", alpha=0.8, zorder=3)

        ax.set_title("Pass Map", color="white", fontsize=13)
        return fig
