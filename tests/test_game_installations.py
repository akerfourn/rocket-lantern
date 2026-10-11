"""Launcher discovery uses isolated files, never the machine's real libraries."""

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest

from rocket_lantern.game_installations import (
    MAX_METADATA_SIZE,
    DiscoverySources,
    detect_installations,
    windows_sources,
)
from rocket_lantern.steam_keyvalues import parse_keyvalues


def make_game(directory: Path, *, filename: str = "DefaultStatsAPI.ini") -> Path:
    config = directory / "TAGame/Config"
    config.mkdir(parents=True)
    executable = directory / "Binaries/Win64/RocketLeague.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"synthetic executable")
    if filename:
        (config / filename).write_text("[TAGame.MatchStatsExporter_TA]\n", encoding="utf-8")
    return directory


def write_manifest(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def quoted_path(path: Path) -> str:
    return json.dumps(str(path), ensure_ascii=False)


def test_steam_should_find_custom_game_folders_in_multiple_declared_libraries(
    tmp_path: Path,
) -> None:
    steam = tmp_path / "Steam"
    libraries = [tmp_path / "Library one", tmp_path / "Bibliothèque two"]
    games = [make_game(library / "steamapps/common/Custom RL") for library in libraries]
    folders = steam / "steamapps/libraryfolders.vdf"
    folders.parent.mkdir(parents=True)
    entries = []
    for index, library in enumerate(libraries):
        entries.append(f'"{index}" {{ "path" {quoted_path(library)} "apps" {{}} }}')
        (library / "steamapps/appmanifest_252950.acf").write_text(
            '"AppState" { "appid" "252950" "installdir" "Custom RL" }', encoding="utf-8"
        )
    folders.write_text('"libraryfolders" { ' + " ".join(entries) + " }", encoding="utf-8")

    report = detect_installations(DiscoverySources(steam_roots=(steam,)))

    assert {entry.directory for entry in report.installations} == set(games)
    assert all(entry.launcher == "Steam" for entry in report.installations)
    assert report.warnings == 0


def test_steam_should_read_legacy_libraries_and_check_each_launcher_root(tmp_path: Path) -> None:
    roots = [tmp_path / "Steam A", tmp_path / "Steam B"]
    library = tmp_path / "Old library"
    first = make_game(roots[1] / "steamapps/common/rocketleague")
    second = make_game(library / "steamapps/common/rocketleague")
    folders = roots[0] / "config/libraryfolders.vdf"
    folders.parent.mkdir(parents=True)
    folders.write_text(
        f'"LibraryFolders" {{ "TimeNextStatsReport" "123" "1" {quoted_path(library)} }}',
        encoding="utf-8",
    )

    report = detect_installations(DiscoverySources(steam_roots=tuple(roots)))

    assert {entry.directory for entry in report.installations} == {first, second}


def test_epic_should_find_multiple_custom_locations_and_deduplicate_manifests(
    tmp_path: Path,
) -> None:
    first = make_game(tmp_path / "Drive D/RL")
    second = make_game(tmp_path / "Drive E/Rocket League", filename="TAStatsAPI.ini")
    manifests = tmp_path / "Epic manifests"
    write_manifest(manifests / "sugar.item", {"InstallLocation": str(first)})
    write_manifest(manifests / "duplicate.item", {"InstallLocation": str(first)})
    installed = tmp_path / "LauncherInstalled.dat"
    write_manifest(
        installed,
        {"InstallationList": [{"InstallLocation": str(first)}, {"InstallLocation": str(second)}]},
    )

    report = detect_installations(
        DiscoverySources(epic_manifest_directories=(manifests,), epic_installed_files=(installed,))
    )

    assert {entry.directory for entry in report.installations} == {first, second}
    assert all(entry.launcher == "Epic Games" for entry in report.installations)
    assert report.warnings == 0


def test_discovery_should_prefer_ta_file_and_preserve_game_files(tmp_path: Path) -> None:
    game = make_game(tmp_path / "Epic Games/rocketleague")
    ta_file = game / "TAGame/Config/TAStatsAPI.ini"
    ta_file.write_text("PacketSendRate=10\n", encoding="utf-8")

    report = detect_installations(DiscoverySources(epic_game_roots=(game.parent,)))

    assert len(report.installations) == 1
    assert report.installations[0].config_file == ta_file
    assert report.installations[0].config_directory == ta_file.parent
    assert ta_file.read_text(encoding="utf-8") == "PacketSendRate=10\n"


def test_discovery_should_report_existing_config_folder_even_when_ini_is_missing(
    tmp_path: Path,
) -> None:
    game = make_game(tmp_path / "Epic Games/Rocket League", filename="")

    report = detect_installations(DiscoverySources(epic_game_roots=(game.parent,)))

    assert len(report.installations) == 1
    assert report.installations[0].config_file is None


def test_discovery_should_ignore_stale_manifests_unrelated_games_and_relative_paths(
    tmp_path: Path,
) -> None:
    manifests = tmp_path / "manifests"
    unrelated = tmp_path / "Other game/TAGame/Config"
    unrelated.mkdir(parents=True)
    for index, location in enumerate([str(tmp_path / "removed"), str(unrelated.parents[1]), "RL"]):
        write_manifest(manifests / f"{index}.item", {"InstallLocation": location})

    report = detect_installations(DiscoverySources(epic_manifest_directories=(manifests,)))

    assert report.installations == ()
    assert report.warnings == 0


def test_steam_should_reject_manifest_path_outside_library_common_folder(tmp_path: Path) -> None:
    library = tmp_path / "Steam"
    make_game(tmp_path / "Escaped game")
    manifest = library / "steamapps/appmanifest_252950.acf"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        f'"AppState" {{ "installdir" {quoted_path(tmp_path / "Escaped game")} }}',
        encoding="utf-8",
    )

    report = detect_installations(DiscoverySources(steam_roots=(library,)))

    assert report.installations == ()


def test_discovery_should_keep_valid_results_when_other_metadata_is_malformed(
    tmp_path: Path,
) -> None:
    game = make_game(tmp_path / "Game")
    manifests = tmp_path / "Manifests"
    write_manifest(manifests / "valid.item", {"InstallLocation": str(game)})
    (manifests / "broken.item").write_text("{broken", encoding="utf-8")
    steam = tmp_path / "Steam"
    folders = steam / "config/libraryfolders.vdf"
    folders.parent.mkdir(parents=True)
    folders.write_text('"libraryfolders" {', encoding="utf-8")

    report = detect_installations(
        DiscoverySources(steam_roots=(steam,), epic_manifest_directories=(manifests,))
    )

    assert [entry.directory for entry in report.installations] == [game]
    assert report.warnings == 2


def test_discovery_should_report_unreadable_sources_without_losing_other_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = make_game(tmp_path / "Epic Games/rocketleague")
    blocked = tmp_path / "blocked"
    original = Path.iterdir

    def read_directory(path: Path) -> Iterator[Path]:
        if path == blocked:
            raise PermissionError("synthetic access denied")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", read_directory)
    report = detect_installations(
        DiscoverySources(epic_manifest_directories=(blocked,), epic_game_roots=(game.parent,))
    )

    assert [entry.directory for entry in report.installations] == [game]
    assert report.warnings == 1


def test_discovery_should_reject_oversized_metadata(tmp_path: Path) -> None:
    manifest = tmp_path / "Manifests/large.item"
    manifest.parent.mkdir()
    manifest.write_bytes(b" " * (MAX_METADATA_SIZE + 1))

    report = detect_installations(DiscoverySources(epic_manifest_directories=(manifest.parent,)))

    assert report.installations == ()
    assert report.warnings == 1


def test_discovery_should_not_inspect_windows_sources_on_other_platforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_reader = Mock()
    monkeypatch.setattr("rocket_lantern.game_installations.sys.platform", "linux")
    monkeypatch.setattr("rocket_lantern.game_installations.windows_sources", source_reader)

    report = detect_installations()

    assert not report.supported
    source_reader.assert_not_called()


def test_windows_sources_should_use_registry_and_environment_locations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steam = tmp_path / "Custom Steam"
    epic = tmp_path / "Custom Epic data"
    reader = Mock(side_effect=[([steam], 0), ([steam], 0), ([epic], 1)])
    monkeypatch.setattr("rocket_lantern.game_installations._registry_paths", reader)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Programs"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "Programs32"))
    monkeypatch.setenv("ProgramData", str(tmp_path / "Data"))

    sources = windows_sources()

    assert steam in sources.steam_roots
    assert epic / "Manifests" in sources.epic_manifest_directories
    assert (
        tmp_path / "Data/Epic/UnrealEngineLauncher/LauncherInstalled.dat"
        in sources.epic_installed_files
    )
    assert sources.warnings == 1


def test_keyvalues_should_preserve_unicode_and_decode_escaped_paths_and_comments() -> None:
    parsed = parse_keyvalues('// comment\n"libraryfolders" { "0" { "path" "D:\\\\Jeux\\\\Été" } }')

    assert parsed == {"libraryfolders": {"0": {"path": "D:\\Jeux\\Été"}}}


@pytest.mark.parametrize("contents", ['"key"', '"key" {', '"key" "unterminated', "}"])
def test_keyvalues_should_reject_malformed_structure(contents: str) -> None:
    with pytest.raises(ValueError, match="Steam KeyValues"):
        parse_keyvalues(contents)
