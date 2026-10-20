"""Configurable HUD counters and passive, live match annotation icons."""

import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication

from rocket_lantern.i18n import language_manager
from rocket_lantern.label_icons import label_icon
from rocket_lantern.labels import DEFAULT_LIST, Label, LabelList
from rocket_lantern.overlay_placement import placement_from_position
from rocket_lantern.storage import MatchStore, Summary
from rocket_lantern.summary_overlay_content import SummaryOverlayContent, parse_summary_content
from rocket_lantern.window import MainWindow

GROUP = "custom:00000000-0000-0000-0000-000000000001"
ITEM = "custom:00000000-0000-0000-0000-000000000002"


@pytest.fixture
def window(application: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    clock = Mock()
    clock.now.return_value = datetime(2026, 10, 20, 18, tzinfo=UTC)
    monkeypatch.setattr("rocket_lantern.evaluation_controller.datetime", clock)
    store = MatchStore(":memory:")
    store.labels.save_list(LabelList(GROUP, "Mon jeu", family="flag"))
    store.labels.save_label(Label(ITEM, GROUP, "À revoir", "#123456", "possible"))
    widget = MainWindow(store)
    widget.show()
    yield widget
    widget.close()
    store.close()
    language_manager().set_language("fr")


def test_content_should_round_trip_stable_category_ids_and_deduplicate_them() -> None:
    content = SummaryOverlayContent(False, True, False, (DEFAULT_LIST, GROUP))

    assert parse_summary_content(content.serialize()) == content
    assert parse_summary_content("{}") == SummaryOverlayContent()
    assert parse_summary_content('{"label_lists":["smurfing","smurfing"]}').label_lists == (
        DEFAULT_LIST,
    )


@pytest.mark.parametrize(
    "value",
    [
        "invalid-json",
        "[]",
        '{"wins":1}',
        '{"losses":"false"}',
        '{"delta":null}',
        '{"label_lists":null}',
        '{"label_lists":"smurfing"}',
        '{"label_lists":[1]}',
        '{"label_lists":[""]}',
    ],
)
def test_content_should_reject_malformed_preferences(value: str) -> None:
    with pytest.raises(ValueError):
        parse_summary_content(value)


def test_content_should_preserve_default_hud_without_enabling_or_writing_it(
    window: MainWindow,
) -> None:
    controls = window.settings.overlay.content

    assert controls.content == SummaryOverlayContent()
    assert all(
        checkbox.isChecked() for checkbox in (controls.wins, controls.losses, controls.delta)
    )
    assert not any(checkbox.isChecked() for checkbox in controls.category_checks.values())
    assert window.store.setting("summary_overlay_content") == ""
    assert window.overlay.window is None
    assert not window.settings.overlay.enabled.isChecked()


@pytest.mark.parametrize("counter", ["wins", "losses", "delta"])
def test_content_should_hide_counter_icon_and_number_without_leaving_space(
    window: MainWindow, counter: str
) -> None:
    window.settings.overlay.enabled.setChecked(True)
    hud = window.overlay.window
    width = hud.width()

    getattr(window.settings.overlay.content, counter).setChecked(False)

    assert getattr(hud, f"{counter}_group").isHidden()
    assert hud.width() < width
    stored = parse_summary_content(window.store.setting("summary_overlay_content"))
    assert not getattr(stored, counter)
    getattr(window.settings.overlay.content, counter).setChecked(True)
    assert hud.width() == width


def test_content_should_follow_hotkeys_manual_edits_and_match_changes_without_history_reads(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.settings.overlay.content.category_checks[DEFAULT_LIST].setChecked(True)
    window.settings.overlay.content.category_checks[GROUP].setChecked(True)
    window.settings.overlay.enabled.setChecked(True)
    hud = window.overlay.window
    window.evaluations._set_target("current")
    history = Mock(side_effect=AssertionError("The HUD must not reload history"))
    monkeypatch.setattr(window.store, "filtered_history", history)

    window.hotkeys.activated.emit("possible")
    window.evaluations.save_label("current", GROUP, ITEM)

    assert set(hud.label_symbols) == {DEFAULT_LIST, GROUP}
    assert "Suspicion possible" in hud.label_symbols[DEFAULT_LIST].toolTip()
    assert hud.label_symbols[GROUP].toolTip() == "Mon jeu · À revoir"
    expected = label_icon(window.label_catalog.labels[ITEM], "flag").pixmap(28, 28).toImage()
    assert hud.label_symbols[GROUP].pixmap().toImage() == expected
    window.evaluations.save("older", "strong")
    assert "Suspicion possible" in hud.label_symbols[DEFAULT_LIST].toolTip()
    window.evaluations._set_target("next")
    assert hud.label_symbols[DEFAULT_LIST].toolTip() == "Suspicion de smurf · Non évalué"
    assert hud.label_symbols[GROUP].toolTip() == "Mon jeu · Non évalué"
    history.assert_not_called()
    assert hud.windowFlags() & Qt.WindowType.WindowTransparentForInput


def test_content_should_retain_custom_category_selection_after_rename_recolor_and_disable(
    window: MainWindow,
) -> None:
    controls = window.settings.overlay.content
    controls.category_checks[GROUP].setChecked(True)
    window.settings.overlay.enabled.setChecked(True)
    window.evaluations._set_target("current")
    window.evaluations.save_label("current", GROUP, ITEM)
    hud = window.overlay.window
    before = hud.label_symbols[GROUP].pixmap().toImage()
    stored = window.store.setting("summary_overlay_content")
    category = next(item for item in window.label_catalog.lists if item.id == GROUP)
    label = window.label_catalog.labels[ITEM]

    window.store.labels.save_list(replace(category, name="Ambiance", family="shield"))
    window.store.labels.save_label(replace(label, name="Compliqué", color="#ff5500"))
    window.label_catalog.reload()

    assert controls.category_checks[GROUP].text() == "Ambiance"
    assert controls.category_checks[GROUP].isChecked()
    assert hud.label_symbols[GROUP].toolTip() == "Ambiance · Compliqué"
    assert hud.label_symbols[GROUP].pixmap().toImage() != before
    window.store.labels.save_list(replace(category, enabled=False))
    window.label_catalog.reload()
    assert GROUP not in hud.label_symbols
    assert not controls.category_checks[GROUP].isEnabled()
    assert controls.category_checks[GROUP].isChecked()
    window.store.labels.save_list(category)
    window.label_catalog.reload()
    assert GROUP in hud.label_symbols
    assert controls.category_checks[GROUP].isChecked()
    assert window.store.setting("summary_overlay_content") == stored


@pytest.mark.parametrize("anchor", ["left", "center", "right"])
def test_content_should_preserve_live_and_preview_anchor_when_elements_change(
    window: MainWindow, anchor: str
) -> None:
    window.settings.overlay.enabled.setChecked(True)
    hud = window.overlay.window
    bounds = QRect(0, 0, 800, 800)
    window.overlay._set_placement(
        placement_from_position("", "top_left", bounds, hud.size(), QPoint(300, 180), anchor)
    )
    original = hud.geometry()
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor
    original_preview = editor.preview.geometry()

    window.settings.overlay.content.category_checks[GROUP].setChecked(True)

    enlarged = hud.geometry()
    preview = editor.preview.geometry()
    assert enlarged.width() > original.width()
    assert preview.width() > original_preview.width()
    for before, after in ((original, enlarged), (original_preview, preview)):
        assert before.y() == after.y()
        if anchor == "left":
            assert before.x() == after.x()
        elif anchor == "center":
            assert before.x() + before.width() // 2 == after.x() + after.width() // 2
        else:
            assert before.right() == after.right()
    assert GROUP in editor.preview.display.label_symbols
    editor.save_button.click()
    assert hud.isVisible()
    assert hud.size() == preview.size()


def test_content_should_hide_empty_overlay_without_forgetting_activation(
    window: MainWindow,
) -> None:
    controls = window.settings.overlay.content
    window.settings.overlay.enabled.setChecked(True)
    hud = window.overlay.window

    for checkbox in (controls.wins, controls.losses, controls.delta):
        checkbox.setChecked(False)

    assert not hud.isVisible()
    assert window.settings.overlay.enabled.isChecked()
    assert window.store.setting("overlay_enabled") == "1"
    assert not window.settings.overlay.place_button.isEnabled()
    assert not controls.empty_hint.isHidden()
    controls.category_checks[GROUP].setChecked(True)
    assert window.overlay.window is hud and hud.isVisible()
    assert controls.empty_hint.isHidden()
    assert window.settings.overlay.place_button.isEnabled()
    assert set(hud.label_symbols) == {GROUP}
    assert all(group.isHidden() for group in (hud.wins_group, hud.losses_group, hud.delta_group))


def test_content_should_restore_selection_from_database_without_writing_on_startup(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "settings.sqlite3"
    store = MatchStore(path)
    first = MainWindow(store)
    first.settings.overlay.content.wins.setChecked(False)
    first.settings.overlay.content.delta.setChecked(False)
    first.settings.overlay.content.category_checks[DEFAULT_LIST].setChecked(True)
    first.close()
    store.close()
    restored_store = MatchStore(path)
    save = Mock(wraps=restored_store.set_setting)
    monkeypatch.setattr(restored_store, "set_setting", save)
    restored = MainWindow(restored_store)
    try:
        content = restored.settings.overlay.content
        assert content.content == SummaryOverlayContent(False, True, False, (DEFAULT_LIST,))
        assert not content.wins.isChecked() and not content.delta.isChecked()
        assert content.losses.isChecked() and content.category_checks[DEFAULT_LIST].isChecked()
        save.assert_not_called()
    finally:
        restored.close()
        restored_store.close()


def test_content_should_fall_back_safely_when_saved_preferences_are_malformed(
    application: QApplication,
) -> None:
    store = MatchStore(":memory:")
    store.set_setting("summary_overlay_content", '{"wins":"false"}')
    window = MainWindow(store)
    try:
        assert window.settings.overlay.content.content == SummaryOverlayContent()
        assert window.overlay.window is None
        assert store.setting("summary_overlay_content") == '{"wins":"false"}'
    finally:
        window.close()
        store.close()


def test_content_should_roll_back_ui_and_keep_rendering_when_storage_write_fails(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.settings.overlay.enabled.setChecked(True)
    hud = window.overlay.window
    original = hud.geometry()
    window.overlay.failed.disconnect()
    failed = Mock()
    window.overlay.failed.connect(failed)
    monkeypatch.setattr(
        window.store, "set_setting", Mock(side_effect=sqlite3.OperationalError("full"))
    )

    window.settings.overlay.content.wins.setChecked(False)

    failed.assert_called_once_with()
    assert window.settings.overlay.content.wins.isChecked()
    assert window.settings.overlay.content.content == SummaryOverlayContent()
    assert hud.geometry() == original
    assert not hud.wins_group.isHidden()


def test_content_should_translate_choices_and_icons_without_resetting_selection(
    window: MainWindow, application: QApplication
) -> None:
    content = window.settings.overlay.content
    content.losses.setChecked(False)
    content.category_checks[DEFAULT_LIST].setChecked(True)
    window.settings.overlay.enabled.setChecked(True)
    window.matches.counters.set_summary(Summary(3, 1, 0))
    window.evaluations._set_target("current")
    window.hotkeys.activated.emit("possible")
    saved = window.store.setting("summary_overlay_content")

    language_manager().set_language("en")
    application.processEvents()

    assert content.title() == "Content"
    assert content.wins.text() == "Wins" and content.losses.text() == "Losses"
    assert content.category_checks[DEFAULT_LIST].isChecked()
    assert content.category_checks[DEFAULT_LIST].text() == "Smurf suspicion"
    assert content.category_checks[GROUP].text() == "Mon jeu"
    hud = window.overlay.window
    assert hud.wins.text() == "3"
    assert "1 losses" not in hud.accessibleName()
    assert "3 wins" in hud.accessibleName() and "delta +2" in hud.accessibleName()
    assert "Possible smurf" in hud.label_symbols[DEFAULT_LIST].toolTip()
    assert window.store.setting("summary_overlay_content") == saved
