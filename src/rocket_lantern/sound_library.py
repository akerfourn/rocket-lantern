"""Resolve Windows sound associations and import local audio into application data."""

import hashlib
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from rocket_lantern.i18n import DisplayText
from rocket_lantern.i18n import text as T
from rocket_lantern.sound_alerts import AUDIO_EXTENSIONS, WINDOWS_SOUNDS, SoundKind, SoundRef

MAX_SOUND_BYTES = 25 * 1024 * 1024


def sound_title(sound: SoundRef) -> DisplayText:
    if sound.kind == SoundKind.WINDOWS:
        return WINDOWS_SOUNDS[sound.value]
    return sound.name or sound.value


def windows_sound_path(alias: str) -> Path | None:
    if sys.platform != "win32" or alias not in WINDOWS_SOUNDS:
        return None
    import winreg

    key_name = rf"AppEvents\Schemes\Apps\.Default\{alias}"
    for scheme in (".Current", ".Default"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name + "\\" + scheme) as key:
                value, _ = winreg.QueryValueEx(key, "")
        except FileNotFoundError:
            continue
        # An explicitly empty current association means the user disabled this sound.
        if not isinstance(value, str) or not value.strip():
            return None
        return Path(os.path.expandvars(value.strip().strip('"')))
    return None


class SoundLibrary:
    def __init__(self, data_directory: Path | None) -> None:
        self.directory: Path | None = None
        if data_directory is not None:
            self.directory = data_directory / "sounds"

    def resolve(self, sound: SoundRef) -> Path:
        if sound.kind == SoundKind.WINDOWS:
            path = windows_sound_path(sound.value)
            if path is None or not path.is_file():
                raise OSError(str(T("Ce son Windows est absent ou désactivé.")))
            return path
        if self.directory is None or Path(sound.value).name != sound.value:
            raise OSError(str(T("Le fichier audio importé est introuvable.")))
        path = self.directory / sound.value
        if not path.is_file():
            raise OSError(str(T("Le fichier audio importé est introuvable.")))
        return path

    def import_sound(self, source: Path) -> SoundRef:
        extension = source.suffix.lower()
        if extension not in AUDIO_EXTENSIONS:
            raise ValueError(str(T("Ce format audio n’est pas pris en charge.")))
        if self.directory is None:
            raise OSError(str(T("Le dossier des sons est indisponible.")))
        if not source.is_file():
            raise OSError(str(T("Le fichier audio est introuvable.")))
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        digest = hashlib.sha256()
        size = 0
        try:
            with (
                source.open("rb") as reader,
                NamedTemporaryFile(dir=self.directory, prefix=".import-", delete=False) as writer,
            ):
                temporary = Path(writer.name)
                while chunk := reader.read(64 * 1024):
                    size += len(chunk)
                    if size > MAX_SOUND_BYTES:
                        raise ValueError(str(T("Le fichier audio dépasse 25 Mo.")))
                    digest.update(chunk)
                    writer.write(chunk)
            if size == 0:
                raise ValueError(str(T("Le fichier audio est vide.")))
            filename = digest.hexdigest() + extension
            os.replace(temporary, self.directory / filename)
            temporary = None
            return SoundRef(SoundKind.FILE, filename, source.name[:255])
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
