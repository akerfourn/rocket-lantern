"""Exercise real MP3/WAV decoders concurrently without opening speakers or microphones."""

from pathlib import Path

from PySide6.QtWidgets import QApplication

from rocket_lantern.sound_smoke import verify_sound_decoding


def test_audio_backend_should_decode_mp3_and_wav_concurrently_without_an_audio_device(
    application: QApplication,
    tmp_path: Path,
) -> None:
    verify_sound_decoding(tmp_path)
