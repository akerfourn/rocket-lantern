"""Verify world coordinates from incoming JSON through SQLite to map projection."""

import json
import sqlite3
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication

from rocket_lantern.event_map_data import positioned_events
from rocket_lantern.game_presence import GamePresenceApi, GamePresenceMonitor
from rocket_lantern.local_player import LocalPlayerLog
from rocket_lantern.map_projection import MapCamera, MapProjection, goal_vertices
from rocket_lantern.match_data import MatchCollector
from rocket_lantern.match_detail_dialog import MatchDetailDialog
from rocket_lantern.protocol import normalize_message
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow

TIME = "2026-10-23T18:00:00+00:00"
BLUE = {"PrimaryId": "Epic|blue|0", "Name": "Blue", "TeamNum": 0, "Shortcut": 1}
ORANGE = {"PrimaryId": "Epic|orange|0", "Name": "Orange", "TeamNum": 1, "Shortcut": 1}


def state(guid: str = "match", *, swapped: bool = False) -> dict[str, object]:
    blue = dict(BLUE)
    orange = dict(ORANGE)
    if swapped:
        blue["TeamNum"] = 1
        orange["TeamNum"] = 0
    return {
        "Event": "UpdateState",
        "Data": {
            "MatchGuid": guid,
            "Players": [blue, orange],
            "Game": {"PlaylistId": 11, "TimeSeconds": 150, "bReplay": False},
        },
    }


def occurrence(
    kind: str, position: tuple[float, float, float], guid: str = "match"
) -> dict[str, object]:
    """Use deliberately conflicting location fields to detect a wrong source field."""
    data: dict[str, object] = {
        "MatchGuid": guid,
        "Scorer": dict(BLUE),
        "Player": dict(BLUE),
        "Players": [dict(BLUE)],
        "BallLastTouch": {"Player": dict(ORANGE), "Speed": 1234},
        "GoalTime": 7.25,
        "GoalSpeed": 1500.5,
        "ImpactLocation": {"X": -111, "Y": -222, "Z": 333},
        "BallLocation": {"X": 444, "Y": 555, "Z": 666},
        "Location": {"X": -777, "Y": 888, "Z": 999},
        "Ball": {"Location": {"X": 12, "Y": 34, "Z": 56}, "PostHitSpeed": 1100},
    }
    vector = dict(zip(("X", "Y", "Z"), position, strict=True))
    if kind == "BallHit":
        data["Ball"]["Location"] = vector
    else:
        field = {
            "GoalScored": "ImpactLocation",
            "CrossbarHit": "BallLocation",
            "BoostPickup": "Location",
        }[kind]
        data[field] = vector
    return {"Event": kind, "Data": data}


@pytest.fixture
def store() -> Iterator[MatchStore]:
    database = MatchStore(":memory:")
    yield database
    database.close()


@pytest.mark.parametrize("encoded_data", [False, True])
@pytest.mark.parametrize("kind", ["GoalScored", "BallHit", "CrossbarHit", "BoostPickup"])
def test_event_coordinates_should_survive_json_sqlite_and_map_without_swaps_or_mirroring(
    store: MatchStore, kind: str, encoded_data: bool
) -> None:
    collector = MatchCollector()
    collector.observe(state(), TIME)
    expected = (-69.59713745117188, -5249.3330078125, 182.97671508789062)
    message = occurrence(kind, expected)
    if encoded_data:
        message["Data"] = json.dumps(message["Data"])
    wire = json.dumps(message)

    snapshot = collector.observe(normalize_message(json.loads(wire)), TIME)
    assert snapshot is not None
    store.save_details(snapshot)
    rows = store.events("match")
    point = positioned_events(rows, store.match_event_participants("match"))[0]

    assert len(rows) == 1
    assert (rows[0]["x"], rows[0]["y"], rows[0]["z"]) == expected
    assert point.position == expected
    assert point.event_id == rows[0]["id"]
    assert point.kind == kind


def test_later_payload_mutation_and_team_changes_should_not_rewrite_an_earlier_goal(
    store: MatchStore,
) -> None:
    collector = MatchCollector()
    snapshot = collector.observe(state(), TIME)
    first = occurrence("GoalScored", (120.125, 5250.25, 94.5))
    original = deepcopy(first)
    collector.observe(first, TIME)
    assert first == original
    first["Data"]["ImpactLocation"].update(X=9999, Y=-8888, Z=7777)
    first["Data"]["Scorer"]["TeamNum"] = 1
    collector.observe(state(swapped=True), TIME)
    second = occurrence("GoalScored", (-320.75, -5300.125, 210.25))
    second["Data"]["Scorer"]["TeamNum"] = 1
    collector.observe(second, TIME)
    assert snapshot is not None

    store.save_details(snapshot)
    points = positioned_events(store.events("match"), store.match_event_participants("match"))

    assert [point.position for point in points] == [
        (120.125, 5250.25, 94.5),
        (-320.75, -5300.125, 210.25),
    ]
    assert [point.actor_team for point in points] == [0, 1]
    assert points[0].actor_key == points[1].actor_key


def test_missing_goal_position_should_not_inherit_a_previous_goal_or_another_location_field(
    store: MatchStore,
) -> None:
    collector = MatchCollector()
    collector.observe(state(), TIME)
    collector.observe(occurrence("GoalScored", (15.25, 5280.5, 93.75)), TIME)
    missing = occurrence("GoalScored", (0, 0, 0))
    del missing["Data"]["ImpactLocation"]
    snapshot = collector.observe(missing, TIME)
    assert snapshot is not None

    store.save_details(snapshot)
    rows = store.events("match")
    points = positioned_events(rows, store.match_event_participants("match"))

    assert len(rows) == 2
    assert (rows[1]["x"], rows[1]["y"], rows[1]["z"]) == (None, None, None)
    assert [point.event_id for point in points] == [rows[0]["id"]]


@pytest.fixture
def window(application: QApplication, store: MatchStore, tmp_path: Path) -> Iterator[MainWindow]:
    api = Mock(spec=GamePresenceApi)
    api.game_process_ids.return_value = frozenset()
    presence = GamePresenceMonitor(application, api)
    widget = MainWindow(store, presence, LocalPlayerLog(tmp_path / "absent.log"))
    presence.timer.stop()
    widget.local_player_monitor.stop()
    yield widget
    widget.close()


def test_real_message_dispatch_should_preserve_positions_through_retries_and_interleaved_matches(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.logs.api_details.setChecked(True)
    window.client._receive_text(json.dumps(state("first")))
    first = occurrence("GoalScored", (-123.25, -5249.125, 182.5), "first")
    first["Data"] = json.dumps(first["Data"])
    with monkeypatch.context() as patch:
        patch.setattr(
            window.store, "save_details", Mock(side_effect=sqlite3.OperationalError("locked"))
        )
        window.client._receive_text(json.dumps(first))
    assert window.store.events("first") == []
    assert window.collector.snapshots["first"].events
    window.client._receive_binary(QByteArray(json.dumps(state("second")).encode("utf-8")))
    assert not window.collector.snapshots["first"].events
    second = occurrence("GoalScored", (321.875, 5301.25, 102.125), "second")
    window.client._receive_text(json.dumps(second))
    delayed = occurrence("GoalScored", (11.5, 5260.25, 200.75), "first")
    window.client._receive_text(json.dumps(delayed))
    window.client._receive_text(json.dumps(delayed))
    first_rows = window.store.events("first")
    second_rows = window.store.events("second")

    assert [(row["x"], row["y"], row["z"]) for row in first_rows] == [
        (-123.25, -5249.125, 182.5),
        (11.5, 5260.25, 200.75),
    ]
    assert [(row["x"], row["y"], row["z"]) for row in second_rows] == [(321.875, 5301.25, 102.125)]
    dialog = MatchDetailDialog(window.store, "first", window)
    dialog.tabs.setCurrentWidget(dialog.map_page)
    assert dialog.map_panel is not None
    assert [(point.event_id, point.position) for point in dialog.map_panel.points] == [
        (row["id"], (row["x"], row["y"], row["z"])) for row in first_rows
    ]
    dialog.close()


@pytest.mark.parametrize("yaw,elevation", [(0, 90), (-35, 38), (145, 12)])
def test_projection_should_place_goal_centers_and_their_world_positions_together(
    yaw: float, elevation: float
) -> None:
    blue = (0.0, -5120.0, 320.0)
    orange = (0.0, 5120.0, 320.0)
    camera = MapCamera(yaw=yaw, elevation=elevation, zoom=1.7, target=blue)
    projection = MapProjection.fit(camera, (blue, orange), 900, 500)

    for team, center in ((0, blue), (1, orange)):
        opening = goal_vertices(team)[:4]
        projected = [projection.project(vertex) for vertex in opening]
        left = min(point[0] for point in projected)
        right = max(point[0] for point in projected)
        top = min(point[1] for point in projected)
        bottom = max(point[1] for point in projected)
        x, y, _ = projection.project(center)
        assert left <= x <= right
        assert top <= y <= bottom
        assert camera.unproject(*camera.project(center)) == pytest.approx(center, abs=1e-9)
        assert {vertex[1] for vertex in opening} == {center[1]}
