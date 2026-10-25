"""Verify bundled audio decoders concurrently, without opening an audio device."""

import base64
import wave
from functools import partial
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer, QUrl


def verify_sound_decoding(directory: Path) -> None:
    """Decode a silent MP3 and WAV together; no speaker, microphone or network is used."""
    from PySide6.QtMultimedia import QAudioBuffer, QAudioBufferOutput, QMediaPlayer

    fixture = Path(__file__).parent / "assets/validation/silence.mp3.b64"
    mp3 = directory / "codec-test.mp3"
    mp3.write_bytes(base64.b64decode(fixture.read_bytes()))
    wav = directory / "codec-test.wav"
    with wave.open(str(wav), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(44100)
        writer.writeframes(bytes(8820))
    pending = {mp3, wav}
    decoded = {path: 0 for path in pending}
    failures: list[str] = []
    players: list[QMediaPlayer] = []
    loop = QEventLoop()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)

    def buffer_received(path: Path, buffer: QAudioBuffer) -> None:
        decoded[path] += buffer.byteCount()

    def status_changed(path: Path, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            pending.discard(path)
            if not pending:
                loop.quit()

    def error_occurred(path: Path, error: QMediaPlayer.Error, message: str) -> None:
        failures.append(f"{path.suffix}: {message}")
        loop.quit()

    try:
        for path in tuple(pending):
            player = QMediaPlayer()
            players.append(player)
            output = QAudioBufferOutput(player)
            output.audioBufferReceived.connect(partial(buffer_received, path))
            player.setAudioBufferOutput(output)
            player.mediaStatusChanged.connect(partial(status_changed, path))
            player.errorOccurred.connect(partial(error_occurred, path))
            player.setSource(QUrl.fromLocalFile(str(path)))
        deadline.start(5000)
        for player in players:
            player.play()
        if pending and not failures:
            loop.exec()
        if failures:
            raise RuntimeError("Bundled audio decoding failed: " + "; ".join(failures))
        if pending or not all(decoded.values()):
            raise RuntimeError("Bundled MP3/WAV audio decoding did not complete")
    finally:
        deadline.stop()
        for player in players:
            player.stop()
            player.deleteLater()
