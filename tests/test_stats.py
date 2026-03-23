import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.stats import StatsGenerator, EVENT_TYPES
from data.database import Database


def _event(event_type, player_id=1, outcome=None):
    """Minimal event dict matching what get_all_events returns."""
    return {
        "event_type":  event_type,
        "player_id":   player_id,
        "outcome":     outcome,
        "pitch_x":     60.0,
        "pitch_y":     40.0,
    }


class TestComputeStatic(unittest.TestCase):
    """Tests for StatsGenerator._compute — pure function, no DB needed."""

    def _compute(self, events):
        return StatsGenerator._compute(events)

    # ── totals & counts ────────────────────────────────────────────────────

    def test_empty_events(self):
        stats = self._compute([])
        self.assertEqual(stats["total"], 0)
        self.assertIsNone(stats["pass_completion"])
        self.assertIsNone(stats["shot_accuracy"])
        for t in EVENT_TYPES:
            self.assertEqual(stats["counts"][t], 0)

    def test_total_counts_all_events(self):
        events = [_event("pass"), _event("shot"), _event("goal"), _event("tackle")]
        self.assertEqual(self._compute(events)["total"], 4)

    def test_counts_by_type(self):
        events = [
            _event("pass"), _event("pass"), _event("pass"),
            _event("shot"), _event("shot"),
            _event("goal"),
        ]
        counts = self._compute(events)["counts"]
        self.assertEqual(counts["pass"],   3)
        self.assertEqual(counts["shot"],   2)
        self.assertEqual(counts["goal"],   1)
        self.assertEqual(counts["tackle"], 0)

    def test_unknown_event_type_ignored(self):
        events = [_event("offside")]    # not in EVENT_TYPES
        stats = self._compute(events)
        self.assertEqual(stats["total"], 1)  # counts towards total
        for t in EVENT_TYPES:
            self.assertEqual(stats["counts"][t], 0)

    # ── pass completion ────────────────────────────────────────────────────

    def test_pass_completion_all_complete(self):
        events = [_event("pass", outcome="complete")] * 4
        self.assertAlmostEqual(self._compute(events)["pass_completion"], 1.0)

    def test_pass_completion_half(self):
        events = (
            [_event("pass", outcome="complete")]   * 3 +
            [_event("pass", outcome="incomplete")] * 3
        )
        self.assertAlmostEqual(self._compute(events)["pass_completion"], 0.5)

    def test_pass_completion_none_when_no_outcome(self):
        """Passes tagged without outcome should not be counted as 0%."""
        events = [_event("pass")]   # no outcome recorded
        self.assertIsNone(self._compute(events)["pass_completion"])

    def test_pass_completion_ignores_null_outcome_rows(self):
        """Only events that have an outcome contribute to the percentage."""
        events = [
            _event("pass", outcome="complete"),
            _event("pass", outcome=None),      # ignored
        ]
        self.assertAlmostEqual(self._compute(events)["pass_completion"], 1.0)

    # ── shot accuracy ──────────────────────────────────────────────────────

    def test_shot_accuracy_all_on_target(self):
        events = [_event("shot", outcome="on target")] * 3
        self.assertAlmostEqual(self._compute(events)["shot_accuracy"], 1.0)

    def test_shot_accuracy_mixed(self):
        events = [
            _event("shot", outcome="on target"),
            _event("shot", outcome="off target"),
            _event("shot", outcome="blocked"),
            _event("shot", outcome="on target"),
        ]
        # 2 on target out of 4
        self.assertAlmostEqual(self._compute(events)["shot_accuracy"], 0.5)

    def test_shot_accuracy_none_when_no_outcome(self):
        events = [_event("shot")]
        self.assertIsNone(self._compute(events)["shot_accuracy"])


class TestStatsGeneratorWithDB(unittest.TestCase):
    """Integration-level tests using an in-memory DB."""

    def setUp(self):
        self.db = Database(":memory:")
        self.gen = StatsGenerator(self.db)
        self.match_id = self.db.create_match("Test", "A", "B")
        self.p1 = self.db.add_player(self.match_id, "Alice", 7, "A")
        self.p2 = self.db.add_player(self.match_id, "Bob",   9, "B")

    def _save(self, event_type, player_id, outcome=None):
        self.db.save_event({
            "match_id":     self.match_id,
            "player_id":    player_id,
            "event_type":   event_type,
            "timestamp":    0.0,
            "frame_number": 0,
            "video_x": None, "video_y": None,
            "pitch_x": None, "pitch_y": None,
            "outcome": outcome,
        })

    def test_for_player_filters_by_player(self):
        self._save("pass", self.p1)
        self._save("shot", self.p1)
        self._save("pass", self.p2)
        stats = self.gen.for_player(self.match_id, self.p1)
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["counts"]["pass"], 1)
        self.assertEqual(stats["counts"]["shot"], 1)

    def test_for_player_none_returns_match_total(self):
        self._save("pass", self.p1)
        self._save("pass", self.p2)
        self._save("goal", self.p2)
        stats = self.gen.for_player(self.match_id, None)
        self.assertEqual(stats["total"], 3)

    def test_all_players_skips_players_with_no_events(self):
        self._save("pass", self.p1)
        rows = self.gen.all_players(self.match_id)
        # p2 has no events → excluded
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["player"]["id"], self.p1)

    def test_all_players_includes_all_active(self):
        self._save("pass", self.p1)
        self._save("shot", self.p2)
        rows = self.gen.all_players(self.match_id)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
