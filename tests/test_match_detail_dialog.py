"""Match sheets display every observed player and highlight identity, not name."""

from collections.abc import Iterator
from sqlite3 import OperationalError
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from rocket_lantern.event_data import MatchEvent
from rocket_lantern.i18n import language_manager
from rocket_lantern.match_data import MatchSnapshot, PlayerStats
from rocket_lantern.match_detail_dialog import MatchDetailDialog
from rocket_lantern.storage import MatchStore


@pytest.fixture
def store() -> Iterator[MatchStore]:
    database = MatchStore(":memory:")
    database.save_details(
        MatchSnapshot(
            guid="detail-test",
            observed_at="2026-10-04T12:00:00+00:00",
            blue_score=2,
            orange_score=1,
            players={
                "blue": PlayerStats("blue", "Same name", 0, goals=2, saves=0),
                "orange": PlayerStats("orange", "Same name", 1, goals=1, car_touches=3),
            },
        )
    )
    yield database
    database.close()


def save_clock_events(store: MatchStore) -> None:
    """Save clocks with boundary, overtime, missing and fractional duration values."""
    snapshot = MatchSnapshot("detail-test", "2026-10-04T12:00:00+00:00")
    for index, (seconds, overtime) in enumerate(
        ((125, False), (0, False), (65, True), (None, False))
    ):
        event = MatchEvent(
            "BallHit",
            snapshot.observed_at,
            seconds,
            overtime,
            round_seconds=12.5,
            fingerprint=f"clock-{index}",
        )
        snapshot.events[event.fingerprint] = event
    store.save_details(snapshot)


def test_event_clock_should_default_to_minutes_and_preserve_missing_and_overtime(
    application: QApplication,
    store: MatchStore,
) -> None:
    save_clock_events(store)
    dialog = MatchDetailDialog(store, "detail-test")

    assert dialog.clock_format.currentData() == "minutes_seconds"
    assert dialog.events.horizontalHeaderItem(0).text() == "Horloge (min:s)"
    assert [dialog.events.item(row, 0).text() for row in range(4)] == [
        "2:05",
        "0:00",
        "Prolongation 1:05",
        "—",
    ]
    assert dialog.events.item(0, 6).text() == "12.5"
    assert store.setting("event_clock_format") == ""
    dialog.close()


def test_event_clock_should_toggle_in_place_remember_choice_and_preserve_saved_times(
    application: QApplication,
    store: MatchStore,
) -> None:
    save_clock_events(store)
    before = [tuple(row) for row in store.events("detail-test")]
    dialog = MatchDetailDialog(store, "detail-test")
    table = dialog.events
    dialog.events.selectRow(2)
    dialog.clock_format.setCurrentIndex(dialog.clock_format.findData("seconds"))

    assert dialog.events is table
    assert dialog.events.currentRow() == 2
    assert dialog.events.horizontalHeaderItem(0).text() == "Horloge (s)"
    assert [dialog.events.item(row, 0).text() for row in range(4)] == [
        "125",
        "0",
        "Prolongation 65",
        "—",
    ]
    assert store.setting("event_clock_format") == "seconds"
    assert [tuple(row) for row in store.events("detail-test")] == before
    dialog.close()

    reopened = MatchDetailDialog(store, "detail-test")
    assert reopened.clock_format.currentData() == "seconds"
    assert reopened.events.item(0, 0).text() == "125"
    reopened.clock_format.setCurrentIndex(reopened.clock_format.findData("minutes_seconds"))
    assert reopened.events.item(0, 0).text() == "2:05"
    assert store.setting("event_clock_format") == "minutes_seconds"
    reopened.close()


@pytest.mark.parametrize("saved", ["", "invalid"])
def test_event_clock_should_use_minutes_when_preference_is_missing_or_invalid(
    application: QApplication,
    store: MatchStore,
    saved: str,
) -> None:
    store.set_setting("event_clock_format", saved)
    dialog = MatchDetailDialog(store, "detail-test")

    assert dialog.clock_format.currentData() == "minutes_seconds"
    assert dialog.events.rowCount() == 0
    dialog.clock_format.setCurrentIndex(dialog.clock_format.findData("seconds"))
    assert dialog.events.horizontalHeaderItem(0).text() == "Horloge (s)"
    dialog.close()


def test_event_clock_should_translate_in_place_without_changing_format_or_selection(
    application: QApplication,
    store: MatchStore,
) -> None:
    save_clock_events(store)
    manager = language_manager()
    previous_language = manager.language
    manager.set_language("fr")
    dialog = MatchDetailDialog(store, "detail-test")
    dialog.show()
    dialog.tabs.setCurrentIndex(1)
    try:
        manager.set_language("en")
        application.processEvents()

        assert dialog.clock_format.currentText() == "Minutes:seconds"
        assert dialog.clock_format.itemText(1) == "Seconds"
        assert dialog.events.horizontalHeaderItem(0).text() == "Clock (min:s)"
        assert dialog.events.item(2, 0).text() == "Overtime 1:05"
        assert dialog.tabs.currentIndex() == 1
        dialog.clock_format.setCurrentIndex(1)
        assert dialog.events.item(2, 0).text() == "Overtime 65"

        manager.set_language("fr")
        application.processEvents()
        assert dialog.clock_format.currentText() == "Secondes"
        assert dialog.events.horizontalHeaderItem(0).text() == "Horloge (s)"
        assert dialog.events.item(2, 0).text() == "Prolongation 65"
    finally:
        dialog.close()
        manager.set_language(previous_language)
        application.processEvents()


def test_event_clock_should_keep_display_usable_when_saving_preference_fails(
    application: QApplication,
    store: MatchStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_clock_events(store)
    dialog = MatchDetailDialog(store, "detail-test")
    with monkeypatch.context() as patch:
        patch.setattr(store, "set_setting", Mock(side_effect=OperationalError("locked")))
        dialog.clock_format.setCurrentIndex(dialog.clock_format.findData("seconds"))

    assert dialog.events.item(0, 0).text() == "125"
    assert "Impossible d’enregistrer" in dialog.clock_format.toolTip()
    assert store.setting("event_clock_format") == ""
    dialog.clock_format.setCurrentIndex(dialog.clock_format.findData("minutes_seconds"))
    assert dialog.clock_format.toolTip() == ""
    assert store.setting("event_clock_format") == "minutes_seconds"
    dialog.close()


@pytest.mark.parametrize("player_id", ["blue", "orange"])
def test_match_dialog_should_highlight_only_selected_identity_when_names_are_identical(
    application: QApplication,
    store: MatchStore,
    player_id: str,
) -> None:
    dialog = MatchDetailDialog(store, "detail-test", player_id=player_id)

    assert dialog.players.rowCount() == 2
    assert dialog.players.item(0, 3).text() == "2"
    assert dialog.players.item(0, 6).text() == "0"
    assert dialog.players.item(1, 9).text() == "3"
    assert dialog.tabs.tabText(0) == "Joueurs (2)"
    assert dialog.tabs.tabText(2) == "Carte 3D"
    assert dialog.tabs.tabText(3) == "Informations"
    for row in range(dialog.players.rowCount()):
        name = dialog.players.item(row, 0)
        is_selected = name.data(Qt.ItemDataRole.UserRole) == player_id
        assert ("(sélectionné)" in name.text()) == is_selected
        for column in range(dialog.players.columnCount()):
            item = dialog.players.item(row, column)
            assert item.font().bold() == is_selected
            if is_selected:
                assert item.background() == dialog.players.palette().highlight()
                assert item.foreground() == dialog.players.palette().highlightedText()
            else:
                assert item.background().style() == Qt.BrushStyle.NoBrush
    dialog.close()


def test_match_dialog_should_leave_players_unmarked_when_selected_identity_is_absent(
    application: QApplication,
    store: MatchStore,
) -> None:
    dialog = MatchDetailDialog(store, "detail-test", player_id="absent")

    assert "non présent" in dialog.player_hint.text()
    assert "<u>" not in dialog.score.text()
    for row in range(dialog.players.rowCount()):
        assert "(sélectionné)" not in dialog.players.item(row, 0).text()
        assert not dialog.players.item(row, 0).font().bold()
    dialog.close()
