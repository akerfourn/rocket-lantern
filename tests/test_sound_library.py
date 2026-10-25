"""Imported clips remain local and independent from their original location."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from rocket_lantern import sound_library
from rocket_lantern.sound_alerts import SoundKind, SoundRef
from rocket_lantern.sound_library import SoundLibrary


def test_import_should_copy_a_common_audio_format_and_keep_it_after_source_is_moved(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Confirmation.MP3"
    source.write_bytes(b"fixture data; decoding is tested separately")
    library = SoundLibrary(tmp_path / "data")

    sound = library.import_sound(source)
    source.unlink()

    assert sound.kind == SoundKind.FILE
    assert sound.name == "Confirmation.MP3"
    assert sound.value.endswith(".mp3")
    assert library.resolve(sound).read_bytes() == b"fixture data; decoding is tested separately"


def test_reimport_should_reuse_identical_content_without_creating_another_asset(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sound.flac"
    source.write_bytes(b"same audio")
    library = SoundLibrary(tmp_path / "data")
    first = library.import_sound(source)

    second = library.import_sound(source)

    assert second == first
    assert len(list(library.directory.iterdir())) == 1


@pytest.mark.parametrize("case", ["empty", "too_large", "unsupported"])
def test_invalid_import_should_leave_no_partial_audio_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    source = tmp_path / "sound.mp3"
    payload = b""
    if case == "too_large":
        payload = b"12345"
        monkeypatch.setattr(sound_library, "MAX_SOUND_BYTES", 4)
    elif case == "unsupported":
        source = source.with_suffix(".exe")
    source.write_bytes(payload)
    library = SoundLibrary(tmp_path / "data")

    with pytest.raises(ValueError):
        library.import_sound(source)

    assert not library.directory.exists() or list(library.directory.iterdir()) == []
    assert source.exists()


def test_windows_sound_should_be_resolved_locally_without_importing_or_copying_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_sound = tmp_path / "windows.wav"
    system_sound.write_bytes(b"system sound")
    resolver = Mock(return_value=system_sound)
    monkeypatch.setattr(sound_library, "windows_sound_path", resolver)
    library = SoundLibrary(tmp_path / "data")

    assert library.resolve(SoundRef()) == system_sound

    resolver.assert_called_once_with("SystemAsterisk")
    assert not library.directory.exists()


def test_missing_windows_sound_should_report_an_unavailable_association(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sound_library, "windows_sound_path", lambda _: None)

    with pytest.raises(OSError, match="absent ou désactivé"):
        SoundLibrary(None).resolve(SoundRef())


def test_imported_reference_should_never_escape_the_sound_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"unrelated")
    library = SoundLibrary(tmp_path / "data")

    with pytest.raises(OSError, match="introuvable"):
        library.resolve(SoundRef(SoundKind.FILE, "../../outside.mp3"))
