"""Mouse assessment, explicit match targets and translated tooltip regressions."""

import json
import sqlite3
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QHeaderView, QStyleOptionToolButton

from rocket_lantern.evaluation_button import EvaluationButton, evaluation_icon
from rocket_lantern.evaluations import Evaluation
from rocket_lantern.i18n import language_manager
from rocket_lantern.match_detail_dialog import MatchDetailDialog
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult
from rocket_lantern.window import MainWindow


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    store.set_setting("player_id", "player")
    language_manager().set_language("fr")
    widget = MainWindow(store)
    widget.show()
    yield widget
    widget.close()
    store.close()
    language_manager().set_language("fr")


def state(window: MainWindow, guid: str, **game: object) -> None:
    window._receive(
        json.dumps(
            {
                "Event": "UpdateState",
                "Data": {
                    "MatchGuid": guid,
                    "Game": {"PlaylistId": 11, **game},
                    "Players": [{"PrimaryId": "player", "Name": "Player", "TeamNum": 0}],
                },
            }
        )
    )


def vote(button: EvaluationButton, value: Evaluation) -> None:
    button._menu.aboutToShow.emit()
    button.actions_by_value[value].trigger()


def test_badge_should_reset_for_new_match_and_keep_last_match_editable(window: MainWindow) -> None:
    button = window.matches.counters.evaluation
    assert not button.isEnabled()
    state(window, "first")
    vote(button, Evaluation.POSSIBLE)
    state(window, "first")
    assert button.value == Evaluation.POSSIBLE
    assert "Suspicion possible" in button.toolTip()
    window._receive(
        json.dumps(
            {
                "Event": "MatchEnded",
                "Data": {
                    "MatchGuid": "first",
                    "WinnerTeamNum": 0,
                },
            }
        )
    )
    assert button.guid == "first"
    assert button.isEnabled()
    window._receive(json.dumps({"Event": "MatchDestroyed", "Data": {"MatchGuid": "first"}}))
    vote(button, Evaluation.STRONG)
    assert window.store.evaluation("first") == Evaluation.STRONG
    state(window, "second")
    assert button.value == Evaluation.NOT_EVALUATED
    assert button.guid == "second"
    assert window.store.evaluation("first") == Evaluation.STRONG
    assert not window.settings.hotkeys.enabled.isChecked()


def test_history_should_edit_a_previous_match_without_changing_current_vote_or_filters(
    window: MainWindow,
) -> None:
    window.store.save(MatchResult("old", "player", "2026-10-11T12:00:00+00:00", 11, "win"))
    window.matches.period.setCurrentIndex(window.matches.period.findData("all"))
    window.matches.playlist_filter.setCurrentIndex(window.matches.playlist_filter.findData("all"))
    window._refresh()
    state(window, "new")
    old = window.matches.history.cellWidget(0, 4)
    vote(old, Evaluation.NO_SUSPICION)
    assert window.store.evaluation("old") == Evaluation.NO_SUSPICION
    assert old.value == Evaluation.NO_SUSPICION
    assert window.matches.counters.evaluation.value == Evaluation.NOT_EVALUATED
    assert window.matches.counters.evaluation.guid == "new"
    assert window.matches.period.currentData() == "all"
    assert window.matches.playlist_filter.currentData() == "all"
    window.matches._open_detail(0, 4)
    assert window.matches.findChild(MatchDetailDialog) is None


def test_open_menu_should_keep_original_match_id_when_a_new_game_arrives(
    window: MainWindow,
) -> None:
    button = window.matches.counters.evaluation
    state(window, "old")
    button._menu.aboutToShow.emit()
    state(window, "new")
    button.actions_by_value[Evaluation.STRONG].trigger()
    assert window.store.evaluation("old") == Evaluation.STRONG
    assert window.store.evaluation("new") == Evaluation.NOT_EVALUATED
    assert button.value == Evaluation.NOT_EVALUATED


def test_late_events_should_not_redirect_the_badge_to_an_old_match(window: MainWindow) -> None:
    state(window, "old")
    state(window, "new")
    for event in ("MatchEnded", "MatchDestroyed"):
        window._receive(
            json.dumps(
                {
                    "Event": event,
                    "Data": {
                        "MatchGuid": "old",
                        "WinnerTeamNum": 0,
                    },
                }
            )
        )
    assert window.matches.counters.evaluation.guid == "new"
    assert window.matches.counters.evaluation.isEnabled()


def test_badge_should_ignore_keyboard_votes_without_a_match_and_while_viewing_replays(
    window: MainWindow,
) -> None:
    window.hotkeys.activated.emit("strong")
    assert window.store.connection.execute("SELECT COUNT(*) FROM match_labels").fetchone()[0] == 0
    state(window, "real")
    window._receive(json.dumps({"Event": "ReplayCreated", "Data": {}}))
    state(window, "replay", bReplay=True, Frame=1)
    window.hotkeys.activated.emit("strong")
    assert not window.matches.counters.evaluation.isEnabled()
    assert window.store.evaluation("real") == Evaluation.NOT_EVALUATED
    assert window.store.evaluation("replay") == Evaluation.NOT_EVALUATED


def test_vote_should_preserve_displayed_value_when_database_write_fails(
    window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state(window, "game")
    monkeypatch.setattr(
        window.store, "set_evaluation", Mock(side_effect=sqlite3.OperationalError())
    )
    vote(window.matches.counters.evaluation, Evaluation.STRONG)
    assert window.matches.counters.evaluation.value == Evaluation.NOT_EVALUATED
    assert "SQLite" in window.notice.text()
    window.matches.counters.evaluation._menu.aboutToShow.emit()
    assert window.matches.counters.evaluation.actions_by_value[Evaluation.NOT_EVALUATED].isChecked()
    assert not window.matches.counters.evaluation.actions_by_value[Evaluation.STRONG].isChecked()


def test_tooltips_and_menu_should_translate_in_place_without_writing(
    window: MainWindow,
    application: QApplication,
) -> None:
    state(window, "game")
    vote(window.matches.counters.evaluation, Evaluation.POSSIBLE)
    language_manager().set_language("en")
    application.processEvents()
    button = window.matches.counters.evaluation
    assert "Possible smurf" in button.toolTip()
    assert button.text() == ""
    assert button.accessibleName() == "Possible smurf"
    assert button.actions_by_value[Evaluation.STRONG].text() == "Strong suspicion"
    assert window.store.evaluation("game") == Evaluation.POSSIBLE


def test_icon_only_badge_should_open_selector_only_on_click(window: MainWindow) -> None:
    state(window, "game")
    button = window.matches.counters.evaluation
    option = QStyleOptionToolButton()
    button.initStyleOption(option)

    assert button.text() == ""
    assert button.menu() is None
    assert not option.features & QStyleOptionToolButton.ToolButtonFeature.HasMenu
    assert not button._menu.isVisible()
    assert button.accessibleName() == "Non évalué"
    assert "Non évalué" in button.toolTip()

    button.click()

    assert button._menu.isVisible()
    assert button._menu_guid == "game"
    button.actions_by_value[Evaluation.POSSIBLE].trigger()
    assert window.store.evaluation("game") == Evaluation.POSSIBLE
    assert button.text() == ""
    assert "Suspicion possible" in button.toolTip()


def test_history_badge_should_remain_compact_and_translate_its_tooltip(
    window: MainWindow, application: QApplication
) -> None:
    window.store.save(MatchResult("old", "player", "2026-10-11T12:00:00+00:00", 11, "win"))
    window.matches.period.setCurrentIndex(window.matches.period.findData("all"))
    window._refresh()
    history = window.matches.history
    button = history.cellWidget(0, 4)
    vote(button, Evaluation.STRONG)
    application.processEvents()

    assert button.text() == ""
    assert button.menu() is None
    assert history.columnWidth(4) <= 60
    cell = history.visualRect(history.model().index(0, 4))
    assert abs(button.geometry().center().x() - cell.center().x()) <= 1
    assert history.horizontalHeader().sectionResizeMode(4) == QHeaderView.ResizeMode.Fixed
    assert "Forte suspicion" in button.toolTip()
    assert history.horizontalHeaderItem(4).toolTip() == "Évaluation"

    language_manager().set_language("en")
    application.processEvents()

    assert button.text() == ""
    assert history.columnWidth(4) <= 60
    assert "Strong suspicion" in button.toolTip()
    assert button.accessibleName() == "Strong suspicion"
    assert history.horizontalHeaderItem(4).toolTip() == "Assessment"


def test_icons_should_have_different_visible_symbols(application: QApplication) -> None:
    images = [evaluation_icon(value).pixmap(32, 32).toImage() for value in Evaluation]
    assert all(not image.isNull() for image in images)
    for index, image in enumerate(images):
        assert all(image != other for other in images[index + 1 :])
