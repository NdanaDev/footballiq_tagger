from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


VALID_EVENTS = {"pass", "shot", "tackle", "dribble", "goal", "cross", "foul"}


class EventTagger(QObject):
    event_tagged   = pyqtSignal(dict)   # raw event dict (before pitch mapping)
    event_untagged = pyqtSignal(int)    # db row id of the undone event

    def __init__(self, pitch_mapper, database, parent=None):
        super().__init__(parent)
        self.pitch_mapper = pitch_mapper
        self.database = database

        self._current_timestamp   = 0.0
        self._current_frame       = 0
        self._click_x             = None
        self._click_y             = None
        self._active_player_id    = None
        self._active_match_id     = None
        self._undo_stack          = []   # list of db event ids (max 20)

    # ── Slots from other modules ───────────────────────────────────────────

    @pyqtSlot(float)
    def update_timestamp(self, t: float):
        self._current_timestamp = t

    def update_frame_number(self, n: int):
        self._current_frame = n

    def set_click_coords(self, x: float, y: float):
        self._click_x = x
        self._click_y = y

    def set_active_player(self, player_id):
        self._active_player_id = player_id

    def set_active_match(self, match_id):
        self._active_match_id = match_id

    # ── Tagging ────────────────────────────────────────────────────────────

    def tag_event(self, event_type: str, outcome: str = None):
        if event_type not in VALID_EVENTS:
            return

        pitch_x, pitch_y = None, None
        if self._click_x is not None and self._click_y is not None:
            pitch_x, pitch_y = self.pitch_mapper.transform(self._click_x, self._click_y)

        event = {
            "match_id":     self._active_match_id,
            "player_id":    self._active_player_id,
            "event_type":   event_type,
            "timestamp":    self._current_timestamp,
            "frame_number": self._current_frame,
            "video_x":      self._click_x,
            "video_y":      self._click_y,
            "pitch_x":      pitch_x,
            "pitch_y":      pitch_y,
            "outcome":      outcome,
            "tagged_at":    datetime.now().isoformat(),
        }

        # Save immediately — no data loss on crash
        row_id = self.database.save_event(event)
        event["id"] = row_id

        # Push onto undo stack (cap at 20)
        self._undo_stack.append(row_id)
        if len(self._undo_stack) > 20:
            self._undo_stack.pop(0)

        self.event_tagged.emit(event)

    def undo_last(self):
        if not self._undo_stack:
            return
        row_id = self._undo_stack.pop()
        self.database.delete_event(row_id)
        self.event_untagged.emit(row_id)
