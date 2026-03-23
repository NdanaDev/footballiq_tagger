import sys
import os
import sqlite3
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import Database


def _make_db():
    return Database(":memory:")


def _base_event(match_id, player_id=None):
    return {
        "match_id":     match_id,
        "player_id":    player_id,
        "event_type":   "pass",
        "timestamp":    1.5,
        "frame_number": 37,
        "video_x": 320.0, "video_y": 240.0,
        "pitch_x":  60.0, "pitch_y":  40.0,
        "outcome": "complete",
    }


class TestMatches(unittest.TestCase):

    def setUp(self):
        self.db = _make_db()

    def test_create_match_returns_id(self):
        mid = self.db.create_match("M1", "Home", "Away")
        self.assertIsInstance(mid, int)
        self.assertGreater(mid, 0)

    def test_get_matches_returns_created_match(self):
        self.db.create_match("Derby", "City", "United")
        rows = self.db.get_matches()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Derby")

    def test_get_matches_ordered_newest_first(self):
        self.db.create_match("First",  "A", "B")
        self.db.create_match("Second", "C", "D")
        rows = self.db.get_matches()
        self.assertEqual(rows[0]["name"], "Second")

    def test_match_stores_team_names(self):
        self.db.create_match("Cup Final", "Arsenal", "Chelsea")
        m = self.db.get_matches()[0]
        self.assertEqual(m["home_team"], "Arsenal")
        self.assertEqual(m["away_team"], "Chelsea")


class TestPlayers(unittest.TestCase):

    def setUp(self):
        self.db = _make_db()
        self.mid = self.db.create_match("M", "H", "A")

    def test_add_and_get_player(self):
        pid = self.db.add_player(self.mid, "Ronaldo", 7, "H")
        players = self.db.get_players(self.mid)
        self.assertEqual(len(players), 1)
        self.assertEqual(players[0]["name"],   "Ronaldo")
        self.assertEqual(players[0]["number"], 7)

    def test_get_players_ordered_by_number(self):
        self.db.add_player(self.mid, "B", 10, "H")
        self.db.add_player(self.mid, "A",  3, "H")
        numbers = [p["number"] for p in self.db.get_players(self.mid)]
        self.assertEqual(numbers, [3, 10])

    def test_add_player_returns_id(self):
        pid = self.db.add_player(self.mid, "X", 1, "H")
        self.assertIsInstance(pid, int)

    def test_foreign_key_rejects_invalid_match(self):
        with self.assertRaises(Exception):
            self.db.add_player(9999, "Ghost", 0, "X")


class TestEvents(unittest.TestCase):

    def setUp(self):
        self.db = _make_db()
        self.mid = self.db.create_match("M", "H", "A")
        self.pid = self.db.add_player(self.mid, "Player", 1, "H")

    def test_save_event_returns_id(self):
        eid = self.db.save_event(_base_event(self.mid, self.pid))
        self.assertIsInstance(eid, int)
        self.assertGreater(eid, 0)

    def test_get_all_events_round_trip(self):
        self.db.save_event(_base_event(self.mid, self.pid))
        events = self.db.get_all_events(self.mid)
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e["event_type"],   "pass")
        self.assertEqual(e["frame_number"], 37)
        self.assertAlmostEqual(e["timestamp"], 1.5)

    def test_get_all_events_ordered_by_timestamp(self):
        e1 = _base_event(self.mid);  e1["timestamp"] = 10.0
        e2 = _base_event(self.mid);  e2["timestamp"] =  2.0
        e3 = _base_event(self.mid);  e3["timestamp"] =  7.0
        for e in (e1, e2, e3):
            self.db.save_event(e)
        timestamps = [e["timestamp"] for e in self.db.get_all_events(self.mid)]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_delete_event_removes_it(self):
        eid = self.db.save_event(_base_event(self.mid))
        self.db.delete_event(eid)
        self.assertEqual(self.db.get_all_events(self.mid), [])

    def test_delete_nonexistent_event_is_noop(self):
        self.db.delete_event(9999)  # must not raise

    def test_update_event_destination(self):
        eid = self.db.save_event(_base_event(self.mid))
        updated = self.db.update_event_destination(eid, 400.0, 300.0, 80.0, 20.0)
        self.assertAlmostEqual(updated["dest_video_x"], 400.0)
        self.assertAlmostEqual(updated["dest_pitch_x"],  80.0)

    def test_events_isolated_by_match(self):
        mid2 = self.db.create_match("Other", "X", "Y")
        self.db.save_event(_base_event(self.mid))
        self.db.save_event(_base_event(mid2))
        self.assertEqual(len(self.db.get_all_events(self.mid)),  1)
        self.assertEqual(len(self.db.get_all_events(mid2)), 1)

    def test_foreign_key_rejects_invalid_match(self):
        with self.assertRaises(Exception):
            self.db.save_event(_base_event(match_id=9999))


class TestCalibration(unittest.TestCase):

    def setUp(self):
        self.db = _make_db()

    def _points(self):
        return [(0.0, 0.0), (640.0, 0.0), (640.0, 480.0), (0.0, 480.0)]

    def test_get_calibration_missing_returns_none(self):
        self.assertIsNone(self.db.get_calibration("/no/such/video.mp4"))

    def test_save_and_get_calibration_round_trip(self):
        pts = self._points()
        self.db.save_calibration("/video.mp4", pts)
        got = self.db.get_calibration("/video.mp4")
        self.assertEqual(len(got), 4)
        for i in range(4):
            self.assertAlmostEqual(got[i][0], pts[i][0])
            self.assertAlmostEqual(got[i][1], pts[i][1])

    def test_save_calibration_upserts(self):
        old = [(0, 0), (100, 0), (100, 100), (0, 100)]
        new = self._points()
        self.db.save_calibration("/v.mp4", old)
        self.db.save_calibration("/v.mp4", new)
        got = self.db.get_calibration("/v.mp4")
        self.assertAlmostEqual(got[1][0], 640.0)   # new value, not 100

    def test_different_paths_are_independent(self):
        pts_a = [(0, 0), (200, 0), (200, 200), (0, 200)]
        pts_b = self._points()
        self.db.save_calibration("/a.mp4", pts_a)
        self.db.save_calibration("/b.mp4", pts_b)
        self.assertAlmostEqual(self.db.get_calibration("/a.mp4")[1][0], 200.0)
        self.assertAlmostEqual(self.db.get_calibration("/b.mp4")[1][0], 640.0)


class TestTrackingPoints(unittest.TestCase):

    def setUp(self):
        self.db = _make_db()
        self.mid = self.db.create_match("M", "H", "A")
        self.pid = self.db.add_player(self.mid, "P", 1, "H")

    def test_save_and_get_tracking_point(self):
        self.db.save_tracking_point(
            player_id=self.pid, pitch_x=30.0, pitch_y=20.0,
            match_id=self.mid, frame_number=5, timestamp=0.2,
            video_x=100.0, video_y=80.0,
        )
        positions = self.db.get_player_positions(self.pid, self.mid)
        self.assertEqual(len(positions), 1)
        self.assertAlmostEqual(positions[0][0], 30.0)
        self.assertAlmostEqual(positions[0][1], 20.0)

    def test_get_positions_filtered_by_match(self):
        mid2 = self.db.create_match("M2", "X", "Y")
        pid2 = self.db.add_player(mid2, "Q", 2, "X")
        self.db.save_tracking_point(self.pid, 10, 10, match_id=self.mid)
        self.db.save_tracking_point(pid2,     20, 20, match_id=mid2)
        self.assertEqual(len(self.db.get_player_positions(self.pid, self.mid)), 1)
        self.assertEqual(len(self.db.get_player_positions(pid2,     mid2)),     1)
        self.assertEqual(len(self.db.get_player_positions(self.pid, mid2)),     0)


if __name__ == "__main__":
    unittest.main()
