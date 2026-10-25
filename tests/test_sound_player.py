"""Polyphony and bounded player lifetimes without sending audio to real devices."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from rocket_lantern.sound_player import MAX_VOICES, AudioVoice, SoundPlayer


class FakeMediaPlayer(QObject):
    mediaStatusChanged = Signal(object)
    errorOccurred = Signal(object, str)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.setSource = Mock()
        self.play = Mock()
        self.stop = Mock()

    def errorString(self) -> str:
        return "Invalid media fixture"


@pytest.fixture
def player(application: QApplication, monkeypatch: pytest.MonkeyPatch) -> SoundPlayer:
    player = SoundPlayer(application)

    def create_voice() -> AudioVoice:
        media = FakeMediaPlayer(player)
        output = Mock()
        deadline = QTimer(media)
        return AudioVoice(media, output, deadline)

    monkeypatch.setattr(player, "_create_voice", create_voice)
    yield player
    player.stop()
    player.deleteLater()


def test_simultaneous_sounds_should_have_independent_players_and_audio_outputs(
    player: SoundPlayer, tmp_path: Path
) -> None:
    path = tmp_path / "sound.mp3"

    player.play(path, 70)
    first = player._voices[0]
    player.play(path, 40)
    second = player._voices[1]

    assert player.active_count == 2
    assert first.player is not second.player
    assert first.output is not second.output
    first.player.stop.assert_not_called()
    first.output.setVolume.assert_called_once_with(0.7)
    second.output.setVolume.assert_called_once_with(0.4)


def test_finished_voice_should_release_only_its_own_player(
    player: SoundPlayer, tmp_path: Path
) -> None:
    player.play(tmp_path / "one.mp3", 70)
    player.play(tmp_path / "two.wav", 70)

    player._voices[0].deadline.timeout.emit()

    assert list(player._voices) == [1]
    player._voices[1].player.stop.assert_not_called()


def test_playback_error_should_release_resources_and_emit_a_single_failure(
    player: SoundPlayer, tmp_path: Path
) -> None:
    failed = Mock()
    player.failed.connect(failed)
    player.play(tmp_path / "broken.mp3", 70)
    media = player._voices[0].player

    media.errorOccurred.emit(1, "Invalid media fixture")
    media.errorOccurred.emit(1, "Invalid media fixture")

    assert player.active_count == 0
    failed.assert_called_once_with("Invalid media fixture")


def test_voice_limit_should_bound_resources_without_serializing_normal_playback(
    player: SoundPlayer, tmp_path: Path
) -> None:
    player.play(tmp_path / "one.mp3", 70)
    first = player._voices[0].player
    for _ in range(MAX_VOICES):
        player.play(tmp_path / "one.mp3", 70)

    assert player.active_count == MAX_VOICES
    first.stop.assert_called_once()


def test_muting_should_not_allocate_an_audio_backend_and_volume_should_apply_to_all_voices(
    player: SoundPlayer, tmp_path: Path
) -> None:
    player.play(tmp_path / "silent.mp3", 0)
    assert player.active_count == 0
    player.play(tmp_path / "one.mp3", 70)
    player.play(tmp_path / "two.mp3", 70)

    player.set_volume(25)

    for voice in player._voices.values():
        assert voice.output.setVolume.call_args.args == (0.25,)
    player.stop()
    assert player.active_count == 0
