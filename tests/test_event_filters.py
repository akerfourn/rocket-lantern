"""Combined role/family filters share the map without altering saved occurrences."""

from collections.abc import Iterator
from dataclasses import replace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from rocket_lantern.event_data import EventParticipant, MatchEvent
from rocket_lantern.event_filters import EventFilterIndex, event_family
from rocket_lantern.i18n import language_manager
from rocket_lantern.match_data import MatchSnapshot, PlayerStats
from rocket_lantern.match_detail_dialog import MatchDetailDialog
from rocket_lantern.storage import MatchStore

TIME = "2026-10-25T19:00:00+00:00"
GUID = "filtered-match"


def participant(role: str, player: str | None) -> EventParticipant:
    name = {"me": "Nova", "mate": "Mate", "enemy": "Nova"}.get(player, "Nova")
    team = 0
    if player == "enemy":
        team = 1
    return EventParticipant(role, player, name, team, 1)


@pytest.fixture
def store() -> Iterator[MatchStore]:
    database = MatchStore(":memory:")
    snapshot = MatchSnapshot(
        GUID,
        TIME,
        playlist=11,
        players={
            "me": PlayerStats("me", "Nova", 0),
            "mate": PlayerStats("mate", "Mate", 0),
            "enemy": PlayerStats("enemy", "Nova", 1),
        },
    )
    events = (
        MatchEvent(
            "Stat:Demolish",
            TIME,
            300,
            False,
            actor="enemy",
            secondary="me",
            participants=[
                participant("actor", "enemy"),
                participant("target", "me"),
                participant("last_touch", "mate"),
            ],
        ),
        MatchEvent("Stat:Demolish", TIME, 299, False, actor="me", secondary="enemy"),
        MatchEvent(
            "GoalScored",
            TIME,
            298,
            False,
            actor="me",
            secondary="mate",
            x=0,
            y=5200,
            z=100,
            participants=[participant("scorer", "me"), participant("assister", "mate")],
        ),
        MatchEvent(
            "BallHit",
            TIME,
            297,
            False,
            actor="me",
            x=100,
            y=200,
            z=100,
            participants=[
                participant("hitter", "me"),
                participant("hitter", "mate"),
                participant("last_touch", "enemy"),
            ],
        ),
        MatchEvent(
            "CrossbarHit",
            TIME,
            296,
            False,
            actor="enemy",
            x=100,
            y=-5120,
            z=640,
            participants=[participant("last_touch", "enemy")],
        ),
        MatchEvent("PlayerState:bOnGround", TIME, 295, False, actor="mate", origin="state"),
        MatchEvent("BoostPickup", TIME, 294, False, actor="mate", x=3000, y=4000, z=70),
        MatchEvent("MatchEnded", TIME, 0, False),
        MatchEvent("FutureEvent", TIME, 0, False),
        MatchEvent("Stat:Clear", TIME, 291, False, actor="me"),
        MatchEvent(
            "GoalScored",
            TIME,
            290,
            False,
            secondary="me",
            participants=[participant("scorer", None), participant("assister", "me")],
        ),
    )
    for index, event in enumerate(events):
        event.fingerprint = f"filter-{index}"
        snapshot.events[event.fingerprint] = event
    database.save_details(snapshot)
    yield database
    database.close()


def player_id(store: MatchStore, account: str) -> int:
    return next(
        player["player_id"]
        for player in store.participants(GUID)
        if player["primary_id"] == account
    )


def index(store: MatchStore) -> EventFilterIndex:
    return EventFilterIndex(store.events(GUID), store.match_event_participants(GUID))


def ids(store: MatchStore, *positions: int) -> frozenset[int]:
    rows = store.events(GUID)
    return frozenset(rows[position]["id"] for position in positions)


def visible_rows(dialog: MatchDetailDialog) -> frozenset[int]:
    return frozenset(
        dialog.events.item(row, 1).data(Qt.ItemDataRole.UserRole)
        for row in range(dialog.events.rowCount())
        if not dialog.events.isRowHidden(row)
    )


@pytest.mark.parametrize(
    "kind, family",
    [
        ("Stat:Assist", "goals"),
        ("Stat:EpicSave", "saves_shots"),
        ("Stat:Demolish", "demolitions"),
        ("BallHit", "ball_hits"),
        ("CrossbarHit", "posts"),
        ("BoostPickup", "boost"),
        ("PlayerState:bOnWall", "states"),
        ("PlayerLeft", "presence"),
        ("GoalReplayStart", "match"),
        ("Stat:FutureStat", "statistics"),
        ("FutureEvent", "other"),
    ],
)
def test_event_family_should_classify_known_groups_and_keep_future_events(
    kind: str, family: str
) -> None:
    assert event_family(kind) == family


def test_filters_should_combine_actor_victim_and_family_by_identity(store: MatchStore) -> None:
    filters = index(store)

    assert filters.select(
        player_id(store, "enemy"), player_id(store, "me"), frozenset({"demolitions"})
    ) == ids(store, 0)
    assert (
        filters.select(player_id(store, "me"), player_id(store, "me"), frozenset({"demolitions"}))
        == frozenset()
    )
    assert filters.select(None, player_id(store, "mate"), frozenset({"goals"})) == ids(store, 2)


def test_actor_filter_should_include_every_hitter_but_not_assisters_or_last_touch_bystanders(
    store: MatchStore,
) -> None:
    filters = index(store)
    mate = player_id(store, "mate")

    assert filters.select(mate, None, frozenset({"ball_hits"})) == ids(store, 3)
    assert filters.select(mate, None, frozenset({"goals", "demolitions"})) == frozenset()
    assert filters.select(player_id(store, "enemy"), None, frozenset({"ball_hits"})) == frozenset()
    assert filters.select(player_id(store, "enemy"), None, frozenset({"posts"})) == ids(store, 4)


def test_unidentified_actor_should_not_be_linked_to_a_player_with_the_same_name(
    store: MatchStore,
) -> None:
    filters = index(store)

    assert filters.select("unidentified", None, frozenset({"goals"})) == ids(store, 10)
    assert filters.select(player_id(store, "me"), None, frozenset({"goals"})) == ids(store, 2)
    assert filters.select(None, "unidentified", frozenset({"demolitions", "goals"})) == frozenset()
    assert filters.select(None, None, frozenset(filters.families)) == ids(store, *range(11))


@pytest.fixture
def dialog(application: QApplication, store: MatchStore) -> Iterator[MatchDetailDialog]:
    manager = language_manager()
    previous = manager.language
    manager.set_language("fr")
    widget = MatchDetailDialog(store, GUID)
    widget.show()
    widget.tabs.setCurrentWidget(widget.events_page)
    application.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    manager.set_language(previous)
    application.processEvents()


def test_event_controls_should_filter_and_reset_without_reloading_or_writing_storage(
    dialog: MatchDetailDialog, store: MatchStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = [tuple(row) for row in store.events(GUID)]
    monkeypatch.setattr(store, "events", Mock(side_effect=AssertionError("Unexpected query")))
    monkeypatch.setattr(store, "set_setting", Mock(side_effect=AssertionError("Unexpected write")))
    controls = dialog.event_filters
    controls.actor.setCurrentIndex(controls.actor.findData(player_id(store, "enemy")))
    controls.target.setCurrentIndex(controls.target.findData(player_id(store, "me")))

    assert visible_rows(dialog) == frozenset({before[0][0]})
    assert dialog.event_count.text() == "1 / 11 événements"
    assert controls.reset.isEnabled()
    controls.reset.click()
    assert len(visible_rows(dialog)) == 11
    assert not controls.reset.isEnabled()
    assert [tuple(row) for row in MatchStore.events(store, GUID)] == before


def test_family_checkboxes_should_support_several_groups_and_a_clear_empty_result(
    dialog: MatchDetailDialog, store: MatchStore
) -> None:
    controls = dialog.event_filters
    controls.menu.actions()[1].trigger()
    assert visible_rows(dialog) == frozenset()
    assert not dialog.empty_events.isHidden()
    assert controls.families.text() == "Familles : Aucune"

    controls.family_actions["goals"].setChecked(True)
    controls.family_actions["demolitions"].setChecked(True)

    assert visible_rows(dialog) == ids(store, 0, 1, 2, 10)
    assert dialog.empty_events.isHidden()
    assert controls.families.text() == "Familles : 2/9"
    controls.reset.click()
    assert visible_rows(dialog) == ids(store, *range(11))


def test_family_menu_should_remain_open_for_multiple_mouse_or_keyboard_choices(
    dialog: MatchDetailDialog, application: QApplication
) -> None:
    menu = dialog.event_filters.menu
    menu.popup(
        dialog.event_filters.families.mapToGlobal(dialog.event_filters.families.rect().bottomLeft())
    )
    application.processEvents()
    action = dialog.event_filters.family_actions["states"]
    QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(action).center())
    assert not action.isChecked()
    assert menu.isVisible()
    QTest.keyClick(menu, Qt.Key.Key_Space)
    assert action.isChecked()
    assert menu.isVisible()
    menu.close()


def test_map_should_share_filters_lazily_and_preserve_colors_camera_and_surviving_selection(
    dialog: MatchDetailDialog, store: MatchStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    controls = dialog.event_filters
    dialog.events.selectRow(3)
    controls.family_actions["boost"].setChecked(False)
    assert dialog.map_panel is None
    monkeypatch.setattr(store, "events", Mock(side_effect=AssertionError("Unexpected query")))
    monkeypatch.setattr(
        store, "match_event_participants", Mock(side_effect=AssertionError("Unexpected query"))
    )
    dialog.tabs.setCurrentWidget(dialog.map_page)
    panel = dialog.map_panel
    assert panel is not None
    assert controls.parentWidget() is dialog.map_page
    assert len(panel.points) == 4
    assert len(panel.canvas.points) == 3
    assert panel.canvas.selected_id == dialog.event_rows[3]["id"]
    colors = {point.event_id: point.color for point in panel.points}
    panel.canvas.camera.zoom = 2
    panel.canvas.focus_on((100, 200, 100))
    camera = replace(panel.canvas.camera)

    controls.actor.setCurrentIndex(controls.actor.findData(player_id(store, "mate")))

    assert len(panel.canvas.points) == 1
    assert panel.canvas.points[0].kind == "BallHit"
    assert panel.canvas.points[0].color == colors[panel.canvas.selected_id]
    assert panel.canvas.camera == camera
    controls.family_actions["ball_hits"].setChecked(False)
    assert panel.canvas.selected_id is None
    assert dialog.events.selectedItems() == []
    assert "ne correspond" in panel.position.text()
    assert not panel.selected_button.isEnabled()
    controls.reset.click()
    assert len(panel.canvas.points) == 4
    assert panel.canvas.camera == camera
    dialog.tabs.setCurrentWidget(dialog.events_page)
    assert controls.parentWidget() is dialog.events_page
    assert dialog.events.item(3, 2).text() == "Nova + Mate"


def test_filters_should_translate_and_keep_choices_and_clock_format(
    dialog: MatchDetailDialog, store: MatchStore, application: QApplication
) -> None:
    controls = dialog.event_filters
    controls.actor.setCurrentIndex(controls.actor.findData(player_id(store, "enemy")))
    controls.family_actions["states"].setChecked(False)
    selected = visible_rows(dialog)
    dialog.events.selectRow(0)
    language_manager().set_language("en")
    application.processEvents()

    assert visible_rows(dialog) == selected
    assert controls.actor.currentData() == player_id(store, "enemy")
    assert "Orange" in controls.actor.currentText()
    assert controls.family_actions["states"].text() == "Player states (1)"
    assert controls.families.text() == "Families: 8/9"
    assert dialog.event_count.text() == "2 / 11 events"
    assert dialog.events.currentRow() == 0
    dialog.clock_format.setCurrentIndex(dialog.clock_format.findData("seconds"))
    assert visible_rows(dialog) == selected
    assert dialog.events.item(0, 0).text() == "300"


def test_empty_event_history_should_keep_filter_controls_usable(application: QApplication) -> None:
    store = MatchStore(":memory:")
    store.save_details(MatchSnapshot("empty", TIME))
    dialog = MatchDetailDialog(store, "empty")
    try:
        assert dialog.events.rowCount() == 0
        assert not dialog.event_filters.families.isEnabled()
        assert not dialog.event_filters.reset.isEnabled()
        dialog.tabs.setCurrentWidget(dialog.map_page)
        assert dialog.map_panel.canvas.points == ()
    finally:
        dialog.close()
        dialog.deleteLater()
        store.close()
