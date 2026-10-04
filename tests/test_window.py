"""Offscreen GUI tests using synthetic messages and an in-memory database."""

import json
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from rl_winloose.match_data import MatchCollector
from rl_winloose.match_detail_dialog import MatchDetailDialog
from rl_winloose.storage import MatchStore
from rl_winloose.tracker import MatchResult
from rl_winloose.window import MainWindow


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    widget = MainWindow(store)
    widget.show()
    application.processEvents()
    yield widget
    widget.close()
    store.close()


def send_state(window: MainWindow, encode_data: bool = False) -> None:
    """Deliver an event through the same signal used by the Qt socket."""
    data = {
        "MatchGuid": "gui-match",
        "Players": [{"PrimaryId": "Epic|test|0", "Name": "Test", "TeamNum": 0}],
        "Game": {"PlaylistId": 11},
    }
    wire_data: object = data
    if encode_data:
        wire_data = json.dumps(data)
    window.client.message_received.emit(json.dumps({"Event": "UpdateState", "Data": wire_data}))


@pytest.mark.parametrize("encode_data", [False, True])
def test_window_should_show_saved_win_when_selected_player_wins(
    window: MainWindow,
    encode_data: bool,
) -> None:
    send_state(window, encode_data)
    window.matches.player.setCurrentIndex(1)
    send_state(window, encode_data)

    result: object = {"MatchGuid": "gui-match", "WinnerTeamNum": 0}
    if encode_data:
        result = json.dumps(result)
    window.client.message_received.emit(json.dumps({"Event": "MatchEnded", "Data": result}))

    assert window.matches.history.rowCount() == 1
    assert window.matches.history.item(0, 1).text() == "Victoire"
    assert "100.0 %" in window.matches.counters.text()
    assert "2v2 classé" in window.matches.history.item(0, 2).text()
    assert window.store.setting("player_id") == "Epic|test|0"
    assert "[Rejet]" not in window.logs.text.toPlainText()
    assert "gui-match" not in window.logs.text.toPlainText()
    assert "Epic|test|0" not in window.logs.text.toPlainText()


def test_window_should_mark_unknown_when_connection_lost_signal_arrives(window: MainWindow) -> None:
    send_state(window)
    window.matches.player.setCurrentIndex(1)
    send_state(window)

    window.client.connection_lost.emit()

    assert window.matches.history.item(0, 1).text() == "Inconnu"
    assert window.store.summary("Epic|test|0").losses == 0


def test_window_should_report_bad_message_when_json_is_invalid(window: MainWindow) -> None:
    window.client.message_received.emit("not JSON")

    assert "invalide" in window.notice.text()
    assert window.matches.history.rowCount() == 0
    assert "JSON invalide" in window.logs.text.toPlainText()
    assert window.logs.received_count == 1


def test_window_should_log_every_event_when_no_player_is_selected(window: MainWindow) -> None:
    send_state(window)
    send_state(window)
    window.client.message_received.emit(
        json.dumps({"Event": "GoalScored", "Data": {"MatchGuid": "gui-match"}})
    )

    text = window.logs.text.toPlainText()
    assert text.count('"Event":"UpdateState"') == 2
    assert '"Event":"GoalScored"' in text
    assert window.logs.received_count == 3
    assert "sélectionne ton joueur" in text
    assert "Epic|test|0" not in text
    assert '"Name":"Test"' not in text


def test_window_should_show_live_playlist_when_player_has_not_been_selected(
    window: MainWindow,
) -> None:
    send_state(window)

    assert "2v2 classé" in window.matches.session.text()
    assert window.matches.history.rowCount() == 0


def test_window_should_show_private_match_when_event_has_no_guid(window: MainWindow) -> None:
    window.client.message_received.emit(
        json.dumps({"Event": "UpdateState", "Data": {"Game": {"PlaylistId": 6}, "Players": []}})
    )

    assert "Match privé" in window.matches.session.text()
    assert "sans MatchGuid" in window.matches.observation.text()
    assert "UpdateState" in window.logs.text.toPlainText()


def test_window_should_log_rejection_when_valid_json_has_invalid_schema(window: MainWindow) -> None:
    window.client.message_received.emit('{"Event":"UpdateState","Data":null}')

    text = window.logs.text.toPlainText()
    assert '"Event":"UpdateState"' in text
    assert "[Rejet]" in text
    assert "Event et Data" in text


def test_window_should_switch_counts_when_latest_playlist_changes(window: MainWindow) -> None:
    window.store.save(MatchResult("trios", "test", "2026-01-01T18:00:00+00:00", 13, "win"))
    window.matches.refresh(window.store, "test")
    assert window.matches.history.rowCount() == 0
    window.matches.period.setCurrentIndex(1)
    assert "1 victoires" in window.matches.counters.text()

    window.matches.observe({"Event": "UpdateState", "Data": {"Game": {"PlaylistId": 11}}}, "")
    assert "0 victoires" in window.matches.counters.text()
    assert window.matches.history.rowCount() == 0
    window.matches.playlist_filter.setCurrentIndex(1)
    assert "1 victoires" in window.matches.counters.text()
    window.matches.playlist_filter.setCurrentIndex(0)
    window.matches.observe({"Event": "UpdateState", "Data": {"Game": {"PlaylistId": 13}}}, "")
    assert "1 victoires" in window.matches.counters.text()


def test_window_should_enrich_match_details_when_final_stats_arrive_after_result(
    window: MainWindow,
) -> None:
    send_state(window)
    window.matches.player.setCurrentIndex(1)
    send_state(window)
    window.client.message_received.emit(
        json.dumps(
            {
                "Event": "GoalScored",
                "Data": {
                    "MatchGuid": "gui-match",
                    "Scorer": {"PrimaryId": "Epic|test|0", "TeamNum": 0},
                    "GoalSpeed": 1500,
                    "GoalTime": 20,
                },
            }
        )
    )
    window.client.message_received.emit(
        json.dumps(
            {
                "Event": "MatchEnded",
                "Data": {
                    "MatchGuid": "gui-match",
                    "WinnerTeamNum": 0,
                },
            }
        )
    )
    window.client.message_received.emit(
        json.dumps(
            {
                "Event": "UpdateState",
                "Data": {
                    "MatchGuid": "gui-match",
                    "Players": [
                        {
                            "PrimaryId": "Epic|test|0",
                            "Name": "Test",
                            "TeamNum": 0,
                            "Goals": 2,
                            "Saves": 0,
                        }
                    ],
                    "Game": {
                        "PlaylistId": 11,
                        "bHasWinner": True,
                        "Winner": "Blue",
                        "Teams": [
                            {"Name": "Blue", "TeamNum": 0, "Score": 2},
                            {"Name": "Orange", "TeamNum": 1, "Score": 1},
                        ],
                    },
                },
            }
        )
    )

    assert window.store.summary("Epic|test|0").wins == 1
    assert window.store.participants("gui-match")[0]["goals"] == 2
    assert window.store.detail("gui-match")["final_observed"] == 1
    dialog = MatchDetailDialog(window.store, "gui-match", window)
    assert dialog.players.rowCount() == 1
    assert dialog.events.rowCount() == 1
    assert dialog.players.item(0, 3).text() == "2"
    assert dialog.players.item(0, 6).text() == "0"
    dialog.close()


@pytest.mark.parametrize("team, expected", [(0, "<b>2</b> – 1"), (1, "2 – <b>1</b>")])
def test_score_should_emphasize_selected_team_when_viewing_saved_match(
    window: MainWindow,
    team: int,
    expected: str,
) -> None:
    collector = MatchCollector()
    snapshot = collector.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "score-match",
                "Players": [{"PrimaryId": "test", "Name": "Test", "TeamNum": team}],
                "Game": {
                    "bHasWinner": True,
                    "Teams": [
                        {"TeamNum": 0, "Score": 2},
                        {"TeamNum": 1, "Score": 1},
                    ],
                },
            },
        },
        "2026-01-01T18:00:00+00:00",
    )
    assert snapshot is not None
    window.store.save_details(snapshot)
    window.store.save(MatchResult("score-match", "test", snapshot.observed_at, 11, "win"))
    window.matches.period.setCurrentIndex(1)
    window.matches.refresh(window.store, "test")

    assert expected in window.matches.history.cellWidget(0, 3).text()
    dialog = MatchDetailDialog(window.store, "score-match", window, "test")
    assert expected in dialog.score.text()
    dialog.close()
