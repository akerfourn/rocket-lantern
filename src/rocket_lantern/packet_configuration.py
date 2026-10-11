"""Read and explicitly update only PacketSendRate in local game INI files."""

import codecs
import logging
import math
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from rocket_lantern.game_installations import GameInstallation

LOGGER = logging.getLogger(__name__)
SECTION_NAME = "tagame.matchstatsexporter_ta"
MAX_CONFIG_SIZE = 1024 * 1024
SECTION = re.compile(r"^\s*\[([^\]\r\n]+)\]\s*(?:[;#].*)?$")
ASSIGNMENT = re.compile(r"^(\s*PacketSendRate\s*=\s*)([^;#\r\n]*)([;#].*)?$", re.IGNORECASE)


class ConfigurationProblem(StrEnum):
    MISSING = "missing"
    UNREADABLE = "unreadable"
    INVALID = "invalid"
    AMBIGUOUS = "ambiguous"


class ConfigurationChangedError(ValueError):
    """A checked configuration changed; do not overwrite another editor's work."""


class AmbiguousConfigurationError(ValueError):
    """Duplicate sections or keys cannot be rewritten without guessing precedence."""


@dataclass(frozen=True)
class IniDocument:
    path: Path
    contents: bytes
    text: str
    encoding: str
    prefix: bytes = b""


@dataclass(frozen=True)
class RateConfiguration:
    installation: GameInstallation
    document: IniDocument | None = None
    rate: float | None = None
    source: Path | None = None
    inherited: IniDocument | None = None
    problem: ConfigurationProblem | None = None

    @property
    def can_apply(self) -> bool:
        return self.document is not None and self.problem in (None, ConfigurationProblem.INVALID)


@dataclass(frozen=True)
class IniLocation:
    start: int | None
    end: int
    key: int | None
    value: str | None


def _read_document(path: Path) -> IniDocument:
    if path.is_symlink():
        raise ValueError("Linked configuration files cannot be edited safely")
    with path.open("rb") as stream:
        contents = stream.read(MAX_CONFIG_SIZE + 1)
    if len(contents) > MAX_CONFIG_SIZE:
        raise ValueError("Configuration file exceeds size limit")
    if contents.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        raise ValueError("Unsupported UTF-32 configuration file")
    for prefix, encoding in (
        (codecs.BOM_UTF8, "utf-8"),
        (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"),
    ):
        if contents.startswith(prefix):
            text = contents[len(prefix) :].decode(encoding)
            if "\x00" in text:
                raise ValueError("Unsupported binary configuration file")
            return IniDocument(path, contents, text, encoding, prefix)
    try:
        text = contents.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        text = contents.decode("cp1252")
        encoding = "cp1252"
    if "\x00" in text:
        raise ValueError("Unsupported binary configuration file")
    return IniDocument(path, contents, text, encoding)


def _locate(text: str) -> IniLocation:
    start = None
    key = None
    value = None
    lines = text.splitlines(keepends=True)
    end = len(lines)
    active = False
    for index, line in enumerate(lines):
        section = SECTION.fullmatch(line.rstrip("\r\n"))
        if section is not None:
            if active:
                end = index
            active = section[1].strip().casefold() == SECTION_NAME
            if active:
                if start is not None:
                    raise AmbiguousConfigurationError("Ambiguous Stats API sections")
                start = index
            continue
        assignment = ASSIGNMENT.fullmatch(line.rstrip("\r\n"))
        if active and assignment is not None:
            if key is not None:
                raise AmbiguousConfigurationError("Ambiguous PacketSendRate keys")
            key = index
            value = assignment[2].strip()
    return IniLocation(start, end, key, value)


def _preferred_file(installation: GameInstallation) -> Path | None:
    for name in ("TAStatsAPI.ini", "DefaultStatsAPI.ini"):
        path = installation.config_directory / name
        if path.is_file():
            return path
    return None


def read_configuration(installation: GameInstallation) -> RateConfiguration:
    """Read the installation override, falling back to defaults for an absent key."""
    document = None
    inherited = None
    try:
        path = _preferred_file(installation)
        if path is None:
            return RateConfiguration(installation, problem=ConfigurationProblem.MISSING)
        document = _read_document(path)
        try:
            location = _locate(document.text)
            if location.value is None and path.name == "TAStatsAPI.ini":
                default = path.with_name("DefaultStatsAPI.ini")
                if default.is_file():
                    inherited = _read_document(default)
                    location = _locate(inherited.text)
        except AmbiguousConfigurationError:
            return RateConfiguration(installation, document, problem=ConfigurationProblem.AMBIGUOUS)
        source = None
        if location.value is not None:
            source = document.path
            if inherited is not None:
                source = inherited.path
        try:
            rate = 0.0
            if location.value is not None:
                rate = float(location.value)
            if not math.isfinite(rate) or rate < 0:
                raise ValueError("Invalid PacketSendRate")
        except ValueError:
            return RateConfiguration(
                installation,
                document,
                source=source,
                inherited=inherited,
                problem=ConfigurationProblem.INVALID,
            )
        return RateConfiguration(installation, document, rate, source, inherited)
    except (OSError, ValueError) as error:
        LOGGER.warning(
            "Cannot read Stats API configuration for %s: %s", installation.directory, error
        )
        return RateConfiguration(installation, problem=ConfigurationProblem.UNREADABLE)


def _updated_contents(document: IniDocument, rate: int) -> bytes:
    location = _locate(document.text)
    lines = document.text.splitlines(keepends=True)
    match = re.search(r"\r\n|\n|\r", document.text)
    newline = "\n"
    if match is not None:
        newline = match[0]
    if location.key is not None:
        line = lines[location.key]
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        assignment = ASSIGNMENT.fullmatch(body)
        if assignment is None:
            raise ValueError("PacketSendRate assignment disappeared")
        value = assignment[2]
        spacing = value[len(value.rstrip()) :]
        lines[location.key] = assignment[1] + str(rate) + spacing + (assignment[3] or "") + ending
    else:
        index = location.end
        if index > 0 and not lines[index - 1].endswith(("\n", "\r")):
            lines[index - 1] += newline
        if location.start is None:
            lines.append("[TAGame.MatchStatsExporter_TA]" + newline)
            index = len(lines)
        lines.insert(index, f"PacketSendRate={rate}" + newline)
    return document.prefix + "".join(lines).encode(document.encoding)


def _verify_unchanged(configuration: RateConfiguration) -> None:
    if read_configuration(configuration.installation) != configuration:
        raise ConfigurationChangedError("Configuration changed; check again")


def _backup(document: IniDocument) -> Path:
    for index in range(1000):
        suffix = ""
        if index:
            suffix = f".{index}"
        backup = document.path.with_name(document.path.name + f".rocketlantern{suffix}.bak")
        try:
            stream = backup.open("xb")
        except FileExistsError:
            continue
        try:
            with stream:
                stream.write(document.contents)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            backup.unlink(missing_ok=True)
            raise
        return backup
    raise OSError("Too many existing configuration backups")


def apply_packet_rate(
    configuration: RateConfiguration, rate: int
) -> tuple[RateConfiguration, Path]:
    """Back up and atomically replace one checked file, preserving other settings."""
    if type(rate) is not int or not 1 <= rate <= 120:
        raise ValueError("PacketSendRate must be an integer between 1 and 120")
    if not configuration.can_apply or configuration.document is None:
        raise ValueError("Configuration cannot be safely updated")
    document = configuration.document
    updated = _updated_contents(document, rate)
    _verify_unchanged(configuration)
    mode = stat.S_IMODE(document.path.stat().st_mode)
    if not mode & stat.S_IWUSR:
        raise PermissionError("Configuration file is read-only")
    backup = _backup(document)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=document.path.parent, prefix=".rocketlantern-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        _verify_unchanged(configuration)
        os.replace(temporary, document.path)
        if document.path.read_bytes() != updated:
            raise OSError("Written configuration could not be verified")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return read_configuration(configuration.installation), backup
