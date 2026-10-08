"""Compact boost placement, persisted preference and accessible team dots."""

import pytest
from PySide6.QtCore import QAbstractAnimation, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow


@pytest.mark.parametrize("side", ["left", "right"])
def test_panel_should_place_compact_boosts_next_to_table_when_wide_and_above_when_narrow(
    application: QApplication, side: str
) -> None:
    panel = LiveMatchPanel("", side)
    font = QFont(panel.font())
    font.setPixelSize(12)
    panel.setFont(font)
    panel.resize(1100, 700)
    panel.show()
    application.processEvents()

    assert panel.boost_dock.width() == 240
    assert panel.boost.height() == 22
    assert panel.selected_boost.name.height() >= panel.selected_boost.name.fontMetrics().height()
    assert panel.boost_dock.geometry().top() == panel.player_area.geometry().top()
    if side == "left":
        assert panel.boost_dock.geometry().right() < panel.player_area.geometry().left()
    else:
        assert panel.boost_dock.geometry().left() > panel.player_area.geometry().right()

    panel.resize(750, 700)
    application.processEvents()
    assert panel.width() == 750
    assert panel.boost_dock.geometry().bottom() < panel.player_area.geometry().top()
    assert panel.boost_dock.width() == 240
    if side == "left":
        assert panel.boost_dock.geometry().left() == panel.player_area.geometry().left()
    else:
        assert panel.boost_dock.geometry().right() == panel.player_area.geometry().right()
    assert panel.boost.geometry().bottom() < panel.selected_boost.height()
    assert panel.selected_boost.name.height() >= panel.selected_boost.name.fontMetrics().height()
    assert panel.boost_dock.height() >= panel.boost_dock.minimumSizeHint().height()
    panel.close()


def test_window_should_restore_boost_side_and_save_only_explicit_side_changes(
    application: QApplication,
) -> None:
    store = MatchStore(":memory:")
    store.set_setting("boost_side", "right")
    window = MainWindow(store)
    previous_changes = store.connection.total_changes

    assert window.live.boost_side.currentData() == "right"
    window.live.resize(1100, 700)
    assert store.connection.total_changes == previous_changes
    window.live.boost_side.setCurrentIndex(window.live.boost_side.findData("left"))
    assert store.setting("boost_side") == "left"
    window.close()
    reopened = MainWindow(store)
    assert reopened.live.boost_side.currentData() == "left"
    reopened.close()
    store.close()


def test_panel_should_replace_team_names_with_dots_and_stop_alert_when_view_is_hidden(
    application: QApplication,
) -> None:
    panel = LiveMatchPanel("selected")
    panel.show()
    panel.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "live",
                "Game": {
                    "Teams": [
                        {"TeamNum": 0, "Score": 2},
                        {"TeamNum": 1, "Score": 1},
                    ]
                },
                "Players": [
                    {"PrimaryId": "selected", "Name": "Moi", "TeamNum": 0, "Boost": 50},
                    {"PrimaryId": "mate", "Name": "Mate", "TeamNum": 0, "Boost": 0},
                    {"PrimaryId": "opponent", "Name": "Other", "TeamNum": 1},
                ],
            },
        },
        "2026-10-08T19:00:00+00:00",
        False,
    )
    application.processEvents()

    assert panel.score.text().count("●") == 2
    assert "Bleus" not in panel.score.text()
    assert "Oranges" not in panel.score.text()
    assert "<u>2</u>" in panel.score.text()
    assert panel.score.accessibleName() == "Équipe bleue 2 ; équipe orange 1"
    teams = {
        panel.players.item(row, 0).data(Qt.ItemDataRole.UserRole): panel.players.item(row, 1)
        for row in range(panel.players.rowCount())
    }
    assert teams["selected"].text() == "●"
    assert teams["selected"].toolTip() == "Équipe bleue"
    assert teams["opponent"].toolTip() == "Équipe orange"
    assert teams["opponent"].data(Qt.ItemDataRole.AccessibleTextRole) == "Équipe orange"
    assert teams["selected"].foreground().color() != teams["opponent"].foreground().color()
    animation = panel.teammate_gauges["mate"].bar.animation
    assert animation.state() == QAbstractAnimation.State.Running
    panel.hide()
    assert animation.state() == QAbstractAnimation.State.Stopped
    panel.close()
