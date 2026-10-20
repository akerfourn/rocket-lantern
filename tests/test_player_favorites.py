"""Offline bookmarks, historical player search and separation from live tracking."""

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from rocket_lantern.game_presence import GamePresenceApi, GamePresenceMonitor
from rocket_lantern.i18n import language_manager
from rocket_lantern.local_player import LocalPlayer, LocalPlayerLog
from rocket_lantern.match_data import MatchCollector
from rocket_lantern.player_favorites import PlayerFavorites
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult, Player
from rocket_lantern.window import MainWindow

OBSERVED_AT = "2026-10-20T19:00:00+00:00"


def save_match(
    store: MatchStore, guid: str = "match", name: str = "Ami", at: str = OBSERVED_AT
) -> None:
    collector = MatchCollector()
    snapshot = collector.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": guid,
                "Game": {"PlaylistId": 11},
                "Players": [
                    {"PrimaryId": "me", "Name": "Moi", "TeamNum": 0},
                    {"PrimaryId": "friend", "Name": name, "TeamNum": 0},
                    {"PrimaryId": "other", "Name": "Autre", "TeamNum": 1},
                ],
            },
        },
        at,
    )
    assert snapshot is not None
    store.save_details(snapshot)
    store.save(MatchResult(guid, "me", at, 11, "win"))


@pytest.fixture
def window(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[MainWindow]:
    clock = Mock()
    clock.now.return_value = datetime(2026, 10, 20, 19, tzinfo=UTC)
    monkeypatch.setattr("rocket_lantern.window.datetime", clock)
    store = MatchStore(":memory:")
    save_match(store)
    store.set_settings({"player_id": "me", "player_name": "Moi"})
    api = Mock(spec=GamePresenceApi)
    api.game_process_ids.return_value = frozenset()
    api.foreground_window.return_value = 0
    presence = GamePresenceMonitor(application, api)
    widget = MainWindow(store, presence, LocalPlayerLog(tmp_path / "missing.log"))
    presence.timer.stop()
    widget.local_player_monitor.timer.stop()
    widget.tracker.players = [
        Player("me", "Moi", 0),
        Player("friend", "Ami", 0),
        Player("other", "Autre", 1),
    ]
    widget._update_players(force=True)
    widget.show()
    yield widget
    widget.close()
    store.close()
    language_manager().set_language("fr")


def test_known_players_should_include_teammates_and_opponents_using_latest_saved_names() -> None:
    store = MatchStore(":memory:")
    try:
        save_match(store, "new", "Æther", "2026-10-20T20:00:00+00:00")
        save_match(store, "old", "Ancien", "2026-10-20T18:00:00+00:00")

        known = {row["primary_id"]: row["name"] for row in store.known_players()}

        assert known == {"me": "Moi", "friend": "Æther", "other": "Autre"}
        assert store.history("friend") == [], "Known participants need not have tracked results"
    finally:
        store.close()


def test_star_should_toggle_selected_player_and_keep_favorites_first_without_duplicates(
    window: MainWindow,
) -> None:
    selector = window.matches.player
    selector.setCurrentIndex(selector.findData("friend"))
    button = window.matches.favorite_player
    assert not button.isChecked()
    assert button.toolTip() == "Ajouter Ami aux favoris"

    QTest.mouseClick(button, Qt.MouseButton.LeftButton)

    assert button.isChecked()
    assert button.toolTip() == "Retirer Ami des favoris"
    assert selector.itemData(1) == "friend"
    assert not selector.itemIcon(1).isNull()
    assert json.loads(window.store.setting("favorite_players")) == {"friend": "Ami"}
    assert [selector.itemData(index) for index in range(selector.count())].count("friend") == 1
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert not button.isChecked()
    assert window.player_favorites.favorites == {}
    assert selector.currentData() == "friend", "Removing a bookmark must not change selection"
    selector.setCurrentIndex(0)
    assert not button.isEnabled()


def test_offline_selection_should_not_replace_tracked_account_or_live_player(
    window: MainWindow,
) -> None:
    tracked = window.tracker.player_id
    live = window.live.player_id
    window.matches.player.setCurrentIndex(window.matches.player.findData("friend"))

    assert window.matches._player_id == "friend"
    assert window.tracker.player_id == tracked == "me"
    assert window.live.player_id == live == "me"
    assert window.store.setting("player_id") == "me"
    assert window.store.setting("history_player_id") == "friend"


def test_game_close_should_preserve_history_selection_and_favorites(window: MainWindow) -> None:
    window._local_player_changed(LocalPlayer("me", "Moi"))
    window.matches.player.setCurrentIndex(window.matches.player.findData("friend"))
    window.matches.favorite_player.click()

    window._local_player_changed(None)

    assert window.matches.player.currentData() == "friend"
    assert window.matches._player_id == "friend"
    assert window.matches.favorite_player.isChecked()
    assert window.tracker.player_id == ""
    assert window.live.player_id == ""
    assert window.store.setting("player_id") == "me"
    window.matches.player.setCurrentIndex(window.matches.player.findData("me"))
    assert window.tracker.player_id == "", "Browsing offline must not reactivate tracking"


def test_favorite_history_selection_should_not_change_detected_account_or_boost_team(
    window: MainWindow,
) -> None:
    window._local_player_changed(LocalPlayer("me", "Moi"))
    window.player_favorites.set_favorite("other", "Autre", True)

    window.matches.player.setCurrentIndex(window.matches.player.findData("other"))

    assert window.matches._player_id == "other"
    assert window.tracker.player_id == "me"
    assert window.live.player_id == "me"
    assert window.store.setting("player_id") == "me"
    window._local_player_changed(LocalPlayer("Epic|new|0", "Second compte"))
    assert window.tracker.player_id == "Epic|new|0"
    assert window.matches.player.currentData() == "Epic|new|0"
    assert window.matches.player.findData("other") >= 0
    assert "other" in window.player_favorites.favorites


def test_settings_should_search_match_participants_and_sync_stars_without_tracking_them(
    window: MainWindow,
) -> None:
    window.settings.manage_players.click()
    dialog = window.favorite_players_dialog
    assert dialog.isVisible()
    assert set(dialog.stars) == {"me", "friend", "other"}
    dialog.search.setText("AMI")
    visible = [
        dialog.players.item(row, 1).text()
        for row in range(dialog.players.rowCount())
        if not dialog.players.isRowHidden(row)
    ]
    assert visible == ["Ami"]

    dialog.stars["friend"].click()

    assert window.matches.player.itemData(1) == "friend"
    assert window.matches.player.currentData() == "me"
    assert window.tracker.player_id == "me"
    assert window.store.setting("player_id") == "me"
    assert "friend" in window.player_favorites.favorites
    dialog.search.setText("absent")
    assert not dialog.empty.isHidden()
    dialog.search.setText("friend")
    assert dialog.empty.isHidden(), "Search must also match the stable account identifier"
    dialog.close_button.click()
    assert not dialog.isVisible()


def test_selector_should_keep_old_nonfavorite_players_in_settings_not_clutter_the_dropdown(
    window: MainWindow,
) -> None:
    window.tracker.players = []
    window._update_players(force=True)
    assert window.matches.player.findData("friend") == -1
    window.favorite_players_dialog.open()

    window.favorite_players_dialog.stars["friend"].click()

    assert window.matches.player.findData("friend") == 1
    assert window.matches.player.currentData() == "me"


def test_favorites_and_last_history_selection_should_survive_restart(
    application: QApplication, tmp_path: Path
) -> None:
    path = tmp_path / "favorites.sqlite3"
    store = MatchStore(path)
    save_match(store)
    first = MainWindow(store)
    first.player_favorites.set_favorite("friend", "Ami", True)
    first.matches.player.setCurrentIndex(first.matches.player.findData("friend"))
    first.close()
    store.close()
    reopened_store = MatchStore(path)
    reopened = MainWindow(reopened_store)
    try:
        assert reopened.matches.player.currentData() == "friend"
        assert reopened.matches.player.itemData(1) == "friend"
        assert reopened.matches.favorite_player.isChecked()
        assert reopened.player_favorites.favorites == {"friend": "Ami"}
    finally:
        reopened.close()
        reopened_store.close()


def test_star_should_roll_back_when_database_write_fails(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.matches.player.setCurrentIndex(window.matches.player.findData("friend"))
    failed = Mock()
    monkeypatch.setattr(window, "_storage_error", failed)
    monkeypatch.setattr(
        window.store, "set_setting", Mock(side_effect=sqlite3.OperationalError("full"))
    )

    window.matches.favorite_player.click()

    assert not window.matches.favorite_player.isChecked()
    assert window.player_favorites.favorites == {}
    failed.assert_called_once_with()


def test_settings_stars_should_roll_back_when_database_write_fails(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog = window.favorite_players_dialog
    dialog.open()
    monkeypatch.setattr(
        window.store, "set_setting", Mock(side_effect=sqlite3.OperationalError("full"))
    )

    dialog.stars["friend"].click()

    assert not dialog.stars["friend"].isChecked()
    assert window.player_favorites.favorites == {}
    assert dialog.status.text() == "Impossible d’enregistrer les favoris."


@pytest.mark.parametrize("saved", ["invalid", "[]", '{"friend":4}', '{"":"name"}'])
def test_invalid_favorites_should_not_prevent_history_access_or_be_silently_overwritten(
    saved: str,
) -> None:
    store = MatchStore(":memory:")
    store.set_setting("favorite_players", saved)
    try:
        favorites = PlayerFavorites(store)
        assert favorites.favorites == {}
        assert store.setting("favorite_players") == saved
    finally:
        store.close()


def test_search_and_live_updates_should_not_reload_saved_match_players_repeatedly(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = Mock(side_effect=AssertionError("The directory is cached, not read per key or packet"))
    monkeypatch.setattr(window.store, "known_players", reader)
    window.favorite_players_dialog.open()
    window.favorite_players_dialog.search.setText("A")
    window.favorite_players_dialog.search.setText("AM")
    window._update_players(force=True)
    reader.assert_not_called()


def test_favorite_buttons_and_search_should_translate_without_changing_player_names(
    window: MainWindow, application: QApplication
) -> None:
    window.matches.player.setCurrentIndex(window.matches.player.findData("friend"))
    window.matches.favorite_player.click()
    window.favorite_players_dialog.open()

    language_manager().set_language("en")
    application.processEvents()

    assert window.matches.favorite_player.toolTip() == "Remove Ami from favorites"
    assert window.matches.favorite_player.accessibleName() == "Remove Ami from favorites"
    assert window.settings.manage_players.text() == "Manage favorite players…"
    assert window.favorite_players_dialog.windowTitle() == "Favorite players"
    assert window.favorite_players_dialog.search.placeholderText() == "Search players…"
    assert window.favorite_players_dialog.stars["friend"].toolTip() == "Remove Ami from favorites"
    assert window.matches.player.currentText() == "Ami"
    assert window.matches.favorite_player.isChecked()
