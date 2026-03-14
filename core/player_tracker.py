import cv2


class PlayerTracker:
    """
    Manages multiple CSRT trackers, one per player.

    Usage:
        tracker = PlayerTracker()
        tracker.add(player_id, frame, (x, y, w, h))
        boxes = tracker.update(frame)   # {player_id: (x, y, w, h)}
    """

    def __init__(self):
        self._trackers = {}   # player_id → cv2.TrackerCSRT
        self._boxes    = {}   # player_id → (x, y, w, h) last known bbox

    def add(self, player_id, frame, bbox):
        """
        Initialize (or reinitialize) a CSRT tracker for player_id.
        bbox: (x, y, w, h) in frame pixel coords.
        """
        tracker = cv2.TrackerCSRT_create()
        tracker.init(frame, bbox)
        self._trackers[player_id] = tracker
        self._boxes[player_id]    = tuple(int(v) for v in bbox)

    def update(self, frame):
        """
        Update all trackers with the new frame.
        Returns {player_id: (x, y, w, h)} for successfully tracked players.
        Players whose trackers fail are automatically removed.
        """
        results = {}
        failed  = []
        for player_id, tracker in self._trackers.items():
            ok, bbox = tracker.update(frame)
            if ok:
                x, y, w, h = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                self._boxes[player_id] = (x, y, w, h)
                results[player_id] = (x, y, w, h)
            else:
                failed.append(player_id)
        for pid in failed:
            del self._trackers[pid]
            del self._boxes[pid]
        return results

    def remove(self, player_id):
        self._trackers.pop(player_id, None)
        self._boxes.pop(player_id, None)

    def clear(self):
        self._trackers.clear()
        self._boxes.clear()

    @property
    def active_ids(self):
        return list(self._trackers.keys())

    @property
    def is_empty(self):
        return len(self._trackers) == 0
