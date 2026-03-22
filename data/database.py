import sqlite3
import threading
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSlot


class Database(QObject):
    def __init__(self, db_path="footballiq.db"):
        super().__init__()
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()
        self._migrate_schema()

    def _create_schema(self):
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS matches (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    name      TEXT NOT NULL,
                    home_team TEXT,
                    away_team TEXT,
                    date      TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS players (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id  INTEGER NOT NULL REFERENCES matches(id),
                    name      TEXT,
                    number    INTEGER,
                    team      TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id    INTEGER NOT NULL REFERENCES matches(id),
                    player_id   INTEGER REFERENCES players(id),
                    event_type  TEXT NOT NULL,
                    timestamp   REAL,
                    frame_number INTEGER,
                    video_x     REAL,
                    video_y     REAL,
                    pitch_x     REAL,
                    pitch_y     REAL,
                    outcome     TEXT,
                    tagged_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tracking (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id     INTEGER NOT NULL REFERENCES matches(id),
                    player_id    INTEGER NOT NULL REFERENCES players(id),
                    frame_number INTEGER,
                    timestamp    REAL,
                    video_x      REAL,
                    video_y      REAL,
                    pitch_x      REAL,
                    pitch_y      REAL
                );
            """)
            self._conn.commit()

    def _migrate_schema(self):
        """Add columns introduced after initial schema — safe to run on existing DBs."""
        new_cols = [
            ("events", "dest_video_x", "REAL"),
            ("events", "dest_video_y", "REAL"),
            ("events", "dest_pitch_x", "REAL"),
            ("events", "dest_pitch_y", "REAL"),
        ]
        with self._lock:
            for table, col, col_type in new_cols:
                try:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass  # column already exists
            self._conn.commit()

    # ── Match ──────────────────────────────────────────────────────────────

    def create_match(self, name, home_team="", away_team="", date=None):
        date = date or datetime.today().strftime("%Y-%m-%d")
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO matches (name, home_team, away_team, date) VALUES (?,?,?,?)",
                (name, home_team, away_team, date)
            )
            self._conn.commit()
            return cur.lastrowid

    def get_matches(self):
        with self._lock:
            rows = self._conn.execute("SELECT * FROM matches ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    # ── Players ────────────────────────────────────────────────────────────

    def add_player(self, match_id, name, number, team=""):
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO players (match_id, name, number, team) VALUES (?,?,?,?)",
                (match_id, name, number, team)
            )
            self._conn.commit()
            return cur.lastrowid

    def get_players(self, match_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM players WHERE match_id=? ORDER BY number", (match_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Events ─────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def save_event(self, event: dict):
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO events
                   (match_id, player_id, event_type, timestamp, frame_number,
                    video_x, video_y, pitch_x, pitch_y, outcome,
                    dest_video_x, dest_video_y, dest_pitch_x, dest_pitch_y)
                   VALUES (:match_id,:player_id,:event_type,:timestamp,:frame_number,
                           :video_x,:video_y,:pitch_x,:pitch_y,:outcome,
                           :dest_video_x,:dest_video_y,:dest_pitch_x,:dest_pitch_y)""",
                {**event,
                 "dest_video_x": event.get("dest_video_x"),
                 "dest_video_y": event.get("dest_video_y"),
                 "dest_pitch_x": event.get("dest_pitch_x"),
                 "dest_pitch_y": event.get("dest_pitch_y")}
            )
            self._conn.commit()
            return cur.lastrowid

    def update_event_destination(self, event_id: int,
                                 dest_video_x: float, dest_video_y: float,
                                 dest_pitch_x: float, dest_pitch_y: float):
        """Set the destination coords on an already-saved pass/cross event."""
        with self._lock:
            self._conn.execute(
                """UPDATE events SET
                   dest_video_x=?, dest_video_y=?, dest_pitch_x=?, dest_pitch_y=?
                   WHERE id=?""",
                (dest_video_x, dest_video_y, dest_pitch_x, dest_pitch_y, event_id)
            )
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            return dict(row) if row else {}

    def delete_event(self, event_id: int):
        with self._lock:
            self._conn.execute("DELETE FROM events WHERE id=?", (event_id,))
            self._conn.commit()

    def get_all_events(self, match_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE match_id=? ORDER BY timestamp", (match_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Tracking ───────────────────────────────────────────────────────────

    @pyqtSlot(int, float, float)
    def save_tracking_point(self, player_id: int, pitch_x: float, pitch_y: float,
                            match_id: int = None, frame_number: int = None,
                            timestamp: float = None, video_x: float = None,
                            video_y: float = None):
        with self._lock:
            self._conn.execute(
                """INSERT INTO tracking
                   (match_id, player_id, frame_number, timestamp, video_x, video_y, pitch_x, pitch_y)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (match_id, player_id, frame_number, timestamp, video_x, video_y, pitch_x, pitch_y)
            )
            self._conn.commit()

    def get_player_positions(self, player_id, match_id=None):
        with self._lock:
            if match_id:
                rows = self._conn.execute(
                    "SELECT pitch_x, pitch_y FROM tracking WHERE player_id=? AND match_id=?",
                    (player_id, match_id)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT pitch_x, pitch_y FROM tracking WHERE player_id=?", (player_id,)
                ).fetchall()
            return [(r["pitch_x"], r["pitch_y"]) for r in rows]

    def close(self):
        self._conn.close()
