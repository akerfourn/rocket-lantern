"""Language changes update existing widgets without touching game state."""

import ast
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock
from xml.etree import ElementTree

import pytest
from PySide6.QtCore import QTranslator
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLabel

from rocket_lantern.i18n import TRANSLATION_DIRECTORY, DateText, language_manager, text
from rocket_lantern.live_match import PHASE_EVENTS
from rocket_lantern.live_team_table import LIVE_STAT_LABELS
from rocket_lantern.match_data import MatchCollector
from rocket_lantern.match_detail_dialog import MatchDetailDialog
from rocket_lantern.playlists import PLAYLIST_NAMES
from rocket_lantern.session_detail_dialog import SessionDetailDialog
from rocket_lantern.statistics import STAT_LABELS
from rocket_lantern.storage import MatchStore, Summary
from rocket_lantern.tracker import MatchResult
from rocket_lantern.translated_widgets import TranslatedLabel
from rocket_lantern.window import MainWindow


@pytest.fixture
def localized_window(application: QApplication) -> Iterator[MainWindow]:
    manager = language_manager()
    manager.set_language("fr")
    database = MatchStore(":memory:")
    database.set_setting("player_id", "test")
    database.set_setting("player_name", "Victoire")
    window = MainWindow(database)
    window.show()
    application.processEvents()
    yield window
    window.close()
    window.deleteLater()
    database.close()
    manager.set_language("fr")
    application.processEvents()


def test_settings_should_translate_in_place_without_changing_startup_preference(
    localized_window: MainWindow, application: QApplication
) -> None:
    window = localized_window
    window.settings_button.click()
    window.settings.default_tab.setCurrentIndex(1)
    window.language.setCurrentIndex(window.language.findData("en"))
    application.processEvents()
    assert window.settings_button.text() == "Settings"
    assert window.settings.windowTitle() == "Settings"
    assert window.settings.close_button.text() == "Close"
    assert window.settings.default_tab.currentText() == "Live match"
    assert window.store.setting("default_tab") == "live"
    assert window.settings.isVisible()


def switch_to_english(window: MainWindow, application: QApplication) -> None:
    window.language.setCurrentIndex(window.language.findData("en"))
    application.processEvents()


def test_language_should_update_labels_without_reconnecting_or_resetting_filters(
    localized_window: MainWindow, application: QApplication
) -> None:
    window = localized_window
    window.matches.period.setCurrentIndex(window.matches.period.findData("all"))
    window.matches.playlist_filter.setCurrentIndex(window.matches.playlist_filter.findData("all"))
    window.tabs.setCurrentIndex(1)
    window.matches.counters.set_summary(Summary(3, 1, 2))
    window.client._status(text("Connecté • événements reçus"))
    window.client.start = Mock()
    window._refresh = Mock()
    window.logs.append_entry("Test", "Historical entry")
    history = window.logs.text.toPlainText()

    switch_to_english(window, application)

    assert window.tabs.tabText(0) == "Matches"
    assert window.tabs.tabText(1) == "Live match"
    assert window.logs.api_details.text() == "API details"
    assert "Disabled at startup" in window.logs.api_details.toolTip()
    assert window.status.text() == "Connected • receiving events"
    assert window.matches.counters.wins.text() == "3 wins"
    assert window.matches.counters.rate.text() == "75.0 % win rate"
    assert window.matches.counters.accessibleName() == window.matches.counters.text()
    assert window.matches.period.currentText() == "Full history"
    assert window.matches.playlist_filter.currentText() == "All game modes"
    assert window.matches.player.currentText() == "Victoire", "Player data must not be translated"
    assert window.tabs.currentIndex() == 1
    assert window.store.setting("language") == "en"
    assert window.logs.text.toPlainText() == history
    window.client.start.assert_not_called()
    window._refresh.assert_not_called()

    window.language.setCurrentIndex(window.language.findData("fr"))
    application.processEvents()
    assert window.matches.counters.rate.text() == "75,0 % de victoires"
    assert window.status.text() == "Connecté • événements reçus"


def test_language_should_update_live_boosts_without_replacing_gauges(
    localized_window: MainWindow, application: QApplication
) -> None:
    window = localized_window
    window._receive(
        json.dumps(
            {
                "Event": "UpdateState",
                "Data": {
                    "MatchGuid": "live",
                    "Game": {"PlaylistId": 11},
                    "Players": [
                        {"PrimaryId": "test", "Name": "Victoire", "TeamNum": 0, "Boost": 25},
                        {"PrimaryId": "mate", "Name": "Défaite", "TeamNum": 0, "Boost": 0},
                    ],
                },
            }
        )
    )
    gauge = window.live.teammate_gauges["mate"]
    snapshot = window.live.state.snapshot
    switch_to_english(window, application)

    assert window.live.teammate_gauges["mate"] is gauge
    assert window.live.state.snapshot is snapshot
    assert gauge.amount.text() == "0 % · empty"
    assert gauge.name.text() == "Défaite"
    assert gauge.bar.maximum() == 0
    assert window.live.selected_boost.name.text() == "Victoire · selected"
    assert "In progress" in window.live.status_indicator.toolTip()
    assert "Ranked 2v2" in window.live.status_indicator.toolTip()
    assert "Blue team" in window.live.status_indicator.toolTip()
    assert window.live.status_indicator.accessibleName() == window.live.status_indicator.toolTip()
    assert window.live.players.horizontalHeaderItem(1).text() == ""
    assert not window.live.players.horizontalHeaderItem(1).icon().isNull()
    assert window.live.players.horizontalHeaderItem(1).toolTip() == "Points"
    assert window.live.players.item(0, 0).text() == "Blue team"


def test_language_should_update_open_match_and_session_details_in_place(
    localized_window: MainWindow, application: QApplication
) -> None:
    window = localized_window
    window.store.save(MatchResult("saved", "test", "2026-10-04T12:00:00+00:00", 11, "win"))
    snapshot = MatchCollector().observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "saved",
                "Game": {"PlaylistId": 11, "bOvertime": False},
                "Players": [{"PrimaryId": "test", "Name": "Victoire", "TeamNum": 0}],
            },
        },
        "2026-10-04T12:00:00+00:00",
    )
    assert snapshot is not None
    window.store.save_details(snapshot)
    session_id = window.store.sessions("test")[0]["id"]
    match = MatchDetailDialog(window.store, "saved", window, "test")
    session = SessionDetailDialog(window.store, "test", session_id, window)
    match.show()
    session.show()
    match.tabs.setCurrentIndex(2)
    session.tabs.setCurrentIndex(1)
    saved_rows = session.rows

    switch_to_english(window, application)

    assert match.windowTitle() == "Match details"
    assert match.tabs.tabText(0) == "Players (1)"
    assert match.players.item(0, 0).text() == "Victoire (selected)"
    assert match.players.horizontalHeaderItem(1).text() == "Team"
    assert match.tabs.currentIndex() == 2
    assert "Orange" in match.score.text()
    assert session.windowTitle() == f"Session #{session_id} details"
    assert session.tabs.currentIndex() == 1
    assert session.rows is saved_rows
    assert session.matches.item(0, 1).text() == "Win"
    assert session.matches.item(0, 5).text() == "No"
    assert "10/4/2026" in session.matches.item(0, 0).text()
    assert "Game mode" in [label.text() for label in match.findChildren(QLabel)]
    for dialog in (match, session):
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons.button(QDialogButtonBox.StandardButton.Close).text() == "Close"
        dialog.close()


def test_language_should_restore_saved_preference_when_window_is_created(
    localized_window: MainWindow, application: QApplication
) -> None:
    database = MatchStore(":memory:")
    database.set_setting("language", "en")
    window = MainWindow(database)
    application.processEvents()
    assert window.language.currentData() == "en"
    assert window.tabs.tabText(0) == "Matches"
    window.close()
    window.deleteLater()
    database.close()


def test_translation_should_preserve_literal_player_names_and_format_dates(
    localized_window: MainWindow, application: QApplication
) -> None:
    literal = TranslatedLabel("Victoire")
    translated = TranslatedLabel(text("{name} (sélectionné)", name="{losses} Défaite"))
    date = TranslatedLabel(DateText(datetime(2026, 10, 4, 12, tzinfo=UTC)))
    literal.show()
    translated.show()
    date.show()
    switch_to_english(localized_window, application)
    assert literal.text() == "Victoire"
    assert translated.text() == "{losses} Défaite (selected)"
    assert date.text().startswith("10/4/2026")
    for label in (literal, translated, date):
        label.close()


def test_catalogs_should_cover_all_explicit_application_texts() -> None:
    source_directory = Path(__file__).parents[1] / "src/rocket_lantern"
    sources = set()
    sources.update(PLAYLIST_NAMES.values())
    sources.update(STAT_LABELS.values())
    sources.update(LIVE_STAT_LABELS.values())
    sources.update(PHASE_EVENTS.values())
    for path in source_directory.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in ("T", "text") or len(node.args) == 0:
                continue
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                sources.add(argument.value)
    for language in ("fr", "en"):
        catalog = TRANSLATION_DIRECTORY / f"rocket_lantern_{language}.ts"
        messages = ElementTree.parse(catalog).findall(".//message")
        catalog_sources = {message.findtext("source") for message in messages}
        assert sources <= catalog_sources, (
            f"Missing {language} translations: {sources - catalog_sources}"
        )
        translator = QTranslator()
        assert translator.load(str(catalog.with_suffix(".qm")))
        for message in messages:
            source = message.findtext("source")
            translated = message.findtext("translation")
            assert translator.translate("RocketLantern", source) == translated, (
                f"Stale compiled {language} translation: {source}"
            )


def test_language_should_reject_unknown_code_without_changing_current_language(
    localized_window: MainWindow,
) -> None:
    manager = language_manager()
    with pytest.raises(ValueError, match="Unsupported language: xx"):
        manager.set_language("xx")
    assert manager.language == "fr"
