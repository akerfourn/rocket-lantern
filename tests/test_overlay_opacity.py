"""Independent, persistent opacity for real overlays and their placement previews."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from rocket_lantern.i18n import language_manager
from rocket_lantern.storage import MatchStore, Summary
from rocket_lantern.window import MainWindow


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    store.set_setting("boost_overlay_risk_accepted", "1")
    widget = MainWindow(store)
    widget.show()
    yield widget
    widget.close()
    store.close()
    language_manager().set_language("fr")


def observe_teammate(window: MainWindow) -> None:
    window.live.set_player("me")
    window.live.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "match",
                "Game": {},
                "Players": [
                    {"PrimaryId": "me", "Name": "Me", "TeamNum": 0, "Boost": 80},
                    {"PrimaryId": "mate", "Name": "Mate", "TeamNum": 0, "Boost": 40},
                ],
            },
        },
        "2026-10-20T19:00:00+00:00",
        False,
    )


def test_opacity_should_preserve_existing_appearance_and_not_enable_overlays(
    window: MainWindow,
) -> None:
    for controls in (window.settings.overlay, window.settings.boost_overlay):
        assert controls.opacity.value() == 100
        assert controls.opacity_slider.value() == 100
        assert controls.opacity.minimum() == 10 and controls.opacity.maximum() == 100
        assert not controls.activation_enabled()
    assert window.store.setting("overlay_opacity") == ""
    assert window.store.setting("boost_overlay_opacity") == ""
    assert window.overlay.window is None and window.boost_overlay.window is None


@pytest.mark.parametrize("boost", [False, True])
def test_opacity_should_sync_slider_and_number_and_write_once_per_change(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, boost: bool
) -> None:
    controls = window.settings.overlay
    key = "overlay_opacity"
    if boost:
        controls = window.settings.boost_overlay
        key = "boost_overlay_opacity"
    save = Mock(wraps=window.store.set_setting)
    monkeypatch.setattr(window.store, "set_setting", save)

    controls.opacity_slider.setValue(60)

    assert controls.opacity.value() == 60
    save.assert_called_once_with(key, "60")
    save.reset_mock()
    controls.opacity.setValue(35)
    assert controls.opacity_slider.value() == 35
    save.assert_called_once_with(key, "35")
    assert not controls.activation_enabled()


def test_opacity_should_apply_to_both_live_huds_and_survive_updates_and_visibility_changes(
    window: MainWindow,
) -> None:
    window.settings.overlay.opacity.setValue(65)
    window.settings.boost_overlay.opacity.setValue(40)
    window.settings.overlay.enabled.setChecked(True)
    window.settings.boost_overlay.scope.setCurrentIndex(2)
    observe_teammate(window)
    hud = window.overlay.window
    boost = window.boost_overlay.window

    assert hud.windowOpacity() == pytest.approx(0.65, abs=1 / 255)
    assert boost.windowOpacity() == pytest.approx(0.4, abs=1 / 255)
    original = hud.geometry()
    window.settings.overlay.opacity_slider.setValue(50)
    assert hud.windowOpacity() == pytest.approx(0.5, abs=1 / 255)
    assert hud.geometry() == original
    assert boost.windowOpacity() == pytest.approx(0.4, abs=1 / 255)
    window.matches.counters.set_summary(Summary(12, 3, 0))
    observe_teammate(window)
    window.settings.overlay.enabled.setChecked(False)
    window.settings.overlay.opacity.setValue(75)
    window.settings.overlay.enabled.setChecked(True)
    assert window.overlay.window is hud and hud.isVisible()
    assert hud.windowOpacity() == pytest.approx(0.75, abs=1 / 255)
    assert boost.windowOpacity() == pytest.approx(0.4, abs=1 / 255)


@pytest.mark.parametrize("boost", [False, True])
def test_opacity_should_update_only_preview_content_without_moving_it_or_fading_toolbar(
    window: MainWindow, boost: bool
) -> None:
    controls = window.settings.overlay
    controller = window.overlay
    if boost:
        controls = window.settings.boost_overlay
        controller = window.boost_overlay
    controls.opacity.setValue(65)
    controls.place_button.click()
    editor = controller.editor
    editor.preview.place(QPoint(20, editor.toolbar.geometry().bottom() + 20))
    original_geometry = editor.preview.geometry()
    area = editor.preview.geometry()
    original = editor.grab(area).toImage()
    toolbar = editor.grab(editor.toolbar.geometry()).toImage()

    controls.opacity.setValue(30)

    assert editor.preview.opacity_effect.opacity() == 0.3
    assert editor.preview.opacity_effect.isEnabled()
    assert editor.preview.geometry() == original_geometry
    assert editor.grab(area).toImage() != original
    assert editor.grab(editor.toolbar.geometry()).toImage() == toolbar
    assert editor.toolbar_opacity.opacity() == 1.0
    assert controller.window is None
    editor.cancel_button.click()
    controls.place_button.click()
    assert controller.editor.preview.opacity_effect.opacity() == 0.3
    controls.opacity.setValue(100)
    assert not controller.editor.preview.opacity_effect.isEnabled()


def test_opacity_should_restore_independent_preferences_without_writing_on_startup(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "opacity.sqlite3"
    store = MatchStore(path)
    first = MainWindow(store)
    first.settings.overlay.opacity.setValue(70)
    first.settings.boost_overlay.opacity.setValue(25)
    first.settings.overlay.enabled.setChecked(True)
    first.close()
    store.close()
    reopened_store = MatchStore(path)
    save = Mock(wraps=reopened_store.set_setting)
    monkeypatch.setattr(reopened_store, "set_setting", save)
    restored = MainWindow(reopened_store)
    try:
        assert restored.settings.overlay.opacity.value() == 70
        assert restored.settings.boost_overlay.opacity.value() == 25
        assert restored.settings.overlay.opacity_slider.value() == 70
        assert restored.settings.boost_overlay.opacity_slider.value() == 25
        assert restored.overlay.window.windowOpacity() == pytest.approx(0.7, abs=1 / 255)
        assert restored.boost_overlay.window is None
        save.assert_not_called()
    finally:
        restored.close()
        reopened_store.close()


@pytest.mark.parametrize("value", ["0", "9", "101", "-1", "1.5", "invalid"])
def test_opacity_should_ignore_invalid_saved_values_without_overwriting_them(
    application: QApplication, value: str
) -> None:
    store = MatchStore(":memory:")
    store.set_settings({"overlay_opacity": value, "boost_overlay_opacity": value})
    window = MainWindow(store)
    try:
        assert window.settings.overlay.opacity.value() == 100
        assert window.settings.boost_overlay.opacity.value() == 100
        assert store.setting("overlay_opacity") == value
        assert store.setting("boost_overlay_opacity") == value
    finally:
        window.close()
        store.close()


def test_opacity_should_roll_back_both_controls_and_rendering_on_storage_failure(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    controls = window.settings.overlay
    controls.opacity.setValue(70)
    controls.enabled.setChecked(True)
    controls.place_button.click()
    editor = window.overlay.editor
    window.overlay.failed.disconnect()
    failed = Mock()
    window.overlay.failed.connect(failed)
    monkeypatch.setattr(
        window.store, "set_setting", Mock(side_effect=sqlite3.OperationalError("full"))
    )

    controls.opacity_slider.setValue(40)

    failed.assert_called_once_with()
    assert controls.opacity.value() == 70 and controls.opacity_slider.value() == 70
    assert window.overlay.window.windowOpacity() == pytest.approx(0.7, abs=1 / 255)
    assert editor.preview.opacity_effect.opacity() == 0.7


def test_opacity_should_translate_controls_without_resetting_preferences(
    window: MainWindow, application: QApplication
) -> None:
    window.settings.overlay.opacity.setValue(55)

    language_manager().set_language("en")
    application.processEvents()

    for controls in (window.settings.overlay, window.settings.boost_overlay):
        assert controls.opacity_label.text() == "Opacity:"
        assert controls.opacity.accessibleName() == "Opacity:"
        assert controls.opacity_slider.accessibleName() == "Opacity:"
    assert window.settings.overlay.opacity.value() == 55
    assert window.store.setting("overlay_opacity") == "55"
