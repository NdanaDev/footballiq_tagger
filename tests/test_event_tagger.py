import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# QApplication must exist before any QObject is instantiated
from PyQt5.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(sys.argv)

from core.event_tagger import EventTagger
from core.pitch_mapper  import PitchMapper
from data.database      import Database


def _make_tagger():
    db    = Database(":memory:")
    pm    = PitchMapper()          # uncalibrated — pitch_x/y will be None
    mid   = db.create_match("Match", "H", "A")
    pid   = db.add_player(mid, "Player", 10, "H")
    et    = EventTagger(pm, db)
    et.set_active_match(mid)
    et.set_active_player(pid)
    et.set_click_coords(320.0, 240.0)
    return et, db, mid, pid


class TestTagEvent(unittest.TestCase):

    def setUp(self):
        self.tagger, self.db, self.mid, self.pid = _make_tagger()

    def test_tag_event_saves_to_db(self):
        self.tagger.tag_event("pass")
        events = self.db.get_all_events(self.mid)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "pass")

    def test_tag_event_emits_signal(self):
        received = []
        self.tagger.event_tagged.connect(received.append)
        self.tagger.tag_event("shot")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["event_type"], "shot")

    def test_tag_event_stores_player_id(self):
        self.tagger.tag_event("tackle")
        events = self.db.get_all_events(self.mid)
        self.assertEqual(events[0]["player_id"], self.pid)

    def test_tag_event_stores_timestamp(self):
        self.tagger.update_timestamp(12.5)
        self.tagger.tag_event("dribble")
        events = self.db.get_all_events(self.mid)
        self.assertAlmostEqual(events[0]["timestamp"], 12.5)

    def test_tag_event_stores_frame_number(self):
        self.tagger.update_frame_number(300)
        self.tagger.tag_event("foul")
        events = self.db.get_all_events(self.mid)
        self.assertEqual(events[0]["frame_number"], 300)

    def test_tag_event_stores_click_coords(self):
        self.tagger.set_click_coords(100.0, 200.0)
        self.tagger.tag_event("cross")
        events = self.db.get_all_events(self.mid)
        self.assertAlmostEqual(events[0]["video_x"], 100.0)
        self.assertAlmostEqual(events[0]["video_y"], 200.0)

    def test_tag_event_stores_outcome(self):
        self.tagger.tag_event("pass", outcome="complete")
        events = self.db.get_all_events(self.mid)
        self.assertEqual(events[0]["outcome"], "complete")

    def test_invalid_event_type_ignored(self):
        self.tagger.tag_event("offside")
        self.assertEqual(self.db.get_all_events(self.mid), [])

    def test_emitted_event_has_db_id(self):
        received = []
        self.tagger.event_tagged.connect(received.append)
        self.tagger.tag_event("goal")
        self.assertIn("id", received[0])
        self.assertIsNotNone(received[0]["id"])


class TestUndoStack(unittest.TestCase):

    def setUp(self):
        self.tagger, self.db, self.mid, _ = _make_tagger()

    def test_undo_removes_from_db(self):
        self.tagger.tag_event("pass")
        self.assertEqual(len(self.db.get_all_events(self.mid)), 1)
        self.tagger.undo_last()
        self.assertEqual(len(self.db.get_all_events(self.mid)), 0)

    def test_undo_emits_event_untagged(self):
        received = []
        self.tagger.event_untagged.connect(received.append)
        self.tagger.tag_event("pass")
        eid = self.db.get_all_events(self.mid)[0]["id"]
        self.tagger.undo_last()
        self.assertEqual(received, [eid])

    def test_undo_empty_stack_is_noop(self):
        self.tagger.undo_last()   # must not raise

    def test_undo_removes_most_recent_event(self):
        self.tagger.tag_event("pass")
        self.tagger.tag_event("shot")
        self.tagger.undo_last()
        events = self.db.get_all_events(self.mid)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "pass")

    def test_undo_stack_capped_at_20(self):
        for _ in range(21):
            self.tagger.tag_event("tackle")
        # Undo 20 times — all should succeed
        for _ in range(20):
            self.tagger.undo_last()
        # 21st undo hits empty stack — must not raise
        self.tagger.undo_last()
        # 1 event should remain (the oldest, which fell off the stack)
        self.assertEqual(len(self.db.get_all_events(self.mid)), 1)


class TestDestinationFlow(unittest.TestCase):

    def setUp(self):
        self.tagger, self.db, self.mid, _ = _make_tagger()
        # Calibrate the pitch mapper so destinations are processed
        self.tagger.pitch_mapper.calibrate(
            [(0, 0), (640, 0), (640, 480), (0, 480)]
        )
        self.tagger.set_click_coords(100.0, 100.0)

    def test_pass_sets_awaiting_destination(self):
        self.tagger.tag_event("pass")
        self.assertTrue(self.tagger.awaiting_destination)

    def test_cross_sets_awaiting_destination(self):
        self.tagger.tag_event("cross")
        self.assertTrue(self.tagger.awaiting_destination)

    def test_tackle_does_not_set_awaiting(self):
        self.tagger.tag_event("tackle")
        self.assertFalse(self.tagger.awaiting_destination)

    def test_destination_awaiting_signal_emitted(self):
        received = []
        self.tagger.destination_awaiting.connect(received.append)
        self.tagger.tag_event("pass")
        self.assertEqual(received, ["pass"])

    def test_second_click_records_destination(self):
        self.tagger.tag_event("pass")
        eid = self.db.get_all_events(self.mid)[0]["id"]
        # Simulate user clicking the destination
        self.tagger.set_click_coords(400.0, 300.0)
        event = self.db.get_all_events(self.mid)[0]
        self.assertAlmostEqual(event["dest_video_x"], 400.0)

    def test_second_click_clears_awaiting(self):
        self.tagger.tag_event("pass")
        self.tagger.set_click_coords(400.0, 300.0)
        self.assertFalse(self.tagger.awaiting_destination)

    def test_cancel_destination_clears_awaiting(self):
        self.tagger.tag_event("pass")
        self.tagger.cancel_destination()
        self.assertFalse(self.tagger.awaiting_destination)

    def test_undo_cancels_pending_destination(self):
        self.tagger.tag_event("pass")
        self.assertTrue(self.tagger.awaiting_destination)
        self.tagger.undo_last()
        self.assertFalse(self.tagger.awaiting_destination)
        self.assertEqual(self.db.get_all_events(self.mid), [])


class TestPublicProperties(unittest.TestCase):

    def setUp(self):
        self.tagger, _, _, self.pid = _make_tagger()

    def test_active_player_id(self):
        self.assertEqual(self.tagger.active_player_id, self.pid)

    def test_has_click_location_true(self):
        self.assertTrue(self.tagger.has_click_location)

    def test_has_click_location_false(self):
        et = EventTagger(PitchMapper(), Database(":memory:"))
        self.assertFalse(et.has_click_location)

    def test_awaiting_destination_false_initially(self):
        self.assertFalse(self.tagger.awaiting_destination)


if __name__ == "__main__":
    unittest.main()
