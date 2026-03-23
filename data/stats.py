EVENT_TYPES = ("pass", "shot", "goal", "cross", "tackle", "dribble", "foul")


class StatsGenerator:
    def __init__(self, database):
        self.db = database

    def for_player(self, match_id: int, player_id=None) -> dict:
        """Stats for one player (or the whole match if player_id is None)."""
        events = self.db.get_all_events(match_id)
        if player_id is not None:
            events = [e for e in events if e["player_id"] == player_id]
        return self._compute(events)

    def all_players(self, match_id: int) -> list:
        """One stats dict per player who has at least one event."""
        players = self.db.get_players(match_id)
        rows = []
        for p in players:
            stats = self.for_player(match_id, p["id"])
            if stats["total"] > 0:
                rows.append({"player": p, **stats})
        return rows

    @staticmethod
    def _compute(events: list) -> dict:
        counts = {t: 0 for t in EVENT_TYPES}
        for e in events:
            t = e.get("event_type", "")
            if t in counts:
                counts[t] += 1

        # Pass completion (only events where outcome was recorded)
        passes_with_outcome = [
            e for e in events
            if e["event_type"] == "pass" and e.get("outcome")
        ]
        if passes_with_outcome:
            complete = sum(1 for e in passes_with_outcome if e["outcome"] == "complete")
            pass_completion = complete / len(passes_with_outcome)
        else:
            pass_completion = None   # no outcome data, not the same as 0%

        # Shot accuracy (on target / total shots with outcome)
        shots_with_outcome = [
            e for e in events
            if e["event_type"] == "shot" and e.get("outcome")
        ]
        if shots_with_outcome:
            on_target = sum(1 for e in shots_with_outcome if e["outcome"] == "on target")
            shot_accuracy = on_target / len(shots_with_outcome)
        else:
            shot_accuracy = None

        return {
            "total":           len(events),
            "counts":          counts,
            "pass_completion": pass_completion,   # 0.0–1.0 or None
            "shot_accuracy":   shot_accuracy,     # 0.0–1.0 or None
        }
