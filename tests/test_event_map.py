"""Positioned-event projection, player identity, picking and linked GUI selections."""

import math
from collections.abc import Iterator
from dataclasses import replace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QTextDocument, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QToolButton

from rocket_lantern.event_data import EventParticipant, MatchEvent
from rocket_lantern.event_map_canvas import EventMapCanvas
from rocket_lantern.event_map_data import UNKNOWN_COLOR, MapEvent, positioned_events
from rocket_lantern.event_map_panel import EventMapPanel
from rocket_lantern.i18n import language_manager
from rocket_lantern.map_projection import (
    BACK_WALL,
    GOAL_HEIGHT,
    MapCamera,
    MapProjection,
    arena_bounds,
)
from rocket_lantern.match_data import MatchSnapshot, PlayerStats
from rocket_lantern.match_detail_dialog import MatchDetailDialog
from rocket_lantern.storage import MatchStore

TIME = "2026-10-22T18:00:00+00:00"


def seed_map(store: MatchStore) -> tuple[int, ...]:
    """Store real event records with two named players, one unknown and one missing position."""
    snapshot = MatchSnapshot(
        "map-match",
        TIME,
        playlist=11,
        arena="Stadium_P",
        blue_score=2,
        orange_score=1,
        players={
            "blue": PlayerStats("blue", "Nova", 0, goals=2),
            "orange": PlayerStats("orange", "Orbit", 1, goals=1),
        },
    )
    specifications = (
        ("BallHit", "blue", "Nova", (-2500, -2000, 100), "ball"),
        ("BallHit", "orange", "Orbit", (1600, 1700, 1300), "ball"),
        ("GoalScored", "blue", "Nova", (300, 5200, 210), "ball"),
        ("BoostPickup", "orange", "Orbit", (3072, 4096, 73), "boost_pickup"),
        ("CrossbarHit", None, None, (200, -5120, 640), "ball"),
        ("ClockUpdatedSeconds", None, None, (None, None, None), None),
    )
    for index, (kind, primary_id, name, position, subject) in enumerate(specifications):
        event = MatchEvent(
            kind,
            TIME,
            125 - index,
            index == 4,
            actor=primary_id,
            x=position[0],
            y=position[1],
            z=position[2],
            fingerprint=f"point-{index}",
            position_subject=subject,
        )
        if primary_id is not None:
            role = {"GoalScored": "scorer", "BoostPickup": "collector"}.get(kind, "hitter")
            event.participants.append(EventParticipant(role, primary_id, name, index % 2, 1))
        snapshot.events[event.fingerprint] = event
    store.save_details(snapshot)
    return tuple(row["id"] for row in store.events("map-match"))


@pytest.fixture
def store() -> Iterator[MatchStore]:
    database = MatchStore(":memory:")
    seed_map(database)
    yield database
    database.close()


def test_map_data_should_keep_only_finite_full_positions_and_real_actor_links(
    store: MatchStore,
) -> None:
    points = positioned_events(
        store.events("map-match"), store.match_event_participants("map-match")
    )

    assert len(points) == 5
    assert points[0].position == (-2500, -2000, 100)
    assert points[0].actor_name == "Nova"
    assert points[0].actor_key == points[2].actor_key
    assert points[0].color == points[2].color
    assert points[0].color != points[1].color
    assert points[0].actor_team == points[2].actor_team == 0
    assert points[1].actor_team == points[3].actor_team == 1
    assert points[3].position_subject == "boost_pickup"
    assert points[4].color == UNKNOWN_COLOR
    assert points[4].actor_team is None
    assert points[4].overtime


def test_map_data_should_not_merge_identical_player_names_or_link_by_name_alone(
    store: MatchStore,
) -> None:
    rows = [dict(row) for row in store.events("map-match")]
    references = [dict(row) for row in store.match_event_participants("map-match")]
    for reference in references:
        reference["name"] = "Same name"
    points = positioned_events(rows, references)
    assert points[0].actor_name == points[1].actor_name == "Same name"
    assert points[0].color != points[1].color

    rows[0]["actor_id"] = None
    references[0].update(player_id=None, shortcut=None, team=None)
    unresolved = positioned_events(rows, references)[0]
    assert unresolved.actor_key is None
    assert unresolved.actor_name == "Same name"
    assert unresolved.color == UNKNOWN_COLOR


def test_map_data_should_retain_legacy_events_without_participant_rows(store: MatchStore) -> None:
    points = positioned_events(store.events("map-match"), [])
    assert points[0].actor_name == "Nova"
    assert points[0].actor_team == 0
    assert points[0].color != UNKNOWN_COLOR


@pytest.mark.parametrize("coordinate", [None, float("nan"), float("inf"), "12", True])
def test_map_data_should_reject_invalid_coordinates_without_turning_them_into_zero(
    store: MatchStore,
    coordinate: object,
) -> None:
    row = dict(store.events("map-match")[0])
    row["z"] = coordinate
    assert positioned_events([row], []) == ()


def test_map_colors_should_remain_deterministic_when_event_order_changes(store: MatchStore) -> None:
    rows = store.events("map-match")
    refs = store.match_event_participants("map-match")
    forward = {point.event_id: point.color for point in positioned_events(rows, refs)}
    backward = {point.event_id: point.color for point in positioned_events(rows[::-1], refs)}
    assert forward == backward


def test_map_colors_should_remain_distinct_and_qt_valid_beyond_standard_player_count(
    store: MatchStore,
) -> None:
    base = dict(store.events("map-match")[0])
    rows = []
    for index in range(12):
        row = dict(base)
        row.update(id=index + 1, actor_id=index + 1)
        rows.append(row)

    points = positioned_events(rows, [])
    assert len({point.color for point in points}) == 12
    assert all(QColor(point.color).isValid() for point in points)


def test_map_data_should_not_treat_an_assister_as_the_unknown_scorer(store: MatchStore) -> None:
    row = dict(store.events("map-match")[2])
    row["actor_id"] = None
    row["actor_name"] = None
    references = [
        {
            "event_id": row["id"],
            "role": "assister",
            "player_id": 2,
            "name": "Orbit",
            "team": 1,
            "shortcut": 2,
        }
    ]

    point = positioned_events([row], references)[0]
    assert point.actor_key is None
    assert point.actor_team is None
    assert point.color == UNKNOWN_COLOR


def test_map_data_should_use_match_local_hints_without_changing_database_links(
    store: MatchStore,
) -> None:
    row = dict(store.events("map-match")[0])
    row["actor_id"] = None
    references = [
        {
            "event_id": row["id"],
            "role": "hitter",
            "player_id": None,
            "name": "Guest",
            "team": 0,
            "shortcut": 2,
        }
    ]

    point = positioned_events([row], references)[0]
    assert point.actor_key == "hint:0:2:Guest"
    assert point.actor_team == 0
    assert references[0]["player_id"] is None
    assert row["actor_id"] is None


def test_map_data_should_use_the_actors_event_team_before_the_match_roster(
    store: MatchStore,
) -> None:
    row = dict(store.events("map-match")[0])
    references = [dict(reference) for reference in store.match_event_participants("map-match")]
    references[0]["team"] = 1

    point = positioned_events([row], references)[0]

    assert row["actor_team"] == 0
    assert point.actor_team == 1
    assert point.actor_key == f"player:{row['actor_id']}"


def test_map_data_should_keep_a_recorded_spectator_team_out_of_the_playing_teams(
    store: MatchStore,
) -> None:
    row = dict(store.events("map-match")[0])
    references = [dict(reference) for reference in store.match_event_participants("map-match")]
    references[0]["team"] = 255

    point = positioned_events([row], references)[0]

    assert row["actor_team"] == 0
    assert point.actor_team is None
    assert point.actor_key == f"player:{row['actor_id']}"


@pytest.mark.parametrize("team", [None, 255, True])
def test_map_data_should_keep_unknown_teams_neutral_without_losing_the_player_identity(
    store: MatchStore,
    team: object,
) -> None:
    row = dict(store.events("map-match")[0])
    row["actor_team"] = team
    references = [dict(reference) for reference in store.match_event_participants("map-match")]
    references[0]["team"] = team

    point = positioned_events([row], references)[0]

    assert point.actor_team is None
    assert point.actor_key == f"player:{row['actor_id']}"
    assert point.color != UNKNOWN_COLOR


def test_map_projection_should_fit_received_points_without_clamping_to_arena() -> None:
    positions = ((0.0, 0.0, 0.0), (9000.0, -14000.0, 4000.0))
    projection = MapProjection.fit(MapCamera(), positions, 700, 400)

    for position in (*arena_bounds(), *positions):
        x, y, depth = projection.project(position)
        assert 35 <= x <= 665
        assert 30 <= y <= 370
        assert math.isfinite(depth)
    assert positions[1] == (9000, -14000, 4000)


def test_map_projection_should_preserve_height_in_3d_and_remove_it_in_top_view() -> None:
    low = (100.0, 200.0, 0.0)
    high = (100.0, 200.0, 1600.0)
    camera = MapCamera()
    assert camera.project(high)[1] < camera.project(low)[1]
    camera.elevation = 90
    assert camera.project(low)[:2] == pytest.approx(camera.project(high)[:2], abs=1e-12)


def test_map_camera_should_bound_rotation_and_zoom() -> None:
    camera = MapCamera()
    camera.rotate(10000, -10000)
    assert 0 <= camera.yaw < 360
    assert camera.elevation == 12
    camera.rotate(0, 10000)
    assert camera.elevation == 90
    camera.zoom_by(1000)
    assert camera.zoom == 6
    camera.zoom_by(1e-10)
    assert camera.zoom == 0.5


def test_map_canvas_should_pick_points_and_keep_camera_controls_off_the_database(
    application: QApplication,
    store: MatchStore,
) -> None:
    points = positioned_events(
        store.events("map-match"), store.match_event_participants("map-match")
    )
    canvas = EventMapCanvas(points)
    canvas.resize(720, 420)
    canvas.show()
    application.processEvents()
    selected = []
    canvas.event_selected.connect(selected.append)
    changes = store.connection.total_changes
    x, y, _ = canvas.projection().project(points[0].position)

    assert canvas.hit_test(QPointF(x, y)) == points[0].event_id
    before = canvas.grab().toImage()
    canvas.select_event(points[0].event_id)
    application.processEvents()
    assert canvas.grab().toImage() != before
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(x), round(y)))
    assert selected == [points[0].event_id]
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    QTest.keyClick(canvas, Qt.Key.Key_Plus)
    assert canvas.camera.yaw != MapCamera().yaw
    assert canvas.camera.zoom > 1
    wheel = QWheelEvent(
        QPointF(100, 100),
        QPointF(100, 100),
        QPoint(),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    canvas.wheelEvent(wheel)
    assert canvas.camera.zoom == pytest.approx(1)
    assert store.connection.total_changes == changes
    assert not canvas.grab().isNull()
    canvas.close()


def test_map_canvas_should_not_select_an_event_when_dragging_to_rotate(
    application: QApplication,
) -> None:
    canvas = EventMapCanvas(())
    canvas.resize(500, 300)
    canvas.show()
    selected = []
    canvas.event_selected.connect(selected.append)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(canvas, QPoint(150, 120))
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(150, 120))

    assert canvas.camera.yaw != MapCamera().yaw
    assert selected == []
    canvas.close()


def test_map_canvas_should_pick_the_nearest_depth_when_screen_positions_overlap(
    application: QApplication,
) -> None:
    base = MapEvent(1, "BallHit", (0, 0, 0), 120, False, None, None, (), "ball")
    canvas = EventMapCanvas((base, replace(base, event_id=2, position=(0, 0, 1500))))
    canvas.resize(600, 400)
    canvas.top_view()
    x, y, _ = canvas.projection().project(base.position)
    assert canvas.hit_test(QPointF(x, y)) == 2


def test_dialog_should_load_map_lazily_and_link_all_three_selection_paths(
    application: QApplication,
    store: MatchStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_participants = Mock(wraps=store.match_event_participants)
    monkeypatch.setattr(store, "match_event_participants", read_participants)
    dialog = MatchDetailDialog(store, "map-match")
    dialog.show()
    assert dialog.map_panel is None
    read_participants.assert_called_once_with("map-match")
    dialog.events.selectRow(1)
    dialog.tabs.setCurrentWidget(dialog.map_page)
    application.processEvents()
    panel = dialog.map_panel
    assert panel is not None
    assert len(panel.points) == 5
    assert panel.canvas.selected_id == panel.points[1].event_id
    assert panel.events.currentRow() == 1

    panel.events.selectRow(3)
    assert panel.canvas.selected_id == panel.points[3].event_id
    assert dialog.events.currentRow() == 3
    assert "Point de boost" in panel.position.text()
    x, y, _ = panel.canvas.projection().project(panel.points[0].position)
    QTest.mouseClick(panel.canvas, Qt.MouseButton.LeftButton, pos=QPoint(round(x), round(y)))
    assert panel.canvas.selected_id == panel.points[0].event_id
    assert panel.events.currentRow() == 0
    assert dialog.events.currentRow() == 0

    dialog.events.selectRow(5)
    assert panel.canvas.selected_id is None
    assert panel.events.selectedItems() == []
    dialog.tabs.setCurrentIndex(0)
    dialog.tabs.setCurrentWidget(dialog.map_page)
    assert dialog.map_panel is panel
    read_participants.assert_called_once_with("map-match")
    dialog.close()


def test_map_should_keep_clock_format_and_language_changes_without_resetting_selection(
    application: QApplication,
    store: MatchStore,
) -> None:
    manager = language_manager()
    previous = manager.language
    manager.set_language("fr")
    dialog = MatchDetailDialog(store, "map-match")
    dialog.show()
    dialog.tabs.setCurrentWidget(dialog.map_page)
    panel = dialog.map_panel
    assert panel is not None
    panel.events.selectRow(4)
    assert panel.events.item(4, 0).text() == "Prolongation 2:01"
    dialog.clock_format.setCurrentIndex(dialog.clock_format.findData("seconds"))
    assert panel.events.item(4, 0).text() == "Prolongation 121"
    selected_id = panel.canvas.selected_id
    try:
        manager.set_language("en")
        application.processEvents()
        assert panel.events.item(4, 0).text() == "Overtime 121"
        assert panel.events.item(0, 1).text() == "Ball touch"
        assert panel.events.item(0, 2).text() == "Nova"
        assert "Unknown player" in panel.legend.text()
        assert "Blue team" in panel.legend.text()
        assert "Orange team" in panel.legend.text()
        assert "Unknown team" in panel.legend.text()
        assert "Équipe bleue" not in panel.legend.text()
        assert panel.canvas.selected_id == selected_id
        assert panel.top_button.text() == "Top view"
    finally:
        dialog.close()
        manager.set_language(previous)
        application.processEvents()


def test_map_legend_should_group_players_by_team_and_preserve_event_colors(
    application: QApplication,
    store: MatchStore,
) -> None:
    dialog = MatchDetailDialog(store, "map-match")
    dialog.tabs.setCurrentWidget(dialog.map_page)
    panel = dialog.map_panel
    assert panel is not None
    document = QTextDocument()
    document.setHtml(panel.legend.text())
    legend = document.toPlainText()

    assert legend.index("Équipe bleue") < legend.index("Nova") < legend.index("Équipe orange")
    assert legend.index("Équipe orange") < legend.index("Orbit") < legend.index("Équipe inconnue")
    assert legend.index("Équipe inconnue") < legend.index("Auteur inconnu")
    assert legend.count("Nova") == legend.count("Orbit") == 1
    assert all(point.color in panel.legend.text() for point in panel.points)
    dialog.close()


def test_map_legend_should_show_a_player_in_both_teams_after_a_team_switch(
    application: QApplication,
    store: MatchStore,
) -> None:
    points = positioned_events(
        store.events("map-match"), store.match_event_participants("map-match")
    )
    player = points[0]
    panel = EventMapPanel(
        (player, replace(player, event_id=100, actor_team=1)),
        lambda seconds, overtime: str(seconds),
    )
    document = QTextDocument()
    document.setHtml(panel.legend.text())
    legend = document.toPlainText()

    assert legend.count("Nova") == 2
    assert "Équipe bleue" in legend and "Équipe orange" in legend
    assert panel.points[0].color == panel.points[1].color == player.color
    panel.close()


def test_map_should_explain_empty_history_and_reset_camera_without_clearing_selection(
    application: QApplication,
    store: MatchStore,
) -> None:
    store.save_details(MatchSnapshot("empty", TIME))
    dialog = MatchDetailDialog(store, "empty")
    dialog.tabs.setCurrentWidget(dialog.map_page)
    panel = dialog.map_panel
    assert panel is not None
    assert panel.events.rowCount() == 0
    assert panel.legend.text() == ""
    assert "Aucun événement" in panel.position.text()
    assert not panel.canvas.grab().isNull()
    panel.top_button.click()
    assert panel.canvas.camera.elevation == 90
    panel.reset_button.click()
    assert panel.canvas.camera == MapCamera()
    dialog.close()


def test_map_should_support_read_only_storage_and_escape_names_in_the_legend(
    application: QApplication,
    store: MatchStore,
) -> None:
    with store.connection:
        store.connection.execute(
            "UPDATE match_event_players SET name = '<b>Nova</b>' WHERE player_id = 1"
        )
    store.connection.execute("PRAGMA query_only = ON")
    changes = store.connection.total_changes
    dialog = MatchDetailDialog(store, "map-match")
    dialog.tabs.setCurrentWidget(dialog.map_page)
    panel = dialog.map_panel
    assert panel is not None
    assert "&lt;b&gt;Nova&lt;/b&gt;" in panel.legend.text()
    assert "<b>Nova</b>" not in panel.legend.text()
    panel.events.selectRow(0)
    selected_id = panel.canvas.selected_id
    panel.top_button.click()
    panel.reset_button.click()
    assert panel.canvas.selected_id == selected_id
    panel.canvas.event_selected.emit(None)
    assert dialog.events.selectedItems() == []
    assert store.connection.total_changes == changes
    dialog.close()


@pytest.mark.parametrize("yaw,elevation", [(0, 12), (145, 38), (270, 90)])
def test_camera_should_round_trip_world_positions_through_camera_space(
    yaw: float,
    elevation: float,
) -> None:
    camera = MapCamera(yaw=yaw, elevation=elevation)
    position = (1234.0, -4567.0, 1310.0)

    assert camera.unproject(*camera.project(position)) == pytest.approx(position, abs=1e-9)


@pytest.mark.parametrize("target", [None, (0.0, -5120.0, 320.0)])
def test_projection_should_pan_with_the_pointer_without_changing_zoom_or_rotation(
    target: tuple[float, float, float] | None,
) -> None:
    camera = MapCamera(zoom=1.7, target=target)
    point = (1200.0, 1500.0, 500.0)
    before = MapProjection.fit(camera, (point,), 700, 450)
    x, y, _ = before.project(point)

    camera.target = before.panned_target(43, -27)
    after = MapProjection.fit(camera, (point,), 700, 450)
    moved_x, moved_y, _ = after.project(point)

    assert (moved_x - x, moved_y - y) == pytest.approx((43, -27), abs=1e-9)
    assert (camera.yaw, camera.elevation, camera.zoom) == (-35, 38, 1.7)


def test_projection_should_keep_the_chosen_pivot_fixed_during_rotation_and_resize() -> None:
    target = (0.0, -5120.0, GOAL_HEIGHT / 2)
    camera = MapCamera(target=target, zoom=2)

    for width, height, rotation in (
        (700, 450, (0, 0)),
        (1200, 800, (80, 20)),
        (600, 400, (-190, -30)),
    ):
        camera.rotate(*rotation)
        projection = MapProjection.fit(camera, (), width, height)
        assert projection.project(target)[:2] == pytest.approx((width / 2, height / 2))
        assert camera.target == target


@pytest.mark.parametrize(
    "button,modifier",
    [
        (Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier),
        (Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier),
        (Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier),
    ],
)
def test_canvas_should_pan_without_rotating_or_changing_event_selection(
    application: QApplication,
    button: Qt.MouseButton,
    modifier: Qt.KeyboardModifier,
) -> None:
    canvas = EventMapCanvas(())
    canvas.resize(600, 400)
    canvas.show()
    canvas.select_event(42)
    selected = []
    canvas.event_selected.connect(selected.append)

    QTest.mousePress(canvas, button, modifier, QPoint(200, 160))
    QTest.mouseMove(canvas, QPoint(260, 180))
    QTest.mouseRelease(canvas, button, modifier, QPoint(260, 180))

    assert canvas.camera.target is not None
    assert (canvas.camera.yaw, canvas.camera.elevation, canvas.camera.zoom) == (-35, 38, 1)
    assert canvas.selected_id == 42
    assert selected == []
    canvas.close()


def test_map_target_buttons_should_preserve_angle_zoom_and_selected_event(
    application: QApplication,
    store: MatchStore,
) -> None:
    changes = store.connection.total_changes
    dialog = MatchDetailDialog(store, "map-match")
    dialog.tabs.setCurrentWidget(dialog.map_page)
    panel = dialog.map_panel
    assert panel is not None
    assert not panel.selected_button.isEnabled()
    panel.events.selectRow(1)
    selected_id = panel.canvas.selected_id
    panel.canvas.camera.zoom = 2

    for button, expected in (
        (panel.blue_goal_button, (0, -BACK_WALL, GOAL_HEIGHT / 2)),
        (panel.orange_goal_button, (0, BACK_WALL, GOAL_HEIGHT / 2)),
        (panel.center_button, (0, 0, 0)),
        (panel.selected_button, panel.points[1].position),
    ):
        button.click()
        assert panel.canvas.camera.target == expected
        assert panel.canvas.selected_id == selected_id
        assert panel.canvas.camera.zoom == 2
        assert panel.canvas.camera.yaw == -35
    panel.top_button.click()
    assert panel.canvas.camera.target == panel.points[1].position
    assert panel.canvas.camera.zoom == 2
    panel.reset_button.click()
    assert panel.canvas.camera == MapCamera()
    assert panel.canvas.selected_id == selected_id
    assert store.connection.total_changes == changes
    dialog.close()


def test_match_dialog_should_offer_maximize_resize_and_fullscreen_without_losing_map_state(
    application: QApplication,
    store: MatchStore,
) -> None:
    dialog = MatchDetailDialog(store, "map-match")
    dialog.resize(760, 600)
    dialog.show()
    dialog.tabs.setCurrentWidget(dialog.map_page)
    application.processEvents()
    application.processEvents()
    panel = dialog.map_panel
    assert panel is not None
    panel.events.selectRow(1)
    panel.selected_button.click()
    panel.canvas.camera.zoom = 2
    camera = replace(panel.canvas.camera)
    size = dialog.size()
    selected_id = panel.canvas.selected_id

    assert dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint
    assert dialog.isSizeGripEnabled()
    assert dialog.fullscreen_button is not None
    dialog.fullscreen_button.click()
    application.processEvents()
    assert dialog.isFullScreen()
    assert dialog.fullscreen_button.text() == "Quitter le plein écran"
    dialog.fullscreen_button.click()
    application.processEvents()

    assert not dialog.isFullScreen()
    assert dialog.isVisible()
    assert dialog.size() == size
    assert panel.canvas.camera == camera
    assert panel.canvas.selected_id == selected_id
    assert dialog.tabs.currentWidget() is dialog.map_page
    dialog.close()


def test_match_dialog_should_handle_f11_and_escape_from_the_focused_map(
    application: QApplication,
    store: MatchStore,
) -> None:
    dialog = MatchDetailDialog(store, "map-match")
    dialog.show()
    dialog.activateWindow()
    dialog.tabs.setCurrentWidget(dialog.map_page)
    application.processEvents()
    panel = dialog.map_panel
    assert panel is not None
    panel.events.selectRow(0)
    panel.canvas.setFocus()
    application.processEvents()

    QTest.keyClick(panel.canvas, Qt.Key.Key_F11)
    application.processEvents()
    assert dialog.isFullScreen()
    QTest.keyClick(panel.canvas, Qt.Key.Key_Escape)
    application.processEvents()
    assert not dialog.isFullScreen()
    assert dialog.isVisible()
    assert panel.canvas.selected_id == panel.points[0].event_id

    QTest.keyClick(panel.canvas, Qt.Key.Key_Escape)
    assert panel.canvas.selected_id is None
    assert dialog.isVisible()
    dialog.close()


def test_match_dialog_should_restore_maximized_state_after_fullscreen(
    application: QApplication,
    store: MatchStore,
) -> None:
    dialog = MatchDetailDialog(store, "map-match")
    dialog.showMaximized()
    application.processEvents()
    assert dialog.isMaximized()
    assert dialog.fullscreen_button is not None

    dialog.fullscreen_button.click()
    assert dialog.isFullScreen()
    dialog.fullscreen_button.click()
    application.processEvents()

    assert dialog.isMaximized()
    assert not dialog.isFullScreen()
    dialog.close()


def test_match_dialog_should_translate_fullscreen_and_pivot_controls_in_place(
    application: QApplication,
    store: MatchStore,
) -> None:
    manager = language_manager()
    previous = manager.language
    manager.set_language("fr")
    dialog = MatchDetailDialog(store, "map-match")
    dialog.show()
    dialog.tabs.setCurrentWidget(dialog.map_page)
    panel = dialog.map_panel
    assert panel is not None
    panel.blue_goal_button.click()
    target = panel.canvas.camera.target
    assert dialog.fullscreen_button is not None
    dialog.fullscreen_button.click()
    try:
        manager.set_language("en")
        application.processEvents()
        assert dialog.fullscreen_button.text() == "Exit fullscreen"
        assert panel.blue_goal_button.text() == "Blue goal"
        assert panel.orange_goal_button.text() == "Orange goal"
        assert panel.center_button.text() == "Center"
        assert panel.center_button.toolTip() == "Field center"
        assert panel.top_button.text() == "Top view"
        assert panel.reset_button.text() == "Reset view"
        assert panel.canvas.camera.target == target
        assert dialog.isFullScreen()
    finally:
        dialog.close()
        manager.set_language(previous)
        application.processEvents()


def test_map_toolbar_should_keep_camera_actions_on_one_left_aligned_row(
    application: QApplication,
    store: MatchStore,
) -> None:
    dialog = MatchDetailDialog(store, "map-match")
    dialog.resize(1200, 800)
    dialog.show()
    dialog.tabs.setCurrentWidget(dialog.map_page)
    application.processEvents()
    application.processEvents()
    panel = dialog.map_panel
    assert panel is not None
    dialog.resize(max(1200, panel.toolbar.sizeHint().width() + 80), 800)
    application.processEvents()
    buttons = (
        panel.center_button,
        panel.blue_goal_button,
        panel.orange_goal_button,
        panel.selected_button,
        panel.top_button,
        panel.reset_button,
    )
    origins = [button.mapTo(panel, QPoint()) for button in buttons]

    assert all(button.isVisible() for button in buttons)
    assert len({origin.y() for origin in origins}) == 1
    assert [origin.x() for origin in origins] == sorted(origin.x() for origin in origins)
    label = panel.toolbar.widgetForAction(panel.toolbar.actions()[0])
    assert label is not None and label.geometry().x() < 10
    assert origins[0].x() <= label.geometry().right() + 10
    assert len([action for action in panel.toolbar.actions() if action.isSeparator()]) == 1
    assert panel.toolbar.height() < 2 * max(button.height() for button in buttons)
    assert "Terrain standard schématique" not in [
        label.text() for label in panel.findChildren(QLabel)
    ]
    assert panel.canvas.mapTo(panel, QPoint()).y() <= panel.toolbar.geometry().bottom() + 15
    dialog.close()


def test_map_toolbar_should_keep_overflow_actions_and_selection_state_usable(
    application: QApplication,
    store: MatchStore,
) -> None:
    dialog = MatchDetailDialog(store, "map-match")
    dialog.show()
    dialog.tabs.setCurrentWidget(dialog.map_page)
    panel = dialog.map_panel
    assert panel is not None
    panel.toolbar.setFixedWidth(280)
    application.processEvents()
    application.processEvents()
    selection = panel.selected_button.defaultAction()
    top = panel.top_button.defaultAction()
    reset = panel.reset_button.defaultAction()

    assert selection is not None and not selection.isEnabled()
    assert not panel.top_button.isVisible()
    assert top is not None and reset is not None
    extension = panel.toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
    assert extension is not None and extension.isVisible()
    overflow = extension.menu()
    assert overflow is not None
    assert all(action in overflow.actions() for action in (selection, top, reset))
    top.trigger()
    assert panel.canvas.camera.elevation == 90
    panel.events.selectRow(1)
    assert selection.isEnabled()
    selection.trigger()
    assert panel.canvas.camera.target == panel.points[1].position
    reset.trigger()
    assert panel.canvas.camera == MapCamera()
    assert panel.canvas.selected_id == panel.points[1].event_id
    dialog.close()
