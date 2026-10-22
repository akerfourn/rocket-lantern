"""Refresh recognition only when the live match, account, roster or session changes."""

import sqlite3
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.live_team_table import ENCOUNTER_ROLE
from rocket_lantern.match_data import MatchSnapshot, PlayerStats
from rocket_lantern.player_encounter_controller import PlayerEncounterController
from rocket_lantern.player_encounters import EncounterScope
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult


@pytest.fixture
def store() -> Iterator[MatchStore]:
    database = MatchStore(":memory:")
    snapshot = MatchSnapshot("previous", "2026-10-04T20:00:00+00:00")
    snapshot.players = {
        "me": PlayerStats("me", "Me", 0),
        "known": PlayerStats("known", "Old nickname", 1),
    }
    database.save_details(snapshot)
    database.save(MatchResult("previous", "me", snapshot.observed_at, 11, "win"))
    yield database
    database.close()


def observe(panel: LiveMatchPanel, guid: str = "live", *extra_ids: str) -> None:
    panel.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": guid,
                "Game": {"PlaylistId": 11, "TimeSeconds": 200},
                "Players": [
                    {"PrimaryId": primary_id, "Name": primary_id, "TeamNum": 0, "Boost": 50}
                    for primary_id in ("me", "known", *extra_ids)
                ],
            },
        },
        "2026-10-04T20:10:00+00:00",
        False,
    )


def recognition(panel: LiveMatchPanel, primary_id: str) -> object:
    for row in range(panel.players.rowCount()):
        item = panel.players.item(row, 0)
        if item.data(Qt.ItemDataRole.UserRole) == primary_id:
            return item.data(ENCOUNTER_ROLE)
    raise AssertionError(f"Missing live player: {primary_id}")


def test_recognition_should_cache_roster_lookups_without_rebuilding_rows_on_telemetry(
    application: QApplication, store: MatchStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    lookup = Mock(wraps=store.player_encounters)
    monkeypatch.setattr(store, "player_encounters", lookup)
    panel = LiveMatchPanel("me")
    controller = PlayerEncounterController(store, panel, panel)
    observe(panel)
    item = panel.players.item(1, 0)

    observe(panel)
    panel.observe(
        {"Event": "ClockUpdatedSeconds", "Data": {"MatchGuid": "live", "TimeSeconds": 199}},
        "2026-10-04T20:10:01+00:00",
        False,
    )

    assert lookup.call_count == 1
    assert panel.players.item(1, 0) is item
    assert recognition(panel, "known") == EncounterScope.SESSION
    assert recognition(panel, "me") is None

    observe(panel, "live", "newcomer")
    assert lookup.call_count == 2, "A player joining must trigger one bounded lookup"
    assert recognition(panel, "newcomer") is None
    observe(panel, "next")
    assert lookup.call_count == 3
    controller.deleteLater()
    panel.close()


def test_recognition_should_follow_the_live_account_and_explicit_session_changes(
    application: QApplication, store: MatchStore
) -> None:
    panel = LiveMatchPanel("me")
    controller = PlayerEncounterController(store, panel, panel)
    observe(panel)
    assert recognition(panel, "known") == EncounterScope.SESSION

    panel.set_player("another-account")
    assert recognition(panel, "known") == EncounterScope.HISTORY
    panel.set_player("me")
    assert recognition(panel, "known") == EncounterScope.SESSION

    store.start_session("me", "2026-10-04T20:05:00+00:00")
    controller.refresh()
    assert recognition(panel, "known") == EncounterScope.HISTORY
    panel.close()


def test_recognition_should_reset_on_disconnect_without_counting_the_current_game(
    application: QApplication, store: MatchStore
) -> None:
    panel = LiveMatchPanel("me")
    controller = PlayerEncounterController(store, panel, panel)
    observe(panel, "previous")
    assert recognition(panel, "known") is None

    panel.clear("Disconnected")
    assert panel.players.rowCount() == 0
    observe(panel, "previous")
    assert recognition(panel, "known") is None

    observe(panel, "live")
    assert recognition(panel, "known") == EncounterScope.SESSION
    controller.deleteLater()
    panel.close()


def test_recognition_should_clear_stale_markers_and_report_lookup_errors_without_tick_retries(
    application: QApplication, store: MatchStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel = LiveMatchPanel("me")
    controller = PlayerEncounterController(store, panel, panel)
    failure = Mock()
    controller.failed.connect(failure)
    observe(panel)
    assert recognition(panel, "known") == EncounterScope.SESSION
    lookup = Mock(side_effect=sqlite3.OperationalError("database is locked"))
    monkeypatch.setattr(store, "player_encounters", lookup)

    controller.refresh()
    observe(panel)

    assert recognition(panel, "known") is None
    lookup.assert_called_once()
    failure.assert_called_once_with()
    panel.close()
