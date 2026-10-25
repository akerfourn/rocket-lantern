"""Immediate shortcut permission and automatic rebinding of saved label edits."""

import sqlite3
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QWidget

from rocket_lantern.global_hotkeys import DEFAULT_HOTKEYS, GlobalHotkeys, HotkeyBackend
from rocket_lantern.hotkey_controller import HotkeyController
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.settings_panel import SettingsPanel
from rocket_lantern.storage import MatchStore


@pytest.fixture
def controller(application: QApplication) -> Iterator[HotkeyController]:
    parent = QWidget()
    store = MatchStore(":memory:")
    settings = SettingsPanel(49124, "fr", "matches", parent, LabelCatalog(store.labels, parent))
    backend = Mock(spec=HotkeyBackend)
    backend.register.return_value = True
    control = HotkeyController(settings, store, GlobalHotkeys(settings, backend))
    yield control
    control.shutdown()
    settings.labels.reload()
    settings.labels.close()
    settings.close()
    parent.deleteLater()
    store.close()


def test_settings_should_enable_default_chords_without_an_apply_button(
    controller: HotkeyController,
) -> None:
    assert controller.panel.enabled.isChecked()
    assert tuple(controller._bindings.values()) == DEFAULT_HOTKEYS
    assert controller.manager.backend.register.call_count == 4
    assert not hasattr(controller.panel, "apply_button")
    assert controller.settings.sections.count() == 4
    assert controller.settings.general_section.isAncestorOf(controller.panel)
    assert controller.panel.parentWidget() is controller.settings.general_section.widget()


def test_settings_should_save_permission_immediately_and_pause_while_editing(
    controller: HotkeyController,
) -> None:
    controller.settings.show()
    assert controller.manager.backend.unregister.call_count == 4
    controller.manager.backend.register.reset_mock()

    controller.panel.enabled.setChecked(False)
    assert controller.store.setting("evaluation_hotkeys_enabled") == "0"
    controller.panel.enabled.setChecked(True)
    assert controller.store.setting("evaluation_hotkeys_enabled") == "1"
    controller.manager.backend.register.assert_not_called()

    controller.settings.close()
    assert controller.manager.backend.register.call_count == 4


def test_saved_label_shortcut_should_automatically_replace_registered_chord(
    controller: HotkeyController,
) -> None:
    editor = controller.settings.labels
    editor.show()
    controller.manager.backend.register.reset_mock()
    editor.items.setCurrentCell(2, 0)
    editor.shortcut.setKeySequence(QKeySequence("Alt+Shift+P"))

    assert editor.apply()

    assert controller._bindings["possible"] == "Alt+Shift+P"
    controller.manager.backend.register.assert_not_called()
    editor.close()
    calls = controller.manager.backend.register.call_args_list
    assert len(calls) == 4
    assert calls[2].args[1].key == ord("P")


@pytest.mark.parametrize("saved_permission", ["0", "1"])
def test_settings_should_preserve_explicit_saved_permission(
    controller: HotkeyController,
    saved_permission: str,
) -> None:
    controller.store.set_setting("evaluation_hotkeys_enabled", saved_permission)
    backend = Mock(spec=HotkeyBackend)
    backend.register.return_value = True
    restored = HotkeyController(
        controller.settings, controller.store, GlobalHotkeys(controller.settings, backend)
    )
    try:
        assert restored.panel.enabled.isChecked() == (saved_permission == "1")
        assert backend.register.call_count == (4 if saved_permission == "1" else 0)
    finally:
        restored.shutdown()


def test_saved_label_shortcut_should_remain_inactive_when_global_permission_is_disabled(
    controller: HotkeyController,
) -> None:
    controller.panel.enabled.setChecked(False)
    controller.manager.backend.register.reset_mock()
    editor = controller.settings.labels
    editor.show()
    editor.items.setCurrentCell(2, 0)
    editor.shortcut.setKeySequence(QKeySequence("Alt+Shift+P"))

    assert editor.apply()
    editor.close()

    assert controller._bindings["possible"] == "Alt+Shift+P"
    assert controller.store.setting("evaluation_hotkeys_enabled") == "0"
    controller.manager.backend.register.assert_not_called()


def test_settings_should_reject_duplicates_without_replacing_saved_bindings(
    controller: HotkeyController,
) -> None:
    editor = controller.settings.labels
    editor.items.setCurrentCell(1, 0)
    editor.shortcut.setKeySequence(QKeySequence(DEFAULT_HOTKEYS[0]))

    assert not editor.apply()

    assert "différent" in editor.status.text()
    assert tuple(controller._bindings.values()) == DEFAULT_HOTKEYS


def test_settings_should_report_registration_conflicts_and_keep_shortcuts_inactive(
    controller: HotkeyController,
) -> None:
    controller.panel.enabled.setChecked(False)
    controller.manager.backend.unregister.reset_mock()
    controller.manager.backend.register.side_effect = [True, False]

    controller.panel.enabled.setChecked(True)

    assert "Aucun raccourci n’est actif" in controller.panel.status.text()
    assert not controller.manager._active
    assert controller.manager.backend.unregister.call_count == 1
    controller.settings.show()
    assert "Aucun raccourci n’est actif" in controller.panel.status.text()


def test_settings_should_restore_checkbox_when_saving_permission_fails(
    controller: HotkeyController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        controller.store, "set_setting", Mock(side_effect=sqlite3.OperationalError("full"))
    )

    controller.panel.enabled.setChecked(False)

    assert controller.panel.enabled.isChecked()
    assert controller._enabled
    assert controller.manager._active
    assert "Impossible" in controller.panel.status.text()


def test_settings_should_ignore_unsaved_label_edits_and_release_shortcuts_on_shutdown(
    controller: HotkeyController,
) -> None:
    controller.settings.show()
    controller.settings.labels.shortcut.setKeySequence(QKeySequence("Alt+Shift+A"))
    controller.settings.close()
    assert controller.manager.backend.register.call_args_list[-4].args[1].key == 0x70

    controller.shutdown()
    controller.settings.show()
    controller.settings.close()

    assert not controller.manager._active


def test_settings_should_disable_corrupt_saved_shortcuts_instead_of_guessing(
    controller: HotkeyController,
) -> None:
    with controller.store.connection:
        controller.store.connection.execute(
            "UPDATE labels SET shortcut='invalid' WHERE id='possible'"
        )
    parent = QWidget()
    settings = SettingsPanel(
        49124, "fr", "matches", parent, LabelCatalog(controller.store.labels, parent)
    )
    backend = Mock(spec=HotkeyBackend)
    restored = HotkeyController(settings, controller.store, GlobalHotkeys(settings, backend))
    try:
        assert not restored.panel.enabled.isChecked()
        backend.register.assert_not_called()
        restored.panel.enabled.setChecked(True)
        assert not restored.panel.enabled.isChecked()
    finally:
        restored.shutdown()
        parent.deleteLater()


def test_general_settings_should_keep_close_button_visible_on_small_screen(
    controller: HotkeyController,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen = Mock()
    screen.availableGeometry.return_value = QRect(0, 0, 1000, 300)
    monkeypatch.setattr(controller.settings, "screen", lambda: screen)
    controller.settings.show()
    application.processEvents()
    application.processEvents()

    assert controller.settings.frameGeometry().height() <= 300
    assert controller.settings.sections.currentWidget() is controller.settings.general_section
    assert controller.settings.rect().contains(controller.settings.close_button.geometry())
