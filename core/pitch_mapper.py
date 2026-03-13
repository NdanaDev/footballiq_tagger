import cv2
import numpy as np


PITCH_WIDTH  = 120.0   # metres
PITCH_HEIGHT = 80.0    # metres

# Destination corners in pitch coordinates (top-left, top-right, bottom-right, bottom-left)
PITCH_CORNERS = np.float32([
    [0.0,          0.0],
    [PITCH_WIDTH,  0.0],
    [PITCH_WIDTH,  PITCH_HEIGHT],
    [0.0,          PITCH_HEIGHT],
])


class PitchMapper:
    """
    Maps video pixel coordinates → real pitch coordinates (0–120 × 0–80 m).

    Usage:
        mapper = PitchMapper()
        mapper.calibrate([(x0,y0), (x1,y1), (x2,y2), (x3,y3)])
        pitch_x, pitch_y = mapper.transform(video_x, video_y)

    Calibration point order (must match PITCH_CORNERS):
        0 = top-left corner of visible pitch
        1 = top-right corner
        2 = bottom-right corner
        3 = bottom-left corner
    """

    def __init__(self):
        self._matrix = None

    def calibrate(self, src_points):
        """
        Compute homography from 4 pixel points to pitch corners.
        src_points: list/array of 4 (x, y) tuples in pixel space.
        """
        src = np.float32(src_points)
        dst = PITCH_CORNERS
        self._matrix, _ = cv2.findHomography(src, dst)

    def transform(self, video_x: float, video_y: float):
        """
        Convert a single pixel point to pitch coordinates.
        Returns (pitch_x, pitch_y) or (None, None) if not calibrated.
        """
        if self._matrix is None:
            return None, None
        pt = np.float32([[[video_x, video_y]]])
        result = cv2.perspectiveTransform(pt, self._matrix)
        px, py = float(result[0][0][0]), float(result[0][0][1])
        px = max(0.0, min(px, PITCH_WIDTH))
        py = max(0.0, min(py, PITCH_HEIGHT))
        return px, py

    def transform_bbox_center(self, x, y, w, h):
        """Helper: transform the centre of a bounding box."""
        return self.transform(x + w / 2, y + h / 2)

    @property
    def is_calibrated(self) -> bool:
        return self._matrix is not None

    def reset(self):
        self._matrix = None
