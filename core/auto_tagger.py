"""
YOLO-based auto-detection for the current video frame.
Detects players (person) and the ball, returning their bounding boxes so
the UI can display overlays and auto-set the click location to the ball.

The model (yolov8n.pt) is downloaded automatically on first use (~6 MB).
"""

# COCO class indices used here
_PERSON_CLS = 0
_BALL_CLS   = 32


class AutoTagger:
    def __init__(self):
        self._model = None

    def _load_model(self):
        try:
            from ultralytics import YOLO
            self._model = YOLO("yolov8n.pt")
        except ImportError:
            raise RuntimeError(
                "ultralytics is not installed.\n"
                "Run:  pip install ultralytics"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load AI model: {e}\n\n"
                "This is usually a missing Visual C++ redistributable or an\n"
                "incompatible PyTorch build.  Fix it by running:\n\n"
                "  pip uninstall torch torchvision -y\n"
                "  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu"
            )

    def detect(self, frame):
        """
        Run inference on a BGR numpy frame.

        Returns
        -------
        dict with keys:
          'players' : list of (x, y, w, h, conf)  – bounding boxes in frame coords
          'ball'    : (x, y, w, h, conf) or None
        """
        if self._model is None:
            self._load_model()

        results = self._model(frame, verbose=False)[0]

        players = []
        ball    = None

        for box in results.boxes:
            cls  = int(box.cls)
            conf = float(box.conf)
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            entry = (x1, y1, x2 - x1, y2 - y1, conf)

            if cls == _PERSON_CLS:
                players.append(entry)
            elif cls == _BALL_CLS and (ball is None or conf > ball[4]):
                ball = entry  # keep highest-confidence detection

        return {"players": players, "ball": ball}
