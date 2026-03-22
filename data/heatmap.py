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

    def show_pass_map(self, match_id, player_id=None):
        player_id = player_id or None
        title = f"Player {player_id} — Pass Map" if player_id else "All Players — Pass Map"
        fig = self.generate_pass_map(match_id, player_id)

        dlg = QDialog()
        dlg.setWindowTitle(title)
        dlg.resize(800, 520)
        layout = QVBoxLayout(dlg)
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        dlg.exec_()
        plt.close(fig)

    def show_shot_map(self, match_id, player_id=None):
        title = f"Player {player_id} — Shot Map" if player_id else "All Players — Shot Map"
        fig = self._render_shot_map(match_id, player_id, title)

        dlg = QDialog()
        dlg.setWindowTitle(title)
        dlg.resize(800, 520)
        layout = QVBoxLayout(dlg)
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        dlg.exec_()
        plt.close(fig)

    def _render_shot_map(self, match_id, player_id=None, title="Shot Map"):
        if player_id:
            events = [e for e in self.db.get_all_events(match_id)
                      if e["event_type"] in ("shot", "goal") and e["player_id"] == player_id]
        else:
            events = [e for e in self.db.get_all_events(match_id)
                      if e["event_type"] in ("shot", "goal")]

        pitch = Pitch(
            pitch_type="custom",
            pitch_length=120, pitch_width=80,
            pitch_color="#1a1a1a", line_color="#cccccc",
        )
        fig, ax = pitch.draw(figsize=(10, 6.5))
        fig.patch.set_facecolor("#1a1a1a")

        shots = [e for e in events if e["event_type"] == "shot" and e.get("pitch_x") is not None]
        goals = [e for e in events if e["event_type"] == "goal" and e.get("pitch_x") is not None]

        if shots:
            pitch.scatter(
                [e["pitch_x"] for e in shots], [e["pitch_y"] for e in shots],
                ax=ax, s=120, color="#F44336", alpha=0.8, zorder=3, label="Shot"
            )
        if goals:
            pitch.scatter(
                [e["pitch_x"] for e in goals], [e["pitch_y"] for e in goals],
                ax=ax, s=180, color="#FFD700", marker="*", zorder=4, label="Goal"
            )

        ax.legend(facecolor="#2a2a2a", labelcolor="white", loc="upper left")
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

        # Split events into those with a destination (arrows) and those without (dots)
        arrow_events = [
            e for e in events
            if e.get("pitch_x") is not None and e.get("dest_pitch_x") is not None
        ]
        dot_events = [
            e for e in events
            if e.get("pitch_x") is not None and e.get("dest_pitch_x") is None
        ]

        if arrow_events:
            pitch.arrows(
                [e["pitch_x"] for e in arrow_events],
                [e["pitch_y"] for e in arrow_events],
                [e["dest_pitch_x"] for e in arrow_events],
                [e["dest_pitch_y"] for e in arrow_events],
                ax=ax, color="cyan", width=1.5, headwidth=4, headlength=4,
                alpha=0.8, zorder=3,
            )

        if dot_events:
            pitch.scatter(
                [e["pitch_x"] for e in dot_events],
                [e["pitch_y"] for e in dot_events],
                ax=ax, s=80, color="cyan", alpha=0.6, zorder=3,
            )

        ax.set_title("Pass Map", color="white", fontsize=13)
        return fig
