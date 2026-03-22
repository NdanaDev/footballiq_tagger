import cv2
import math

# OpenCV 4.5+ moved trackers to cv2.legacy
def _make_csrt():
    if hasattr(cv2, "TrackerCSRT_create"):
        return cv2.TrackerCSRT_create()
    return cv2.legacy.TrackerCSRT_create()

# Try to load YOLO for detection-assisted re-anchoring.
# If ultralytics isn't installed the tracker falls back to pure CSRT.
try:
    from ultralytics import YOLO as _YOLO
    _YOLO_AVAILABLE = True
except Exception:
    _YOLO_AVAILABLE = False

# ── Tuning knobs ────────────────────────────────────────────────────────────
# Max pixels a tracked box centre may move from its velocity-predicted
# position before it is considered a drift (and snapped back).
_MAX_DRIFT_PX = 80

# Two boxes are considered overlapping when their IoU exceeds this.
_OVERLAP_IOU_THRESHOLD = 0.30

# Re-anchor to a YOLO detection every N frames.
# Lower = more responsive but more CPU; higher = faster but less correction.
_YOLO_REANCHOR_INTERVAL = 10

# Minimum IoU between a YOLO detection and the current CSRT box needed to
# accept the detection as "the same player".
_YOLO_MATCH_IOU = 0.25

# YOLO model to use.  'yolov8n.pt' is the smallest/fastest.
_YOLO_MODEL_NAME = "yolov8n.pt"
# ────────────────────────────────────────────────────────────────────────────


def _center(bbox):
    x, y, w, h = bbox
    return x + w / 2, y + h / 2


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(ax, bx)
    iy = max(ay, by)
    iw = max(0, min(ax + aw, bx + bw) - ix)
    ih = max(0, min(ay + ah, by + bh) - iy)
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _dist(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _xywh_from_xyxy(x1, y1, x2, y2):
    return int(x1), int(y1), int(x2 - x1), int(y2 - y1)


class PlayerTracker:
    """
    Manages multiple CSRT trackers, one per player.

    When ultralytics is available, YOLO person detections are used every
    _YOLO_REANCHOR_INTERVAL frames to re-anchor each tracker to the closest
    matching detection.  This prevents CSRT from drifting to a nearby player
    during occlusions.

    Usage:
        tracker = PlayerTracker()
        tracker.add(player_id, frame, (x, y, w, h))
        boxes = tracker.update(frame)   # {player_id: (x, y, w, h)}
    """

    def __init__(self):
        self._trackers   = {}   # player_id → cv2.TrackerCSRT
        self._boxes      = {}   # player_id → (x, y, w, h) last known bbox
        self._velocity   = {}   # player_id → (vx, vy) smoothed per-frame motion
        self._frame_count = 0

        self._yolo = None
        if _YOLO_AVAILABLE:
            try:
                self._yolo = _YOLO(_YOLO_MODEL_NAME)
            except Exception:
                self._yolo = None

    # ── public API ───────────────────────────────────────────────────────────

    def add(self, player_id, frame, bbox):
        """Initialize (or reinitialize) a CSRT tracker for player_id.
        bbox: (x, y, w, h) in frame pixel coords."""
        x, y, w, h = (int(v) for v in bbox)
        fh, fw = frame.shape[:2]
        x = max(0, min(x, fw - 2))
        y = max(0, min(y, fh - 2))
        w = max(2, min(w, fw - x))
        h = max(2, min(h, fh - y))
        bbox = (x, y, w, h)
        tracker = _make_csrt()
        tracker.init(frame, bbox)
        self._trackers[player_id] = tracker
        self._boxes[player_id]    = bbox
        self._velocity[player_id] = (0.0, 0.0)

    def update(self, frame):
        """Update all trackers.  Returns {player_id: (x, y, w, h)}."""
        self._frame_count += 1

        # --- Step 1: run CSRT on every tracker ---
        results, failed = self._csrt_update(frame)

        # --- Step 2: drift guard (velocity-based) ---
        results = self._apply_drift_guard(frame, results)

        # --- Step 3: overlap correction ---
        results = self._apply_overlap_correction(frame, results)

        # --- Step 4: YOLO re-anchor (every N frames) ---
        if self._yolo is not None and (self._frame_count % _YOLO_REANCHOR_INTERVAL == 0):
            results = self._yolo_reanchor(frame, results)

        # clean up failed trackers
        for pid in failed:
            self._trackers.pop(pid, None)
            self._boxes.pop(pid, None)
            self._velocity.pop(pid, None)

        return results

    def remove(self, player_id):
        self._trackers.pop(player_id, None)
        self._boxes.pop(player_id, None)
        self._velocity.pop(player_id, None)

    def clear(self):
        self._trackers.clear()
        self._boxes.clear()
        self._velocity.clear()
        self._frame_count = 0

    @property
    def active_ids(self):
        return list(self._trackers.keys())

    @property
    def is_empty(self):
        return len(self._trackers) == 0

    # ── internal helpers ─────────────────────────────────────────────────────

    def _csrt_update(self, frame):
        results = {}
        failed  = []
        for player_id, tracker in self._trackers.items():
            ok, raw_bbox = tracker.update(frame)
            if ok:
                results[player_id] = (
                    int(raw_bbox[0]), int(raw_bbox[1]),
                    int(raw_bbox[2]), int(raw_bbox[3]),
                )
            else:
                failed.append(player_id)
        return results, failed

    def _apply_drift_guard(self, frame, results):
        """Snap any box that jumped further than _MAX_DRIFT_PX from its prediction."""
        for player_id, new_box in list(results.items()):
            prev_box = self._boxes[player_id]
            vx, vy   = self._velocity[player_id]
            px, py   = _center(prev_box)
            pred_cx  = px + vx
            pred_cy  = py + vy
            new_cx, new_cy = _center(new_box)

            if _dist((new_cx, new_cy), (pred_cx, pred_cy)) > _MAX_DRIFT_PX:
                _, _, pw, ph = prev_box
                snapped = (int(pred_cx - pw / 2), int(pred_cy - ph / 2), pw, ph)
                self._reinit(player_id, frame, snapped)
                results[player_id] = snapped
            else:
                self._boxes[player_id] = new_box
                self._velocity[player_id] = (
                    0.5 * vx + 0.5 * (new_cx - px),
                    0.5 * vy + 0.5 * (new_cy - py),
                )
        return results

    def _apply_overlap_correction(self, frame, results):
        """When two boxes overlap heavily, snap the one that drifted more."""
        ids = list(results.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pid_a, pid_b = ids[i], ids[j]
                if pid_a not in results or pid_b not in results:
                    continue
                if _iou(results[pid_a], results[pid_b]) < _OVERLAP_IOU_THRESHOLD:
                    continue

                def drift(pid):
                    vx, vy = self._velocity[pid]
                    cx, cy = _center(results[pid])
                    return _dist((cx, cy), (cx - vx, cy - vy))

                drifter = pid_a if drift(pid_a) >= drift(pid_b) else pid_b
                _, _, pw, ph = self._boxes[drifter]
                dvx, dvy = self._velocity[drifter]
                cx, cy   = _center(results[drifter])
                snapped  = (int(cx - dvx - pw / 2), int(cy - dvy - ph / 2), pw, ph)
                self._reinit(drifter, frame, snapped)
                results[drifter] = snapped
        return results

    def _yolo_reanchor(self, frame, results):
        """
        Run YOLO on the current frame, find all 'person' detections, then for
        each tracked player find the detection that best overlaps its current
        box.  If the best match has IoU >= _YOLO_MATCH_IOU AND is closer to
        the player's predicted position than to any other tracked player's
        predicted position, re-initialize the CSRT tracker there.
        This prevents CSRT from following the wrong player after an occlusion.
        """
        try:
            yolo_results = self._yolo(frame, classes=[0], verbose=False)
        except Exception:
            return results

        # Collect person detections as (x, y, w, h)
        detections = []
        for r in yolo_results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(_xywh_from_xyxy(x1, y1, x2, y2))

        if not detections:
            return results

        for player_id, cur_box in list(results.items()):
            best_iou  = _YOLO_MATCH_IOU - 1e-9   # below threshold initially
            best_det  = None

            for det in detections:
                iou = _iou(cur_box, det)
                if iou > best_iou:
                    best_iou = iou
                    best_det = det

            if best_det is None or best_iou < _YOLO_MATCH_IOU:
                continue  # no good detection found; keep CSRT result

            # Make sure this detection is not a better match for another player
            stolen = False
            for other_id, other_box in results.items():
                if other_id == player_id:
                    continue
                if _iou(other_box, best_det) > best_iou:
                    stolen = True
                    break
            if stolen:
                continue

            # Re-anchor to the YOLO detection
            self._reinit(player_id, frame, best_det)
            results[player_id] = best_det

        return results

    def _reinit(self, player_id, frame, bbox):
        """Re-initialize the CSRT tracker at bbox and update internal state."""
        x, y, w, h = bbox
        fh, fw = frame.shape[:2]
        # clamp bbox inside frame and ensure positive size
        x = max(0, min(x, fw - 2))
        y = max(0, min(y, fh - 2))
        w = max(2, min(w, fw - x))
        h = max(2, min(h, fh - y))
        bbox = (x, y, w, h)
        t = _make_csrt()
        t.init(frame, bbox)
        self._trackers[player_id] = t
        self._boxes[player_id]    = bbox
        # reset velocity so the snap doesn't look like fast motion
        self._velocity[player_id] = (0.0, 0.0)
