"""Independent asynchronous Qt players for overlapping clips; load multimedia only on use."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

if TYPE_CHECKING:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

MAX_VOICES = 16
MAX_CLIP_MS = 60_000


@dataclass
class AudioVoice:
    player: QMediaPlayer
    output: QAudioOutput
    deadline: QTimer


class SoundPlayer(QObject):
    failed = Signal(str)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._voices: dict[int, AudioVoice] = {}
        self._next_voice = 0

    @property
    def active_count(self) -> int:
        return len(self._voices)

    def _create_voice(self) -> AudioVoice:
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

        player = QMediaPlayer(self)
        output = QAudioOutput(player)
        player.setAudioOutput(output)
        deadline = QTimer(player)
        deadline.setSingleShot(True)
        return AudioVoice(player, output, deadline)

    def play(self, path: Path, volume: int) -> None:
        if volume <= 0:
            return
        if len(self._voices) >= MAX_VOICES:
            self._release(next(iter(self._voices)))
        identifier = self._next_voice
        self._next_voice += 1
        try:
            voice = self._create_voice()
        except (ImportError, OSError, RuntimeError) as error:
            self.failed.emit(str(error))
            return
        self._voices[identifier] = voice
        voice.output.setVolume(min(volume, 100) / 100)
        voice.deadline.timeout.connect(lambda: self._release(identifier))
        voice.player.mediaStatusChanged.connect(lambda status: self._status(identifier, status))
        voice.player.errorOccurred.connect(lambda *_: self._error(identifier))
        voice.player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        if identifier not in self._voices:
            return
        voice.deadline.start(MAX_CLIP_MS)
        voice.player.play()

    def _status(self, identifier: int, status: object) -> None:
        from PySide6.QtMultimedia import QMediaPlayer

        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._release(identifier)
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._error(identifier)

    def _error(self, identifier: int) -> None:
        voice = self._voices.get(identifier)
        if voice is None:
            return
        message = voice.player.errorString()
        self._release(identifier)
        self.failed.emit(message)

    def _release(self, identifier: int) -> None:
        voice = self._voices.pop(identifier, None)
        if voice is None:
            return
        voice.deadline.stop()
        voice.player.stop()
        voice.player.deleteLater()

    def set_volume(self, volume: int) -> None:
        for voice in self._voices.values():
            voice.output.setVolume(max(0, min(volume, 100)) / 100)

    def stop(self) -> None:
        for identifier in list(self._voices):
            self._release(identifier)
