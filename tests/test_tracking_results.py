"""Match outcomes and participant teams stay consistent through spectating."""

import json
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from rocket_lantern.game_presence import GamePresenceMonitor
from rocket_lantern.local_player_monitor import LocalPlayerMonitor
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow


@pytest.fixture
def window(application: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    monkeypatch.setattr(GamePresenceMonitor, "start", lambda self: None)
    monkeypatch.setattr(LocalPlayerMonitor, "start", lambda self: None)
    store = MatchStore(":memory:")
    store.set_setting("player_id", "player")
    widget = MainWindow(store)
    try:
        yield widget
    finally:
        widget.close()
        store.close()


def receive_state(window: MainWindow, guid: str, team: int) -> None:
    window._receive(
        json.dumps(
            {
                "Event": "UpdateState",
                "Data": {
                    "MatchGuid": guid,
                    "Game": {
                        "PlaylistId": 6,
                        "Teams": [
                            {"TeamNum": 0, "Score": 4},
                            {"TeamNum": 1, "Score": 3},
                        ],
                    },
                    "Players": [{"PrimaryId": "player", "Name": "Player", "TeamNum": team}],
                },
            }
        )
    )


def test_result_should_match_last_playing_team_when_match_ends_while_spectating(
    window: MainWindow,
) -> None:
    receive_state(window, "private-match", 0)
    receive_state(window, "private-match", 255)
    receive_state(window, "private-match", 1)
    receive_state(window, "private-match", 255)

    window._receive(
        json.dumps(
            {
                "Event": "MatchEnded",
                "Data": {"MatchGuid": "private-match", "WinnerTeamNum": 0},
            }
        )
    )

    history = window.store.filtered_history("player", None, None)
    assert len(history) == 1
    assert history[0]["outcome"] == "loss"
    assert history[0]["team"] == 1
    assert window.store.detail("private-match")["winner"] == 0
    assert window.store.summary("player").losses == 1


def test_result_should_not_inherit_team_when_next_private_match_is_only_spectated(
    window: MainWindow,
) -> None:
    receive_state(window, "played-match", 1)
    receive_state(window, "spectated-match", 255)

    window._receive(
        json.dumps(
            {
                "Event": "MatchEnded",
                "Data": {"MatchGuid": "spectated-match", "WinnerTeamNum": 1},
            }
        )
    )

    history = window.store.filtered_history("player", None, None)
    assert len(history) == 1
    assert history[0]["match_id"] == "played-match"
    assert history[0]["outcome"] == "unknown"
    assert window.tracker.last_team is None
