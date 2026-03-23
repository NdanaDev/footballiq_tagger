import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pitch_mapper import PitchMapper, PITCH_WIDTH, PITCH_HEIGHT

# A clean rectangle that maps the full frame to the pitch
_RECT = [(0, 0), (640, 0), (640, 480), (0, 480)]


class TestCalibration(unittest.TestCase):

    def test_not_calibrated_initially(self):
        self.assertFalse(PitchMapper().is_calibrated)

    def test_is_calibrated_after_calibrate(self):
        m = PitchMapper()
        m.calibrate(_RECT)
        self.assertTrue(m.is_calibrated)

    def test_reset_clears_calibration(self):
        m = PitchMapper()
        m.calibrate(_RECT)
        m.reset()
        self.assertFalse(m.is_calibrated)

    def test_valid_rectangle_succeeds(self):
        m = PitchMapper()
        m.calibrate(_RECT)          # must not raise
        self.assertTrue(m.is_calibrated)

    def test_valid_trapezoid_succeeds(self):
        """A typical broadcast camera angle – trapezoid, still convex."""
        m = PitchMapper()
        m.calibrate([(100, 50), (540, 50), (640, 430), (0, 430)])
        self.assertTrue(m.is_calibrated)


class TestDegenerateQuads(unittest.TestCase):

    def _assert_raises(self, points):
        with self.assertRaises(ValueError):
            PitchMapper().calibrate(points)

    def test_collinear_points_raise(self):
        self._assert_raises([(0, 0), (100, 0), (200, 0), (300, 0)])

    def test_duplicate_adjacent_points_raise(self):
        self._assert_raises([(0, 0), (0, 0), (100, 100), (0, 100)])

    def test_duplicate_opposite_points_raise(self):
        # TL == BL
        self._assert_raises([(0, 0), (100, 0), (100, 100), (0, 0)])

    def test_concave_quad_raises(self):
        # Fourth point pokes inside the expected quad making it non-convex
        self._assert_raises([(0, 0), (200, 0), (200, 200), (100, 50)])

    def test_self_intersecting_butterfly_raises(self):
        # Crossing edges
        self._assert_raises([(0, 0), (100, 100), (100, 0), (0, 100)])


class TestTransform(unittest.TestCase):

    def setUp(self):
        self.m = PitchMapper()
        self.m.calibrate(_RECT)

    def test_uncalibrated_returns_none(self):
        m = PitchMapper()
        self.assertEqual(m.transform(320, 240), (None, None))

    def test_top_left_maps_to_pitch_origin(self):
        px, py = self.m.transform(0, 0)
        self.assertAlmostEqual(px, 0.0, places=1)
        self.assertAlmostEqual(py, 0.0, places=1)

    def test_bottom_right_maps_to_pitch_max(self):
        px, py = self.m.transform(640, 480)
        self.assertAlmostEqual(px, PITCH_WIDTH,  places=1)
        self.assertAlmostEqual(py, PITCH_HEIGHT, places=1)

    def test_centre_maps_to_pitch_centre(self):
        px, py = self.m.transform(320, 240)
        self.assertAlmostEqual(px, PITCH_WIDTH  / 2, places=1)
        self.assertAlmostEqual(py, PITCH_HEIGHT / 2, places=1)

    def test_out_of_bounds_clamped_to_pitch(self):
        px, py = self.m.transform(-9999, -9999)
        self.assertGreaterEqual(px, 0.0)
        self.assertGreaterEqual(py, 0.0)
        self.assertLessEqual(px, PITCH_WIDTH)
        self.assertLessEqual(py, PITCH_HEIGHT)

    def test_transform_bbox_centre_matches_point_transform(self):
        # bbox centred at (320, 240) ↔ transform(320, 240)
        expected = self.m.transform(320, 240)
        got      = self.m.transform_bbox_center(310, 230, 20, 20)
        self.assertAlmostEqual(got[0], expected[0], places=4)
        self.assertAlmostEqual(got[1], expected[1], places=4)

    def test_result_is_finite(self):
        for x, y in [(0, 0), (320, 240), (640, 480), (100, 100)]:
            px, py = self.m.transform(x, y)
            self.assertIsNotNone(px)
            self.assertTrue(-1e6 < px < 1e6)
            self.assertTrue(-1e6 < py < 1e6)


if __name__ == "__main__":
    unittest.main()
