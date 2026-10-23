"""Only identical positioned events are hidden; original stored data is untouched."""

import json
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from rocket_lantern.event_data import EventParticipant, MatchEvent
from rocket_lantern.event_deduplication import visible_events
from rocket_lantern.event_map_data import positioned_events
from rocket_lantern.match_data import MatchSnapshot, PlayerStats
from rocket_lantern.match_detail_dialog import MatchDetailDialog
from rocket_lantern.storage import MatchStore

TIME = "2026-10-23T19:00:00+00:00"


def event_row(event_id: int, delay_ms: float = 0, kind: str = "BallHit") -> dict[str, object]:
    return {
        "id": event_id,
        "match_id": 1,
        "kind": kind,
        "source_event": kind,
        "origin": "api",
        "observed_at": (
            datetime.fromisoformat(TIME) + timedelta(milliseconds=delay_ms)
        ).isoformat(),
        "time_seconds": 120,
        "overtime": False,
        "actor_id": 1,
        "actor_name": "Nova",
        "actor_team": 0,
        "secondary_id": None,
        "secondary_name": None,
        "team": 0,
        "speed": 1000.0,
        "round_seconds": None,
        "x": 100.25,
        "y": 5120.0,
        "z": 200.5,
        "position_subject": "ball",
        "fingerprint": f"occurrence-{event_id}",
        "details_json": '{"PreHitSpeed":800,"PostHitSpeed":1000}',
    }


@pytest.mark.parametrize(
    "kind", ["BallHit", "CrossbarHit", "BoostPickup", "GoalScored", "FutureHit"]
)
def test_positioned_events_should_hide_repeats_without_changing_original_rows(kind: str) -> None:
    first = event_row(1, kind=kind)
    duplicate = event_row(2, 30, kind)
    duplicate["time_seconds"] = 119
    rows = [first, duplicate]
    original = deepcopy(rows)

    visible = visible_events(rows, [])

    assert visible == [first]
    assert visible[0] is first, "Keep the first occurrence's ID for linked selection"
    assert rows == original


def test_positioned_events_should_keep_types_players_and_matches_distinct() -> None:
    rows = [event_row(1)]
    different_kind = event_row(2, 10, "CrossbarHit")
    different_player = event_row(3, 20)
    different_player["actor_id"] = 2
    different_match = event_row(4, 30)
    different_match["match_id"] = 2
    rows.extend((different_kind, different_player, different_match))

    assert visible_events(rows, []) == rows


def test_positioned_events_should_compare_every_hitter_not_only_the_first_actor() -> None:
    rows = [event_row(1), event_row(2, 30)]
    references = [
        {"event_id": 1, "role": "hitter", "player_id": 1, "name": "Nova"},
        {"event_id": 1, "role": "hitter", "player_id": 2, "name": "Orbit"},
        {"event_id": 2, "role": "hitter", "player_id": 1, "name": "Nova"},
        {"event_id": 2, "role": "hitter", "player_id": 3, "name": "Comet"},
    ]

    assert visible_events(rows, references) == rows


def test_positioned_events_should_keep_unresolved_player_hints_distinct() -> None:
    rows = [event_row(1), event_row(2, 30)]
    for row in rows:
        row.update(actor_id=None, actor_name=None)
    references = [
        {"event_id": 1, "role": "hitter", "name": "Nova", "team": 0, "shortcut": 1},
        {"event_id": 2, "role": "hitter", "name": "Orbit", "team": 0, "shortcut": 2},
    ]

    assert visible_events(rows, references) == rows


@pytest.mark.parametrize("field", ["x", "y", "z", "speed", "round_seconds"])
def test_positioned_events_should_keep_changed_coordinates_or_measurements(field: str) -> None:
    first = event_row(1)
    second = event_row(2, 30)
    first["round_seconds"] = 1.0
    second["round_seconds"] = 1.0
    second[field] += 0.000001

    assert visible_events([first, second], []) == [first, second]


def test_positioned_events_should_compare_details_independently_of_json_key_order() -> None:
    first = event_row(1)
    same = event_row(2, 30)
    same["details_json"] = '{"PostHitSpeed":1000,"PreHitSpeed":800}'
    changed = event_row(3, 40)
    changed["details_json"] = json.dumps({"PostHitSpeed": 1000, "PreHitSpeed": 801})

    assert visible_events([first, same, changed], []) == [first, changed]


def test_positioned_events_should_keep_missing_positions_and_derived_state_transitions() -> None:
    missing = [event_row(1), event_row(2, 30)]
    for row in missing:
        row["z"] = None
    transitions = [event_row(3, 40), event_row(4, 50)]
    for row in transitions:
        row["origin"] = "state"
    rows = [*missing, *transitions]

    assert visible_events(rows, []) == rows


def test_positioned_events_should_keep_later_identical_hits_after_the_duplicate_window() -> None:
    rows = [event_row(1), event_row(2, 101)]

    assert visible_events(rows, []) == rows


def test_dialog_and_map_should_show_one_positioned_event_and_preserve_both_in_sqlite(
    application: QApplication,
) -> None:
    store = MatchStore(":memory:")
    snapshot = MatchSnapshot("duplicates", TIME)
    snapshot.players["one"] = PlayerStats("one", "Nova", 0)
    for index, delay in enumerate((0, 30)):
        event = MatchEvent(
            "BallHit",
            (datetime.fromisoformat(TIME) + timedelta(milliseconds=delay)).isoformat(),
            120,
            False,
            actor="one",
            x=100.25,
            y=5120.0,
            z=200.5,
            speed=1000,
            fingerprint=f"duplicate-{index}",
            source_event="BallHit",
            position_subject="ball",
            participants=[EventParticipant("hitter", "one", "Nova", 0, 1)],
        )
        snapshot.events[event.fingerprint] = event
    store.save_details(snapshot)
    before = [dict(row) for row in store.events("duplicates")]
    dialog = MatchDetailDialog(store, "duplicates")
    try:
        assert len(before) == 2
        assert dialog.events.rowCount() == 1
        assert dialog.events.item(0, 1).data(Qt.ItemDataRole.UserRole) == before[0]["id"]
        dialog.tabs.setCurrentWidget(dialog.map_page)
        assert len(dialog.map_panel.points) == 1
        assert dialog.map_panel.points[0].event_id == before[0]["id"]
        assert len(positioned_events(store.events("duplicates"), [])) == 1
        assert [dict(row) for row in store.events("duplicates")] == before
    finally:
        dialog.close()
        store.close()
