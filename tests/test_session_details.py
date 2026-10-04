"""Session dialogs preserve missing values and isolate player/session data."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from rl_winloose.match_data import MatchCollector
from rl_winloose.match_detail_dialog import MatchDetailDialog
from rl_winloose.match_panel import MatchPanel
from rl_winloose.session_detail_dialog import SessionDetailDialog
from rl_winloose.storage import MatchStore
from rl_winloose.tracker import MatchResult


@pytest.fixture
def store() -> Iterator[MatchStore]:
    database = MatchStore(":memory:")
    database.save(MatchResult("detailed", "test", "2026-10-04T12:00:00+00:00", 11, "win"))
    database.save(MatchResult("legacy", "test", "2026-10-04T12:10:00+00:00", 13, "loss"))
    database.save(MatchResult("detailed", "other", "2026-10-04T12:00:00+00:00", 11, "loss"))
    collector = MatchCollector()
    snapshot = collector.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "detailed",
                "Players": [
                    {"PrimaryId": "test", "Name": "Test", "TeamNum": 0, "Goals": 0},
                    {"PrimaryId": "other", "Name": "Other", "TeamNum": 1, "Goals": 7},
                ],
                "Game": {
                    "Arena": "TestArena",
                    "PlaylistId": 11,
                    "bOvertime": False,
                    "bHasWinner": True,
                    "Teams": [{"TeamNum": 0, "Score": 2}, {"TeamNum": 1, "Score": 1}],
                },
            },
        },
        "2026-10-04T12:00:00+00:00",
    )
    assert snapshot is not None
    database.save_details(snapshot)
    yield database
    database.close()


def test_session_dialog_should_show_metadata_and_missing_stats_when_details_are_partial(
    application: QApplication,
    store: MatchStore,
) -> None:
    session_id = store.sessions("test")[0]["id"]
    dialog = SessionDetailDialog(store, "test", session_id)
    dialog.show()
    application.processEvents()

    assert "2 matchs" in dialog.metadata.text()
    assert "1 victoires" in dialog.metadata.text()
    assert dialog.matches.rowCount() == 2
    assert dialog.matches.item(0, 3).text() == "TestArena"
    assert dialog.matches.item(0, 4).text() == "2 – 1"
    assert dialog.matches.item(0, 5).text() == "Non"
    assert dialog.matches.item(1, 6).text() == "Détails indisponibles"
    assert dialog.stats.item(0, 2).text() == "0"
    assert dialog.stats.item(0, 3).text() == "—"
    assert dialog.stats.item(1, 2).text() == "—"
    dialog.matches.cellDoubleClicked.emit(0, 0)
    child = dialog.findChild(MatchDetailDialog)
    assert child is not None
    assert child.players.rowCount() == 2
    child.close()
    dialog.close()


def test_session_dialog_should_show_empty_state_when_session_has_no_matches(
    application: QApplication,
    store: MatchStore,
) -> None:
    session_id = store.start_session("test", "2026-10-04T12:20:00+00:00")
    dialog = SessionDetailDialog(store, "test", session_id)

    assert "aucun match" in dialog.hint.text()
    assert dialog.matches.rowCount() == 0
    assert "0 matchs" in dialog.metadata.text()
    assert store.session_detail("other", session_id) is None
    assert store.session_matches("other", session_id) == []
    dialog.close()


def test_panel_should_open_full_session_when_user_activates_period(
    application: QApplication,
    store: MatchStore,
) -> None:
    panel = MatchPanel("test", "Test")
    panel.refresh(store, "test")
    session_id = store.sessions("test")[0]["id"]
    index = panel.period.findData(session_id)
    panel.period.setCurrentIndex(index)
    assert panel.findChild(SessionDetailDialog) is None, "Refresh must not open dialogs"
    assert panel.history.rowCount() == 1, "Main view still filters to the latest playlist"

    panel.period.activated.emit(index)

    dialog = panel.findChild(SessionDetailDialog)
    assert dialog is not None
    assert dialog.matches.rowCount() == 2, "Session detail includes every playlist"
    assert panel.session_details.isEnabled()
    dialog.close()
    panel.period.setCurrentIndex(panel.period.findData("all"))
    assert not panel.session_details.isEnabled()
    panel.close()
