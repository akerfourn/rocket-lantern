"""Compact boost placement, persisted preference and accessible team dots."""

import pytest
from PySide6.QtCore import QAbstractAnimation, QPoint, Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QLabel

from rocket_lantern.i18n import language_manager
from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow


def trios_message() -> dict[str, object]:
    """Provide six present players, including the tracked player and two teammates."""
    players = []
    for primary_id, team, score in (
        ("selected", 0, 600),
        ("blue-2", 0, 400),
        ("blue-3", 0, 200),
        ("orange-1", 1, 500),
        ("orange-2", 1, 300),
        ("orange-3", 1, 100),
    ):
        players.append(
            {
                "PrimaryId": primary_id,
                "Name": primary_id,
                "TeamNum": team,
                "Score": score,
                "Boost": 75,
            }
        )
    return {
        "Event": "UpdateState",
        "Data": {
            "MatchGuid": "trios",
            "Game": {
                "PlaylistId": 13,
                "Arena": "Stadium_P",
                "TimeSeconds": 123,
                "Teams": [{"TeamNum": 0, "Score": 2}, {"TeamNum": 1, "Score": 1}],
                "Ball": {"Speed": 1500, "TeamNum": 1},
            },
            "Players": players,
        },
    }


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


def test_live_header_should_keep_score_clock_and_controls_on_one_centered_row(
    application: QApplication,
) -> None:
    panel = LiveMatchPanel("selected")
    font = QFont(panel.font())
    font.setPixelSize(12)
    panel.setFont(font)
    panel.resize(1050, 440)
    panel.observe(trios_message(), "2026-10-22T19:00:00+00:00", False)
    panel.show()
    application.processEvents()

    centers = [
        widget.mapTo(panel, widget.rect().center())
        for widget in (panel.status_indicator, panel.scoreboard, panel.boost_controls)
    ]
    assert max(center.y() for center in centers) - min(center.y() for center in centers) <= 1
    assert abs(centers[1].x() - panel.rect().center().x()) <= 1
    assert centers[0].x() < centers[1].x() < centers[2].x()
    assert (
        panel.header.height()
        <= max(panel.score.height(), panel.clock.height(), panel.boost_controls.height()) + 2
    )
    assert panel.players.geometry().top() == 0
    assert panel.player_area.mapTo(panel, QPoint()).y() <= panel.header.geometry().bottom() + 10
    visible_texts = [label.text() for label in panel.findChildren(QLabel) if label.isVisible()]
    assert not any("Vitesse du ballon" in text for text in visible_texts)
    assert "Joueurs · sélection en gras" not in visible_texts
    assert panel.status_indicator.text() == ""
    assert panel.clock.text() == "2:03"
    assert panel.state.ball_speed == 1500, "Only the display changes, not the received live state"
    panel.close()


def test_default_window_should_show_both_trios_teams_without_vertical_table_scrolling(
    application: QApplication,
) -> None:
    store = MatchStore(":memory:")
    window = MainWindow(store)
    font = QFont(window.font())
    font.setPixelSize(12)
    window.setFont(font)
    window.resize(1050, 800)
    window.tabs.setCurrentWidget(window.live)
    window.live.set_player("selected")
    window.live.observe(trios_message(), "2026-10-22T19:00:00+00:00", False)
    # Headless fallback fonts can widen unrelated main-window controls.
    window.resize(max(1050, window.minimumSizeHint().width()), 800)
    window.show()
    application.processEvents()
    application.processEvents()
    table = window.live.players

    assert window.size().height() == 800
    assert table.rowCount() == 7
    assert table.item(3, 0).flags() == Qt.ItemFlag.NoItemFlags
    assert table.visualRect(table.model().index(6, 0)).bottom() < table.viewport().height()
    assert table.verticalScrollBar().maximum() == 0
    assert len(window.live.teammate_gauges) == 2
    window.close()
    store.close()


def test_live_table_should_keep_names_readable_when_stat_columns_need_horizontal_scrolling(
    application: QApplication,
) -> None:
    panel = LiveMatchPanel("selected")
    font = QFont(panel.font())
    font.setPixelSize(12)
    panel.setFont(font)
    panel.resize(1050, 440)
    message = trios_message()
    message["Data"]["Players"][0]["Name"] = "Selected Player"
    panel.observe(message, "2026-10-22T19:00:00+00:00", False)
    panel.show()
    application.processEvents()
    item = panel.players.item(0, 0)

    assert panel.players.columnWidth(0) >= QFontMetrics(item.font()).horizontalAdvance(item.text())
    assert panel.players.columnWidth(0) <= 240
    panel.close()


@pytest.mark.parametrize("language", ["fr", "en"])
def test_live_header_should_keep_overtime_compact_and_clear_its_description_on_disconnect(
    application: QApplication,
    language: str,
) -> None:
    manager = language_manager()
    previous = manager.language
    manager.set_language(language)
    panel = LiveMatchPanel("selected")
    font = QFont(panel.font())
    font.setPixelSize(12)
    panel.setFont(font)
    panel.resize(750, 700)
    message = trios_message()
    message["Data"]["Game"]["bOvertime"] = True
    panel.observe(message, "2026-10-22T19:00:00+00:00", False)
    panel.show()
    application.processEvents()
    try:
        assert panel.width() == 750
        assert panel.clock.text() == "+2:03"
        assert "+2:03" in panel.clock.toolTip()
        assert panel.clock.accessibleName() == panel.clock.toolTip()
        assert panel.scoreboard.geometry().right() < panel.boost_controls.geometry().left()

        panel.clear("Connexion interrompue · valeurs en direct effacées.")
        assert panel.clock.text() == "—:—"
        assert "+2:03" not in panel.clock.toolTip()
        assert "+2:03" not in panel.clock.accessibleName()
    finally:
        panel.close()
        manager.set_language(previous)
        application.processEvents()


def test_live_status_should_follow_the_tracked_team_without_guessing_spectator_mode(
    application: QApplication,
) -> None:
    panel = LiveMatchPanel("selected")
    status = panel.status_indicator
    assert status.view_mode == "waiting"
    panel.observe(trios_message(), "2026-10-22T19:00:00+00:00", False)
    blue_symbol = status.pixmap().toImage()
    assert status.view_mode == "blue"
    assert "Équipe bleue" in status.toolTip()
    assert "3v3 classé" in status.toolTip() and "Stadium_P" in status.toolTip()

    panel.set_player("orange-1")
    assert status.view_mode == "orange"
    assert "Équipe orange" in status.toolTip()
    assert status.pixmap().toImage() != blue_symbol

    panel.set_player("absent")
    assert status.view_mode == "overview"
    assert "Vue d’ensemble" in status.toolTip()
    assert "Équipe orange" not in status.toolTip()
    assert "Spectateur" not in status.toolTip()

    panel.clear("Connexion interrompue · valeurs en direct effacées.")
    assert status.view_mode == "waiting"
    assert "Connexion interrompue" in status.toolTip()
    assert "Stadium_P" not in status.toolTip()
    assert status.accessibleName() == status.toolTip()
    panel.close()


def test_live_status_should_translate_replay_details_without_changing_the_displayed_values(
    application: QApplication,
) -> None:
    manager = language_manager()
    previous = manager.language
    manager.set_language("fr")
    panel = LiveMatchPanel("selected")
    panel.show()
    panel.observe(trios_message(), "2026-10-22T19:00:00+00:00", False)
    panel.observe(
        {"Event": "GoalReplayStart", "Data": {"MatchGuid": "trios"}},
        "2026-10-22T19:00:01+00:00",
        False,
    )
    score = panel.score.text()
    symbol = panel.status_indicator.pixmap().toImage()
    try:
        manager.set_language("en")
        application.processEvents()
        description = panel.status_indicator.toolTip()
        assert "Goal replay" in description and "Blue team" in description
        assert "Ranked 3v3" in description
        assert panel.status_indicator.accessibleName() == description
        assert panel.status_indicator.pixmap().toImage() == symbol
        assert panel.score.text() == score and panel.clock.text() == "2:03"
        assert "tracked player is bold" in panel.players.toolTip()
    finally:
        panel.close()
        manager.set_language(previous)
        application.processEvents()
