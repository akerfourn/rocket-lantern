"""Opt-in preferences, conflicts and suspension during shortcut editing."""

from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QWidget

from rocket_lantern.global_hotkeys import DEFAULT_HOTKEYS, GlobalHotkeys, HotkeyBackend
from rocket_lantern.hotkey_controller import HotkeyController
from rocket_lantern.settings_panel import SettingsPanel
from rocket_lantern.storage import MatchStore


@pytest.fixture
def controller(application: QApplication) -> Iterator[HotkeyController]:
    parent = QWidget()
    settings = SettingsPanel(49124, "fr", "matches", parent)
    store = MatchStore(":memory:")
    backend = Mock(spec=HotkeyBackend)
    backend.register.return_value = True
    manager = GlobalHotkeys(settings, backend)
    control = HotkeyController(settings, store, manager)
    yield control
    control.shutdown()
    settings.close()
    parent.deleteLater()
    store.close()


def test_settings_should_default_to_disabled_with_configured_default_chords(
    controller: HotkeyController,
) -> None:
    assert not controller.panel.enabled.isChecked()
    assert controller.panel.fields.isHidden()
    assert controller.panel.sequences() == DEFAULT_HOTKEYS
    controller.manager.backend.register.assert_not_called()


def test_settings_should_apply_opt_in_and_pause_registration_while_editing(
    controller: HotkeyController,
    application: QApplication,
) -> None:
    settings = controller.settings
    settings.show()
    application.processEvents()
    controller.panel.enabled.setChecked(True)
    assert not controller.panel.fields.isHidden()
    controller.panel.apply_button.click()
    assert controller.store.setting("evaluation_hotkeys_enabled") == "1"
    controller.manager.backend.register.assert_not_called()
    settings.close()
    assert controller.manager.backend.register.call_count == 4
    settings.show()
    assert controller.manager.backend.unregister.call_count == 4
    controller.panel.enabled.setChecked(False)
    controller.panel.apply_button.click()
    settings.close()
    assert controller.store.setting("evaluation_hotkeys_enabled") == "0"
    assert controller.manager.backend.register.call_count == 4


def test_settings_should_save_custom_chords_and_restore_them_without_registration_when_disabled(
    controller: HotkeyController,
) -> None:
    controller.settings.show()
    controller.panel.enabled.setChecked(True)
    controller.panel.editors[2].setKeySequence(QKeySequence("Alt+Shift+P"))
    controller.panel.apply_button.click()
    controller.panel.enabled.setChecked(False)
    controller.panel.apply_button.click()
    parent = QWidget()
    settings = SettingsPanel(49124, "fr", "matches", parent)
    backend = Mock(spec=HotkeyBackend)
    restored = HotkeyController(settings, controller.store, GlobalHotkeys(settings, backend))
    try:
        assert restored.panel.sequences()[2] == "Alt+Shift+P"
        assert not restored.panel.enabled.isChecked()
        backend.register.assert_not_called()
    finally:
        restored.shutdown()
        parent.deleteLater()


def test_settings_should_reject_duplicates_without_changing_saved_configuration(
    controller: HotkeyController,
) -> None:
    controller.panel.enabled.setChecked(True)
    controller.panel.editors[1].setKeySequence(controller.panel.editors[0].keySequence())
    controller.panel.apply_button.click()
    assert "différent" in controller.panel.status.text()
    assert controller.store.setting("evaluation_hotkeys_enabled") == ""
    controller.manager.backend.register.assert_not_called()


def test_settings_should_report_conflicts_and_keep_all_shortcuts_inactive(
    controller: HotkeyController,
) -> None:
    controller.manager.backend.register.side_effect = [True, False]
    controller.panel.enabled.setChecked(True)
    controller.panel.apply_button.click()
    assert "Aucun raccourci n’est actif" in controller.panel.status.text()
    assert not controller.manager._active
    assert controller.manager.backend.unregister.call_count == 1
    controller.settings.show()
    assert "Aucun raccourci n’est actif" in controller.panel.status.text()


def test_settings_should_ignore_unsaved_edits_and_release_shortcuts_on_shutdown(
    controller: HotkeyController,
) -> None:
    controller.panel.enabled.setChecked(True)
    controller.panel.apply_button.click()
    controller.settings.show()
    controller.panel.editors[0].setKeySequence(QKeySequence("Alt+Shift+A"))
    controller.settings.close()
    assert controller.manager.backend.register.call_args_list[-4].args[1].key == 0x70
    controller.shutdown()
    assert not controller.manager._active
    controller.settings.show()
    controller.settings.close()
    assert not controller.manager._active


def test_settings_should_disable_corrupt_saved_shortcuts_instead_of_guessing(
    controller: HotkeyController,
) -> None:
    controller.store.set_settings({"evaluation_hotkeys_enabled": "1", "evaluation_hotkeys": "[42]"})
    parent = QWidget()
    settings = SettingsPanel(49124, "fr", "matches", parent)
    backend = Mock(spec=HotkeyBackend)
    restored = HotkeyController(settings, controller.store, GlobalHotkeys(settings, backend))
    try:
        assert not restored.panel.enabled.isChecked()
        assert restored.panel.sequences() == DEFAULT_HOTKEYS
        backend.register.assert_not_called()
    finally:
        restored.shutdown()
        parent.deleteLater()


def test_settings_should_scroll_long_preferences_and_keep_close_button_visible_on_small_screen(
    controller: HotkeyController,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen = Mock()
    screen.availableGeometry.return_value = QRect(0, 0, 1000, 300)
    monkeypatch.setattr(controller.settings, "screen", lambda: screen)
    controller.settings.show()
    controller.settings.sections.setCurrentWidget(controller.settings.shortcuts_section)
    controller.panel.enabled.setChecked(True)
    application.processEvents()
    application.processEvents()

    assert controller.settings.frameGeometry().height() <= 300
    assert controller.settings.shortcuts_section.verticalScrollBar().maximum() > 0
    close_rect = controller.settings.close_button.geometry()
    assert controller.settings.rect().contains(close_rect)
