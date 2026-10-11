"""INI changes preserve unrelated bytes and never target real game installations."""

import codecs
from pathlib import Path
from unittest.mock import Mock

import pytest

from rocket_lantern.game_installations import GameInstallation
from rocket_lantern.packet_configuration import (
    ConfigurationChangedError,
    ConfigurationProblem,
    apply_packet_rate,
    read_configuration,
)

SECTION = "[TAGame.MatchStatsExporter_TA]"


def make_configuration(tmp_path: Path, contents: bytes) -> tuple[GameInstallation, Path]:
    path = tmp_path / "Game/TAGame/Config/DefaultStatsAPI.ini"
    path.parent.mkdir(parents=True)
    path.write_bytes(contents)
    return GameInstallation("Steam", tmp_path / "Game", path), path


@pytest.mark.parametrize("rate", ["0", "1", "10", "60", "2.5", "150"])
def test_reader_should_read_numeric_rate_from_only_the_stats_api_section(
    tmp_path: Path,
    rate: str,
) -> None:
    contents = f"[Other]\nPacketSendRate=999\n{SECTION}\nPacketSendRate={rate}\n".encode()
    installation, path = make_configuration(tmp_path, contents)

    result = read_configuration(installation)

    assert result.rate == float(rate)
    assert result.source == path
    assert result.can_apply
    assert path.read_bytes() == contents


@pytest.mark.parametrize("value", ["NaN", "inf", "-1", "invalid", "10,5", ""])
def test_reader_should_allow_explicit_repair_of_a_single_invalid_rate(
    tmp_path: Path,
    value: str,
) -> None:
    installation, path = make_configuration(
        tmp_path, f"{SECTION}\nPacketSendRate={value}\n".encode()
    )

    checked = read_configuration(installation)
    updated, _ = apply_packet_rate(checked, 10)

    assert checked.problem == ConfigurationProblem.INVALID
    assert checked.can_apply
    assert updated.rate == 10
    assert path.read_bytes() == f"{SECTION}\nPacketSendRate=10\n".encode()


@pytest.mark.parametrize(
    "encoding,prefix",
    [
        ("utf-8", b""),
        ("utf-8", codecs.BOM_UTF8),
        ("utf-16-le", codecs.BOM_UTF16_LE),
        ("utf-16-be", codecs.BOM_UTF16_BE),
        ("cp1252", b""),
    ],
)
def test_apply_should_preserve_comments_encoding_line_endings_and_other_settings(
    tmp_path: Path,
    encoding: str,
    prefix: bytes,
) -> None:
    original = (
        f"; réglage français\r\n{SECTION}\r\n  PacketSendRate = 1.0  ; commentaire\r\n"
        "WebPort=49124\r\nPort=49123\r\n[Other]\r\nPacketSendRate=99"
    )
    contents = prefix + original.encode(encoding)
    installation, path = make_configuration(tmp_path, contents)

    updated, backup = apply_packet_rate(read_configuration(installation), 20)

    assert path.read_bytes() == prefix + original.replace("= 1.0  ;", "= 20  ;").encode(encoding)
    assert backup.read_bytes() == contents
    assert updated.rate == 20


def test_apply_should_add_missing_key_inside_the_correct_section(tmp_path: Path) -> None:
    original = f"{SECTION}\nWebPort=49124\n[Other]\nPacketSendRate=99\n".encode()
    installation, path = make_configuration(tmp_path, original)
    checked = read_configuration(installation)

    updated, _ = apply_packet_rate(checked, 10)

    assert checked.rate == 0
    assert updated.rate == 10
    assert path.read_bytes() == original.replace(b"[Other]", b"PacketSendRate=10\n[Other]")


def test_apply_should_append_missing_section_without_losing_last_line(tmp_path: Path) -> None:
    installation, path = make_configuration(tmp_path, b"[Other]\nValue=unchanged")

    updated, _ = apply_packet_rate(read_configuration(installation), 10)

    assert updated.rate == 10
    assert path.read_bytes() == f"[Other]\nValue=unchanged\n{SECTION}\nPacketSendRate=10\n".encode()


def test_reader_should_use_default_value_when_override_omits_it_and_update_only_override(
    tmp_path: Path,
) -> None:
    installation, default = make_configuration(tmp_path, f"{SECTION}\nPacketSendRate=60\n".encode())
    override = default.with_name("TAStatsAPI.ini")
    override.write_bytes(f"{SECTION}\nWebPort=49124\n".encode())

    checked = read_configuration(installation)
    updated, backup = apply_packet_rate(checked, 10)

    assert checked.rate == 60
    assert checked.source == default
    assert checked.document.path == override
    assert backup.read_bytes() == f"{SECTION}\nWebPort=49124\n".encode()
    assert updated.source == override
    assert updated.rate == 10
    assert default.read_bytes() == f"{SECTION}\nPacketSendRate=60\n".encode()


@pytest.mark.parametrize(
    "contents",
    [
        f"{SECTION}\nPacketSendRate=1\nPacketSendRate=2\n",
        f"{SECTION}\nPacketSendRate=1\n{SECTION}\nPacketSendRate=2\n",
    ],
)
def test_apply_should_refuse_ambiguous_configuration_without_creating_a_backup(
    tmp_path: Path,
    contents: str,
) -> None:
    installation, path = make_configuration(tmp_path, contents.encode())
    checked = read_configuration(installation)

    with pytest.raises(ValueError, match="cannot be safely updated"):
        apply_packet_rate(checked, 10)

    assert checked.problem == ConfigurationProblem.AMBIGUOUS
    assert not checked.can_apply
    assert path.read_bytes() == contents.encode()
    assert list(path.parent.glob("*.bak")) == []


def test_apply_should_leave_original_untouched_when_backup_cannot_be_completed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contents = f"{SECTION}\nPacketSendRate=1\n".encode()
    installation, path = make_configuration(tmp_path, contents)
    monkeypatch.setattr(
        "rocket_lantern.packet_configuration.os.fsync", Mock(side_effect=OSError("flush failed"))
    )

    with pytest.raises(OSError, match="flush failed"):
        apply_packet_rate(read_configuration(installation), 10)

    assert path.read_bytes() == contents
    assert list(path.parent.glob("*.bak")) == []


def test_reader_should_report_unreadable_inherited_default_instead_of_ambiguity(
    tmp_path: Path,
) -> None:
    installation, default = make_configuration(tmp_path, b"binary\x00data")
    override = default.with_name("TAStatsAPI.ini")
    override.write_bytes(f"{SECTION}\nWebPort=49124\n".encode())

    checked = read_configuration(installation)

    assert checked.problem == ConfigurationProblem.UNREADABLE
    assert not checked.can_apply


def test_apply_should_refuse_external_edits_since_last_check(tmp_path: Path) -> None:
    installation, path = make_configuration(tmp_path, f"{SECTION}\nPacketSendRate=1\n".encode())
    checked = read_configuration(installation)
    external = f"{SECTION}\nPacketSendRate=5\nWebPort=50000\n".encode()
    path.write_bytes(external)

    with pytest.raises(ConfigurationChangedError, match="changed; check again"):
        apply_packet_rate(checked, 10)

    assert path.read_bytes() == external
    assert list(path.parent.glob("*.bak")) == []


def test_apply_should_refuse_new_override_created_since_last_check(tmp_path: Path) -> None:
    installation, path = make_configuration(tmp_path, f"{SECTION}\nPacketSendRate=1\n".encode())
    checked = read_configuration(installation)
    override = path.with_name("TAStatsAPI.ini")
    override.write_bytes(f"{SECTION}\nPacketSendRate=20\n".encode())

    with pytest.raises(ConfigurationChangedError, match="changed; check again"):
        apply_packet_rate(checked, 10)

    assert read_configuration(installation).rate == 20
    assert path.read_bytes() == checked.document.contents


def test_apply_should_preserve_file_on_failed_replacement_and_keep_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contents = f"{SECTION}\nPacketSendRate=1\n".encode()
    installation, path = make_configuration(tmp_path, contents)
    monkeypatch.setattr(
        "rocket_lantern.packet_configuration.os.replace",
        Mock(side_effect=PermissionError("locked")),
    )

    with pytest.raises(PermissionError, match="locked"):
        apply_packet_rate(read_configuration(installation), 10)

    assert path.read_bytes() == contents
    assert path.with_name(path.name + ".rocketlantern.bak").read_bytes() == contents
    assert list(path.parent.glob(".rocketlantern-*")) == []


def test_apply_should_keep_existing_backups_and_create_another_one(tmp_path: Path) -> None:
    contents = f"{SECTION}\nPacketSendRate=1\n".encode()
    installation, path = make_configuration(tmp_path, contents)
    previous = path.with_name(path.name + ".rocketlantern.bak")
    previous.write_bytes(b"previous backup")

    _, backup = apply_packet_rate(read_configuration(installation), 10)

    assert previous.read_bytes() == b"previous backup"
    assert backup != previous
    assert backup.read_bytes() == contents


@pytest.mark.parametrize("rate", [0, 121, -1, 10.5, True])
def test_apply_should_reject_unsupported_target_without_modifying_the_file(
    tmp_path: Path,
    rate: int,
) -> None:
    contents = f"{SECTION}\nPacketSendRate=1\n".encode()
    installation, path = make_configuration(tmp_path, contents)

    with pytest.raises(ValueError, match="integer between 1 and 120"):
        apply_packet_rate(read_configuration(installation), rate)

    assert path.read_bytes() == contents


def test_reader_should_report_missing_file_without_creating_it(tmp_path: Path) -> None:
    installation = GameInstallation("Steam", tmp_path / "missing", None)

    checked = read_configuration(installation)

    assert checked.problem == ConfigurationProblem.MISSING
    assert not checked.can_apply
    assert not installation.directory.exists()


def test_apply_should_refuse_default_created_since_override_was_checked(tmp_path: Path) -> None:
    installation, default = make_configuration(tmp_path, b"unused")
    override = default.with_name("TAStatsAPI.ini")
    override.write_bytes(f"{SECTION}\nWebPort=49124\n".encode())
    default.unlink()
    checked = read_configuration(installation)
    default.write_bytes(f"{SECTION}\nPacketSendRate=60\n".encode())

    with pytest.raises(ConfigurationChangedError, match="changed; check again"):
        apply_packet_rate(checked, 10)

    assert override.read_bytes() == checked.document.contents


@pytest.mark.parametrize("contents", [b"binary\x00data", codecs.BOM_UTF32_LE + b"x\x00\x00\x00"])
def test_reader_should_refuse_unsupported_binary_or_utf32_files(
    tmp_path: Path,
    contents: bytes,
) -> None:
    installation, _ = make_configuration(tmp_path, contents)

    checked = read_configuration(installation)

    assert checked.problem == ConfigurationProblem.UNREADABLE
    assert not checked.can_apply
