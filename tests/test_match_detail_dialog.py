"""Match sheets display every observed player and highlight identity, not name."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

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
    assert dialog.tabs.tabText(2) == "Informations"
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
