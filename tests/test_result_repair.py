"""Historical corrections require a later kickoff, explicit end and consistent team evidence."""

from pathlib import Path

import pytest

from rocket_lantern.match_data import MatchSnapshot, PlayerStats
from rocket_lantern.result_repair import REPAIR_KEY, repair_premature_results
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult

PREMATURE = "2026-10-23T21:44:29+00:00"
KICKOFF = "2026-10-23T21:44:53+00:00"
TOUCH = "2026-10-23T21:51:10+00:00"
END = "2026-10-23T21:51:17+00:00"


def seed_premature_result(
    store: MatchStore,
    *,
    has_end: bool = True,
    has_kickoff: bool = True,
    has_team: bool = True,
    event_team: int = 0,
    winner: int = 1,
    recorded_at: str = PREMATURE,
) -> int:
    # Save the result before its events, as in an affected older application.
    store.save(MatchResult("casual", "player", recorded_at, 2, "win"))
    snapshot = MatchSnapshot("casual", END, winner=winner, final_observed=True)
    snapshot.players["player"] = PlayerStats("player", "Player", 0)
    snapshot.blue_score = 0
    snapshot.orange_score = 4
    if has_kickoff:
        snapshot.add_event("RoundStarted", {}, KICKOFF)
    if has_team:
        snapshot.add_event(
            "BallHit", {"Players": [{"PrimaryId": "player", "TeamNum": event_team}]}, TOUCH
        )
    if has_end:
        snapshot.add_event("MatchEnded", {"WinnerTeamNum": winner}, END)
    store.save_details(snapshot)
    return store.sessions("player")[0]["id"]


def test_startup_should_repair_premature_result_and_time_without_moving_its_links(
    tmp_path: Path,
) -> None:
    path = tmp_path / "old.sqlite3"
    original = MatchStore(path)
    session_id = seed_premature_result(original)
    original.set_evaluation("casual", "possible", END)
    before = original.connection.execute("SELECT * FROM matches").fetchone()
    events = [dict(row) for row in original.events("casual")]
    with original.connection:
        original.connection.execute("DELETE FROM settings WHERE key = ?", (REPAIR_KEY,))
    original.close()

    restored = MatchStore(path)
    try:
        row = restored.connection.execute("SELECT * FROM matches").fetchone()
        assert row["outcome"] == "loss"
        assert row["ended_at"] == END
        assert row["session_id"] == session_id
        assert (row["detail_id"], row["player_ref"]) == (before["detail_id"], before["player_ref"])
        assert restored.evaluation("casual") == "possible"
        assert [dict(row) for row in restored.events("casual")] == events
        assert restored.session_detail("player", session_id)["last_activity_at"] == END
        assert repair_premature_results(restored.connection) == 0
    finally:
        restored.close()


@pytest.mark.parametrize(
    "case",
    ["missing_end", "missing_kickoff", "missing_team", "changed_team", "already_at_end", "unknown"],
)
def test_repair_should_leave_unproven_or_correct_results_untouched(case: str) -> None:
    store = MatchStore(":memory:")
    try:
        seed_premature_result(
            store,
            has_end=case != "missing_end",
            has_kickoff=case != "missing_kickoff",
            has_team=case != "missing_team",
            event_team=1 if case == "changed_team" else 0,
            recorded_at=END if case == "already_at_end" else PREMATURE,
        )
        if case == "unknown":
            with store.connection:
                store.connection.execute("UPDATE matches SET outcome = 'unknown'")
        before = dict(store.connection.execute("SELECT * FROM matches").fetchone())

        assert repair_premature_results(store.connection, "casual") == 0

        assert dict(store.connection.execute("SELECT * FROM matches").fetchone()) == before
    finally:
        store.close()


def test_repair_should_correct_time_even_when_the_premature_outcome_happens_to_match() -> None:
    store = MatchStore(":memory:")
    try:
        seed_premature_result(store, winner=0)

        assert repair_premature_results(store.connection, "casual") == 1

        row = store.history("player")[0]
        assert row["outcome"] == "win"
        assert row["ended_at"] == END
    finally:
        store.close()


def test_save_should_repair_an_old_result_when_the_real_end_arrives_after_upgrading() -> None:
    store = MatchStore(":memory:")
    try:
        seed_premature_result(store, has_end=False)
        assert repair_premature_results(store.connection) == 0, (
            "Startup has already checked history"
        )
        snapshot = MatchSnapshot("casual", END, winner=1, final_observed=True)
        snapshot.players["player"] = PlayerStats("player", "Player", 0)
        snapshot.add_event("MatchEnded", {"WinnerTeamNum": 1}, END)
        store.save_details(snapshot)

        store.save(MatchResult("casual", "player", END, 2, "loss"))

        assert store.history("player")[0]["outcome"] == "loss"
        assert store.history("player")[0]["ended_at"] == END
    finally:
        store.close()
