"""Custom list settings, live/historical menus and optional shortcuts."""

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QInputDialog

from rocket_lantern.evaluation_strip import EvaluationStrip
from rocket_lantern.i18n import language_manager
from rocket_lantern.labels import DEFAULT_LIST, Label, LabelList
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult
from rocket_lantern.window import MainWindow

GROUP = "custom:00000000-0000-0000-0000-000000000001"
ITEM = "custom:00000000-0000-0000-0000-000000000002"
TIMESTAMP = "2026-10-19T12:00:00+00:00"


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    store.set_setting("player_id", "player")
    widget = MainWindow(store)
    widget.show()
    yield widget
    widget.close()
    store.close()
    language_manager().set_language("fr")


def add_custom(window: MainWindow) -> None:
    window.store.labels.save_list(LabelList(GROUP, "Mon jeu", position=1))
    window.store.labels.save_label(Label(ITEM, GROUP, "À revoir", "#123456", "possible"))
    window.label_catalog.reload()


def observe(window: MainWindow, guid: str) -> None:
    window._receive(
        json.dumps(
            {
                "Event": "UpdateState",
                "Data": {
                    "MatchGuid": guid,
                    "Game": {"PlaylistId": 11},
                    "Players": [{"PrimaryId": "player", "Name": "Test", "TeamNum": 0}],
                },
            }
        )
    )


def choose(strip: EvaluationStrip, group: str, value: str) -> None:
    button = strip.buttons[group]
    button._menu.aboutToShow.emit()
    button.actions_by_value[value].trigger()


def test_lists_should_have_independent_live_choices_and_reset_on_each_new_match(
    window: MainWindow,
) -> None:
    add_custom(window)
    observe(window, "first")
    strip = window.matches.counters.evaluations
    choose(strip, DEFAULT_LIST, "strong")
    choose(strip, GROUP, ITEM)
    assert window.store.labels.choices("first") == {DEFAULT_LIST: "strong", GROUP: ITEM}
    assert "Mon jeu" in strip.buttons[GROUP].toolTip()
    observe(window, "second")
    assert strip.buttons[DEFAULT_LIST].value == "not_evaluated"
    assert strip.buttons[GROUP].value == ""
    choose(strip, GROUP, ITEM)
    choose(strip, GROUP, "")
    assert window.store.labels.choices("second") == {}


def test_custom_history_choices_should_not_change_the_live_match_or_other_lists(
    window: MainWindow,
) -> None:
    add_custom(window)
    window.store.save(MatchResult("old", "player", TIMESTAMP, 11, "win"))
    window.matches.period.setCurrentIndex(window.matches.period.findData("all"))
    window._refresh()
    observe(window, "current")
    history = window.matches.history.cellWidget(0, 4)
    assert isinstance(history, EvaluationStrip)
    choose(history, GROUP, ITEM)
    assert window.store.labels.choices("old") == {GROUP: ITEM}
    assert window.matches.counters.evaluations.buttons[GROUP].value == ""
    assert window.matches.counters.evaluations.guid == "current"


def test_disabled_lists_should_hide_live_buttons_but_keep_historical_annotations(
    window: MainWindow,
) -> None:
    add_custom(window)
    window.store.save(MatchResult("old", "player", TIMESTAMP, 11, "win"))
    window.store.labels.choose("old", GROUP, ITEM, TIMESTAMP)
    window.matches.period.setCurrentIndex(window.matches.period.findData("all"))
    group = next(item for item in window.label_catalog.lists if item.id == GROUP)
    window.store.labels.save_list(replace(group, enabled=False))
    window.label_catalog.reload()
    assert window.matches.counters.evaluations.buttons[GROUP].isHidden()
    history = window.matches.history.cellWidget(0, 4)
    assert isinstance(history, EvaluationStrip)
    assert not history.buttons[GROUP].isHidden()
    assert history.buttons[GROUP].value == ITEM
    assert not history.buttons[GROUP].isEnabled()


def test_settings_should_create_lists_labels_and_edit_name_color_and_activation(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel = window.settings.labels
    get_name = Mock(side_effect=[("Mon jeu", True), ("À revoir", True)])
    monkeypatch.setattr(QInputDialog, "getText", get_name)
    panel.add_list.click()
    group = panel.lists.currentData()
    assert group.startswith("custom:")
    panel.add_label.click()
    item = panel.items.currentData()
    assert item.startswith("custom:")
    panel.label_name.setText("Renamed")
    panel._color = "#abcdef"
    panel.label_enabled.setChecked(False)
    panel.save_label.click()
    definition = window.label_catalog.labels[item]
    assert (definition.name, definition.color, definition.enabled) == ("Renamed", "#abcdef", False)
    assert window.store.labels.choices("missing") == {}
    assert item not in window.settings.hotkeys.label_ids


def test_custom_names_should_not_be_translated_or_replace_native_translations(
    window: MainWindow, application: QApplication
) -> None:
    add_custom(window)
    language_manager().set_language("en")
    application.processEvents()
    assert (
        window.matches.counters.evaluations.buttons[GROUP].actions_by_value[ITEM].text()
        == "À revoir"
    )
    assert (
        window.matches.counters.evaluation.actions_by_value["possible"].text() == "Possible smurf"
    )


def test_native_editor_should_translate_without_saving_translations_as_custom_names(
    window: MainWindow,
    application: QApplication,
) -> None:
    panel = window.settings.labels
    panel.items.setCurrentIndex(panel.items.findData("possible"))
    language_manager().set_language("en")
    application.processEvents()
    assert panel.label_name.text() == "Possible smurf"
    panel._color = "#abcdef"
    panel.save_label.click()
    assert window.label_catalog.labels["possible"].name == "Suspicion possible"
    language_manager().set_language("fr")
    application.processEvents()
    assert panel.label_name.text() == "Suspicion possible"


def test_label_configuration_should_preserve_draft_when_database_write_fails(
    window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel = window.settings.labels
    panel.items.setCurrentIndex(panel.items.findData("possible"))
    before = window.label_catalog.labels["possible"]
    panel.label_name.setText("Draft")
    monkeypatch.setattr(
        window.store.labels, "save_label", Mock(side_effect=sqlite3.OperationalError("full"))
    )
    panel.save_label.click()
    assert window.label_catalog.labels["possible"] == before
    assert panel.label_name.text() == "Draft"
    assert "SQLite" in window.notice.text()


def test_optional_shortcuts_should_keep_stable_label_ids_and_support_custom_actions(
    window: MainWindow,
) -> None:
    add_custom(window)
    observe(window, "game")
    panel = window.settings.hotkeys
    assert len(panel.editors) == 5
    window.settings.show()
    panel.enabled.setChecked(True)
    panel.editors[panel.label_ids.index(ITEM)].setKeySequence(QKeySequence("Alt+Shift+A"))
    panel.editors[0].clear()
    panel.apply_button.click()
    assert window.label_catalog.labels[ITEM].shortcut == "Alt+Shift+A"
    assert window.label_catalog.labels["not_evaluated"].shortcut == ""
    window.hotkeys.activated.emit(ITEM)
    assert window.store.labels.choices("game") == {GROUP: ITEM}
    window.hotkeys.activated.emit("possible")
    assert window.store.labels.choices("game") == {GROUP: ITEM, DEFAULT_LIST: "possible"}
