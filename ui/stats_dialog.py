from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QFrame, QProgressBar,
    QHeaderView, QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from data.stats import StatsGenerator, EVENT_TYPES


# Colours shared with the event log
_EVENT_COLORS = {
    "pass":    "#4CAF50",
    "shot":    "#F44336",
    "tackle":  "#2196F3",
    "dribble": "#FF9800",
    "goal":    "#9C27B0",
    "cross":   "#00BCD4",
    "foul":    "#FF5722",
}

_CARD_STYLE = (
    "QFrame {{ background:{bg}; border-radius:6px; }}"
    "QLabel {{ background:transparent; color:{fg}; }}"
)


class StatsDialog(QDialog):
    """
    Modal dialog that displays per-player (or full-match) statistics.

    Contains a player selector combo, summary stat cards for totals/goals/passes/shots,
    percentage bars for pass-completion and shot-accuracy, and a full event-breakdown table.
    """

    def __init__(self, database, match_id: int, players: list,
                 initial_player_id=None, parent=None):
        super().__init__(parent)
        self._gen      = StatsGenerator(database)
        self._match_id = match_id
        self._players  = players

        self.setWindowTitle("Player Stats")
        self.setMinimumSize(500, 540)
        self.setStyleSheet(
            "background-color: #1e1e1e; color: #e0e0e0; font-size: 12px;"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # ── Player selector ─────────────────────────────────────────────
        self._combo = QComboBox()
        self._combo.setStyleSheet(
            "QComboBox { background:#2a2a2a; border:1px solid #444; "
            "border-radius:4px; padding:4px 8px; font-size:13px; }"
            "QComboBox::drop-down { border:none; }"
            "QComboBox QAbstractItemView { background:#2a2a2a; color:#e0e0e0; "
            "selection-background-color:#333; }"
        )
        self._combo.addItem("All Players", None)
        for p in players:
            self._combo.addItem(f"#{p['number']}  {p['name']}  ({p['team']})", p["id"])
        if initial_player_id is not None:
            for i in range(self._combo.count()):
                if self._combo.itemData(i) == initial_player_id:
                    self._combo.setCurrentIndex(i)
                    break
        root.addWidget(self._combo)

        # ── Summary cards ────────────────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        self._card_total  = _StatCard("Total Events", "0", "#2a2a2a", "#e0e0e0")
        self._card_goals  = _StatCard("Goals",         "0", "#1a0a2e", "#9C27B0")
        self._card_passes = _StatCard("Passes",        "0", "#0a1f0a", "#4CAF50")
        self._card_shots  = _StatCard("Shots",         "0", "#2a0a0a", "#F44336")
        for card in (self._card_total, self._card_goals,
                     self._card_passes, self._card_shots):
            cards_row.addWidget(card)
        root.addLayout(cards_row)

        # ── Percentage bars ──────────────────────────────────────────────
        bars_frame = QFrame()
        bars_frame.setStyleSheet(
            "QFrame { background:#252525; border-radius:6px; }"
        )
        bars_layout = QVBoxLayout(bars_frame)
        bars_layout.setContentsMargins(12, 10, 12, 10)
        bars_layout.setSpacing(8)

        self._pass_bar  = _StatBar("Pass completion", "#4CAF50")
        self._shot_bar  = _StatBar("Shot accuracy",   "#F44336")
        bars_layout.addWidget(self._pass_bar)
        bars_layout.addWidget(self._shot_bar)
        root.addWidget(bars_frame)

        # ── Event breakdown table ────────────────────────────────────────
        self._table = QTableWidget(len(EVENT_TYPES), 2)
        self._table.setHorizontalHeaderLabels(["Event Type", "Count"])
        self._table.horizontalHeader().setStyleSheet(
            "QHeaderView::section { background:#2a2a2a; color:#888; "
            "border:none; padding:4px; font-size:11px; }"
        )
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._table.setColumnWidth(1, 70)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        self._table.setFocusPolicy(Qt.NoFocus)
        self._table.setStyleSheet(
            "QTableWidget { background:#1e1e1e; border:1px solid #333; "
            "gridline-color:#2a2a2a; }"
            "QTableWidget::item { padding:4px 8px; }"
        )
        self._table.setFixedHeight(len(EVENT_TYPES) * 30 + self._table.horizontalHeader().height() + 2)
        root.addWidget(self._table)

        root.addStretch()

        self._combo.currentIndexChanged.connect(self._refresh)
        self._refresh()

    # ── Internal ────────────────────────────────────────────────────────────

    def _refresh(self):
        """Re-query stats for the currently selected player and update all widgets."""
        player_id = self._combo.currentData()
        stats = self._gen.for_player(self._match_id, player_id)

        counts = stats["counts"]
        self._card_total.set_value(str(stats["total"]))
        self._card_goals.set_value(str(counts.get("goal", 0)))
        self._card_passes.set_value(str(counts.get("pass", 0)))
        self._card_shots.set_value(str(counts.get("shot", 0)))

        self._pass_bar.set_value(stats["pass_completion"])
        self._shot_bar.set_value(stats["shot_accuracy"])

        for row, etype in enumerate(EVENT_TYPES):
            name_item = QTableWidgetItem(etype.capitalize())
            name_item.setForeground(QColor(_EVENT_COLORS.get(etype, "#e0e0e0")))
            count_item = QTableWidgetItem(str(counts.get(etype, 0)))
            count_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, count_item)


# ── Helper widgets ─────────────────────────────────────────────────────────────

class _StatCard(QFrame):
    """Small coloured card showing a label + big number."""

    def __init__(self, title: str, value: str, bg: str, accent: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(72)
        self.setStyleSheet(
            f"QFrame {{ background:{bg}; border-radius:6px; border:1px solid #333; }}"
            f"QLabel {{ background:transparent; border:none; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(f"color:#888; font-size:10px;")
        self._title_lbl.setAlignment(Qt.AlignCenter)

        self._value_lbl = QLabel(value)
        self._value_lbl.setStyleSheet(f"color:{accent}; font-size:22px; font-weight:bold;")
        self._value_lbl.setAlignment(Qt.AlignCenter)

        layout.addWidget(self._title_lbl)
        layout.addWidget(self._value_lbl)

    def set_value(self, text: str):
        self._value_lbl.setText(text)


class _StatBar(QFrame):
    """Label + QProgressBar + percentage text on one row."""

    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background:transparent; border:none; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(130)
        lbl.setStyleSheet("color:#aaa; font-size:11px;")
        layout.addWidget(lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(10)
        self._bar.setStyleSheet(
            f"QProgressBar {{ background:#3a3a3a; border-radius:5px; border:none; }}"
            f"QProgressBar::chunk {{ background:{color}; border-radius:5px; }}"
        )
        layout.addWidget(self._bar, stretch=1)

        self._pct_lbl = QLabel("—")
        self._pct_lbl.setFixedWidth(40)
        self._pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._pct_lbl.setStyleSheet(f"color:{color}; font-size:11px; font-weight:bold;")
        layout.addWidget(self._pct_lbl)

    def set_value(self, ratio):   # ratio: 0.0–1.0 or None
        if ratio is None:
            self._bar.setValue(0)
            self._pct_lbl.setText("—")
        else:
            pct = round(ratio * 100)
            self._bar.setValue(pct)
            self._pct_lbl.setText(f"{pct}%")
