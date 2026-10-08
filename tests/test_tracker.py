"""Deterministic event sequences matching the official Stats API envelope."""

import pytest

from rocket_lantern.tracker import MatchTracker, parse_players

OBSERVED_AT = "2026-10-02T12:00:00+00:00"
PLAYER_ID = "Epic|test-player|0"


def state(match_id: str = "match-1", **game_fields: object) -> dict[str, object]:
    """Build a minimal live-state fixture with one known player."""
    return {
        "Event": "UpdateState",
        "Data": {
            "MatchGuid": match_id,
            "Players": [{"PrimaryId": PLAYER_ID, "Name": "Test Player", "TeamNum": 0}],
            "Game": {"PlaylistId": 11, **game_fields},
        },
    }


def event(name: str, match_id: str = "match-1", **fields: object) -> dict[str, object]:
    """Build an event fixture without a real network connection."""
    return {"Event": name, "Data": {"MatchGuid": match_id, **fields}}


@pytest.mark.parametrize("winner, expected", [(0, "win"), (1, "loss")])
def test_match_should_use_selected_team_when_result_arrives(winner: int, expected: str) -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(), OBSERVED_AT)

    results = tracker.handle(event("MatchEnded", WinnerTeamNum=winner), OBSERVED_AT)

    assert len(results) == 1
    assert results[0].outcome == expected
    assert results[0].player_id == PLAYER_ID
    assert results[0].playlist == 11


def test_match_should_ignore_duplicates_when_end_is_repeated() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(), OBSERVED_AT)
    tracker.handle(event("MatchEnded", WinnerTeamNum=0), OBSERVED_AT)

    assert tracker.handle(event("MatchEnded", WinnerTeamNum=0), OBSERVED_AT) == []
    assert tracker.handle(event("MatchDestroyed"), OBSERVED_AT) == []


def test_match_should_remain_unknown_when_connection_is_lost() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(), OBSERVED_AT)

    results = tracker.interrupt(OBSERVED_AT)

    assert len(results) == 1
    assert results[0].outcome == "unknown"
    assert tracker.interrupt(OBSERVED_AT) == []


def test_match_should_be_unknown_when_leaving_before_result() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(), OBSERVED_AT)

    results = tracker.handle(event("MatchDestroyed"), OBSERVED_AT)

    assert results[0].outcome == "unknown"


def test_match_should_ignore_other_match_events_when_active() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(), OBSERVED_AT)

    assert tracker.handle(event("MatchEnded", "old-match", WinnerTeamNum=1), OBSERVED_AT) == []
    assert tracker.handle(event("MatchDestroyed", "old-match"), OBSERVED_AT) == []
    assert tracker.handle(event("MatchEnded", WinnerTeamNum=0), OBSERVED_AT)[0].outcome == "win"


def test_match_should_ignore_result_when_player_was_not_observed() -> None:
    tracker = MatchTracker("Epic|someone-else|0")
    tracker.handle(state(), OBSERVED_AT)

    assert tracker.handle(event("MatchEnded", WinnerTeamNum=0), OBSERVED_AT) == []


def test_match_should_ignore_training_when_guid_is_empty() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(""), OBSERVED_AT)

    assert tracker.handle(event("MatchEnded", "", WinnerTeamNum=0), OBSERVED_AT) == []


def test_match_should_record_previous_unknown_when_next_match_starts() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(), OBSERVED_AT)

    results = tracker.handle(state("match-2"), OBSERVED_AT)

    assert results[0].match_id == "match-1"
    assert results[0].outcome == "unknown"
    assert tracker.match_id == "match-2"


def test_replay_should_be_ignored_when_replay_created_arrives() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(event("ReplayCreated"), OBSERVED_AT)
    tracker.handle(state(), OBSERVED_AT)

    assert tracker.handle(event("MatchEnded", WinnerTeamNum=0), OBSERVED_AT) == []
    tracker.handle(event("MatchDestroyed"), OBSERVED_AT)
    tracker.handle(state("live-match"), OBSERVED_AT)
    results = tracker.handle(event("MatchEnded", "live-match", WinnerTeamNum=1), OBSERVED_AT)
    assert results[0].outcome == "loss"


def test_replay_should_be_ignored_when_connecting_during_playback() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(bReplay=True, Frame=100, Elapsed=4.0), OBSERVED_AT)

    assert tracker.handle(event("MatchEnded", WinnerTeamNum=0), OBSERVED_AT) == []


def test_match_should_continue_when_goal_replay_is_active() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(bReplay=True), OBSERVED_AT)

    results = tracker.handle(event("MatchEnded", WinnerTeamNum=0), OBSERVED_AT)

    assert results[0].outcome == "win"


def test_match_should_remain_live_when_replay_fields_exist_but_replay_is_false() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(bReplay=False, Frame=0, Elapsed=0.0), OBSERVED_AT)

    results = tracker.handle(event("MatchEnded", WinnerTeamNum=0), OBSERVED_AT)

    assert results[0].outcome == "win"
    assert not tracker.is_history_replay


def test_match_should_continue_when_goal_replay_has_frame_fields_during_known_match() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(), OBSERVED_AT)
    tracker.handle(state(bReplay=True, Frame=100, Elapsed=4.0), OBSERVED_AT)

    results = tracker.handle(event("MatchEnded", WinnerTeamNum=0), OBSERVED_AT)

    assert results[0].outcome == "win"


def test_tracker_should_explain_missing_guid_when_training_event_arrives() -> None:
    tracker = MatchTracker(PLAYER_ID)

    results = tracker.handle(state(""), OBSERVED_AT)

    assert results == []
    assert "sans MatchGuid" in tracker.status
    assert len(tracker.players) == 1


def test_match_should_use_winner_state_when_end_event_was_missed() -> None:
    tracker = MatchTracker(PLAYER_ID)

    results = tracker.handle(
        state(bHasWinner=True, Winner="Orange", Teams=[{"Name": "Orange", "TeamNum": 1}]),
        OBSERVED_AT,
    )

    assert results[0].outcome == "loss"


def test_match_should_accept_later_result_when_winner_state_is_incomplete() -> None:
    tracker = MatchTracker(PLAYER_ID)
    results = tracker.handle(state(bHasWinner=True), OBSERVED_AT)
    assert results[0].outcome == "unknown"

    results = tracker.handle(event("MatchEnded", WinnerTeamNum=0), OBSERVED_AT)

    assert results[0].outcome == "win"


def test_match_should_reject_boolean_when_winner_number_is_malformed() -> None:
    tracker = MatchTracker(PLAYER_ID)
    tracker.handle(state(), OBSERVED_AT)

    results = tracker.handle(event("MatchEnded", WinnerTeamNum=False), OBSERVED_AT)

    assert results[0].outcome == "unknown"


def test_parser_should_skip_malformed_players_when_list_contains_invalid_entries() -> None:
    assert parse_players([None, {}, {"PrimaryId": "x", "Name": "Player", "TeamNum": True}]) == []


def test_tracker_should_raise_clear_error_when_envelope_is_invalid() -> None:
    tracker = MatchTracker()

    with pytest.raises(ValueError, match="Event et Data"):
        tracker.handle({"Event": "UpdateState", "Data": None}, OBSERVED_AT)
