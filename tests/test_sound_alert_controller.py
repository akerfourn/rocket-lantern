"""Rule editing, persistence and the real live-event boundary with a silent audio double."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QWidget

from rocket_lantern import sound_library, sound_rule_dialog
from rocket_lantern.i18n import language_manager
from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.sound_alert_controller import SoundAlertController
from rocket_lantern.sound_alert_settings import SoundAlertSettings
from rocket_lantern.sound_alerts import (
    PlayerScope,
    SoundAlertConfig,
    SoundAlertMode,
    SoundKind,
    SoundRule,
    SoundTrigger,
    parse_sound_config,
)
from rocket_lantern.sound_library import SoundLibrary
from rocket_lantern.storage import MatchStore

OBSERVED_AT = "2026-10-25T19:00:00+00:00"


class SilentPlayer(QObject):
    failed = Signal(str)

    def __init__(self, owner: QObject) -> None:
        super().__init__(owner)
        self.play = Mock()
        self.stop = Mock()
        self.set_volume = Mock()


@pytest.fixture
def controller(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SoundAlertController]:
    language_manager().set_language("fr")
    owner = QWidget()
    controls = SoundAlertSettings()
    controls.setParent(owner)
    live = LiveMatchPanel("me")
    live.setParent(owner)
    store = MatchStore(tmp_path / "matches.sqlite3")
    player = SilentPlayer(owner)
    system_sound = tmp_path / "system.wav"
    system_sound.write_bytes(b"system sound, never sent to an audio device in this test")
    monkeypatch.setattr(sound_library, "windows_sound_path", lambda _: system_sound)
    widget = SoundAlertController(
        controls,
        live,
        store,
        owner,
        player=player,
        library=SoundLibrary(tmp_path),
        clock=Mock(return_value=100.0),
    )
    owner.show()
    yield widget
    widget.shutdown()
    owner.close()
    owner.deleteLater()
    store.close()
    language_manager().set_language("fr")


def make_rule(
    trigger: SoundTrigger = SoundTrigger.ASSIST,
    scope: PlayerScope = PlayerScope.SELF,
    index: int = 1,
) -> SoundRule:
    return SoundRule(f"00000000-0000-0000-0000-{index:012d}", trigger, scope)


def configure(
    controller: SoundAlertController, *rules: SoundRule, mode: SoundAlertMode = SoundAlertMode.ALL
) -> None:
    controller.controls.config_changed.emit(SoundAlertConfig(mode, 70, tuple(rules)))


def receive(
    controller: SoundAlertController,
    name: str,
    *,
    actor: str = "me",
    target: str = "enemy",
    replay: bool = False,
) -> None:
    if name == "UpdateState":
        message = {
            "Event": name,
            "Data": {
                "MatchGuid": "match",
                "Game": {"PlaylistId": 2},
                "Players": [
                    {"PrimaryId": "me", "Name": "Same", "TeamNum": 0, "Saves": 1},
                    {"PrimaryId": "mate", "Name": "Mate", "TeamNum": 0, "Saves": 1},
                    {"PrimaryId": "enemy", "Name": "Same", "TeamNum": 1, "Saves": 1},
                ],
            },
        }
    else:
        message = {
            "Event": "StatfeedEvent",
            "Data": {
                "MatchGuid": "match",
                "EventName": name,
                "MainTarget": {"PrimaryId": actor},
                "SecondaryTarget": {"PrimaryId": target},
            },
        }
    controller.live.observe(message, OBSERVED_AT, replay)
    controller.observe(message, replay)


def test_sound_settings_should_start_disabled_without_writes_or_audio_backend(
    controller: SoundAlertController,
) -> None:
    assert controller.config.mode == SoundAlertMode.NEVER
    assert controller.store.setting("sound_alerts") == ""
    assert not controller.timer.isActive()
    controller.player.play.assert_not_called()


def test_rule_editor_should_save_and_edit_stable_ids_while_module_remains_disabled(
    controller: SoundAlertController,
) -> None:
    controls = controller.controls
    controls.add_button.click()
    editor = controls.editor
    editor.trigger.setCurrentIndex(editor.trigger.findData("demolished"))
    editor.scope.setCurrentIndex(editor.scope.findData("teammates"))
    assert editor.subject_label.text() == "Joueur démoli :"
    editor.buttons.button(QDialogButtonBox.StandardButton.Save).click()

    saved = parse_sound_config(controller.store.setting("sound_alerts"))
    assert saved.mode == SoundAlertMode.NEVER
    assert len(saved.rules) == 1
    assert saved.rules[0].trigger == SoundTrigger.DEMOLISHED
    assert saved.rules[0].scope == PlayerScope.TEAMMATES
    identifier = saved.rules[0].id
    controls.table.selectRow(0)
    controls.edit_button.click()
    controls.editor.trigger.setCurrentIndex(controls.editor.trigger.findData("assist"))
    assert controls.editor.subject_label.text() == "Passeur :"
    controls.editor.buttons.button(QDialogButtonBox.StandardButton.Save).click()
    assert controller.config.rules[0].id == identifier
    assert controller.config.rules[0].trigger == SoundTrigger.ASSIST
    controller.player.play.assert_not_called()


def test_disabled_rule_should_remain_saved_and_manual_preview_should_still_work(
    controller: SoundAlertController,
) -> None:
    configure(controller, make_rule(), mode=SoundAlertMode.NEVER)
    controls = controller.controls
    controls.table.selectRow(0)
    controls.table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    assert not controller.config.rules[0].enabled

    controls.test_button.click()

    controller.player.play.assert_called_once()
    assert controller.config.mode == SoundAlertMode.NEVER
    assert len(controller.config.rules) == 1


def test_imported_mp3_should_be_selected_previewed_and_saved_without_its_external_path(
    controller: SoundAlertController, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "my sound.mp3"
    source.write_bytes(b"import fixture")
    monkeypatch.setattr(
        sound_rule_dialog.QFileDialog, "getOpenFileName", lambda *args: (str(source), "")
    )
    controller.controls.add_button.click()
    editor = controller.controls.editor

    editor.import_button.click()
    editor.test_button.click()
    editor.buttons.button(QDialogButtonBox.StandardButton.Save).click()

    sound = controller.config.rules[0].sound
    assert sound.kind == SoundKind.FILE
    assert sound.name == "my sound.mp3"
    path, volume = controller.player.play.call_args.args
    assert path != source
    assert path.read_bytes() == b"import fixture"
    assert volume == 70
    assert str(source) not in controller.store.setting("sound_alerts")


def test_live_events_should_play_in_parallel_and_independent_of_rule_selection(
    controller: SoundAlertController,
) -> None:
    configure(controller, make_rule(), make_rule(SoundTrigger.DEMOLISHED, PlayerScope.TEAMMATES, 2))
    receive(controller, "UpdateState")

    receive(controller, "Assist")
    receive(controller, "Demolish", actor="enemy", target="mate")

    assert controller.player.play.call_count == 2
    receive(controller, "Assist", actor="enemy")
    assert controller.player.play.call_count == 2


def test_mode_and_rule_changes_should_apply_immediately_and_preserve_configuration(
    controller: SoundAlertController,
) -> None:
    configure(controller, make_rule())
    receive(controller, "UpdateState")
    controller.controls.mode.setCurrentIndex(controller.controls.mode.findData("private"))
    receive(controller, "Assist")
    controller.player.play.assert_not_called()
    controller.controls.mode.setCurrentIndex(controller.controls.mode.findData("all"))
    receive(controller, "Assist")
    assert controller.player.play.call_count == 1
    controller.controls.volume.setValue(30)
    assert controller.config.volume == 30
    controller.player.set_volume.assert_called_with(30)
    controller.controls.mode.setCurrentIndex(controller.controls.mode.findData("never"))
    assert len(controller.config.rules) == 1
    receive(controller, "Assist")
    assert controller.player.play.call_count == 1


def test_pending_saves_should_use_a_short_timer_and_stop_when_replay_starts(
    controller: SoundAlertController,
) -> None:
    configure(controller, make_rule(SoundTrigger.SAVE))
    receive(controller, "UpdateState")
    receive(controller, "Save")
    assert controller.timer.isActive()
    receive(controller, "UpdateState", replay=True)
    controller.clock.return_value = 101
    controller.timer.timeout.emit()

    controller.player.play.assert_not_called()
    assert not controller.timer.isActive()


def test_save_failure_should_revert_controls_and_preserve_the_previous_rules(
    controller: SoundAlertController, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(controller, make_rule())
    before = controller.config
    failed = Mock()
    controller.failed.connect(failed)
    monkeypatch.setattr(
        controller.store, "set_setting", Mock(side_effect=sqlite3.OperationalError("locked"))
    )

    controller.controls.mode.setCurrentIndex(controller.controls.mode.findData("never"))

    failed.assert_called_once()
    assert controller.config == before
    assert controller.controls.mode.currentData() == "all"
    assert parse_sound_config(controller.store.setting("sound_alerts")) == before


def test_audio_error_should_be_visible_without_removing_the_rule_or_opening_a_modal(
    controller: SoundAlertController,
) -> None:
    configure(controller, make_rule())
    controller.controls.table.selectRow(0)
    controller.controls.edit_button.click()

    controller.player.failed.emit("Unsupported codec")

    assert "Unsupported codec" in controller.controls.status.text()
    assert "Unsupported codec" in controller.controls.editor.status.text()
    assert len(controller.config.rules) == 1


def test_sound_settings_should_restore_mode_volume_and_rules_without_writing(
    controller: SoundAlertController, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(controller, make_rule(), mode=SoundAlertMode.PRIVATE)
    controller.controls.volume.setValue(45)
    save = Mock(wraps=controller.store.set_setting)
    monkeypatch.setattr(controller.store, "set_setting", save)
    controls = SoundAlertSettings()
    restored = SoundAlertController(
        controls,
        controller.live,
        controller.store,
        controller.parent(),
        player=SilentPlayer(controller.parent()),
    )
    try:
        assert restored.config == controller.config
        assert controls.mode.currentData() == "private"
        assert controls.volume.value() == 45
        assert controls.table.rowCount() == 1
        save.assert_not_called()
    finally:
        restored.shutdown()
        controls.deleteLater()
        restored.deleteLater()


def test_shutdown_should_stop_playback_pending_rules_and_the_editor(
    controller: SoundAlertController,
) -> None:
    configure(controller, make_rule(SoundTrigger.SAVE))
    receive(controller, "UpdateState")
    receive(controller, "Save")
    controller.controls.add_button.click()

    controller.shutdown()
    controller.clock.return_value = 101
    controller.timer.timeout.emit()
    receive(controller, "Save")

    assert controller.controls.editor is None
    assert not controller.timer.isActive()
    controller.player.play.assert_not_called()


def test_sound_editor_should_translate_roles_and_choices_without_changing_rule_identity(
    controller: SoundAlertController, application: QApplication
) -> None:
    configure(controller, make_rule(SoundTrigger.DEMOLISHED, PlayerScope.TEAMMATES))
    controller.controls.table.selectRow(0)
    controller.controls.edit_button.click()
    language_manager().set_language("en")
    application.processEvents()

    assert controller.controls.editor.subject_label.text() == "Demolished player:"
    assert controller.controls.editor.scope.currentText() == "My teammates (excluding me)"
    assert controller.controls.table.item(0, 1).text() == "Demolition received"
    assert controller.config.rules[0].id == make_rule().id
