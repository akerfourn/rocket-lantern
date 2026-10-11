"""On-demand local Steam/Epic discovery; never scan whole drives or edit games."""

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from rocket_lantern.steam_keyvalues import KeyValues, parse_keyvalues

LOGGER = logging.getLogger(__name__)
MAX_METADATA_SIZE = 2 * 1024 * 1024


@dataclass(frozen=True)
class DiscoverySources:
    """Explicit input paths allow filesystem tests without real launcher access."""

    steam_roots: tuple[Path, ...] = ()
    epic_manifest_directories: tuple[Path, ...] = ()
    epic_installed_files: tuple[Path, ...] = ()
    epic_game_roots: tuple[Path, ...] = ()
    warnings: int = 0


@dataclass(frozen=True)
class GameInstallation:
    launcher: str
    directory: Path
    config_file: Path | None

    @property
    def config_directory(self) -> Path:
        return self.directory / "TAGame" / "Config"


@dataclass(frozen=True)
class DiscoveryReport:
    installations: tuple[GameInstallation, ...] = ()
    warnings: int = 0
    supported: bool = True


def _registry_paths(key: str, name: str) -> tuple[list[Path], int]:
    import winreg

    paths: list[Path] = []
    warnings = 0
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as handle:
                    value, _ = winreg.QueryValueEx(handle, name)
                if isinstance(value, str) and value.strip():
                    paths.append(Path(os.path.expandvars(value)))
            except FileNotFoundError:
                continue
            except OSError as error:
                LOGGER.warning("Cannot read launcher registry key %s: %s", key, error)
                warnings += 1
    return paths, warnings


def windows_sources() -> DiscoverySources:
    """Read launcher locations only when discovery is explicitly requested."""
    steam, warnings = _registry_paths(r"Software\Valve\Steam", "SteamPath")
    install_paths, errors = _registry_paths(r"Software\Valve\Steam", "InstallPath")
    steam.extend(install_paths)
    warnings += errors
    epic, errors = _registry_paths(r"Software\Epic Games\EpicGamesLauncher", "AppDataPath")
    warnings += errors
    manifests: list[Path] = []
    installed: list[Path] = []
    game_roots: list[Path] = []
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        directory = os.environ.get(variable)
        if directory:
            steam.append(Path(directory) / "Steam")
            game_roots.append(Path(directory) / "Epic Games")
    program_data = os.environ.get("ProgramData")
    if program_data:
        epic.append(Path(program_data) / "Epic" / "EpicGamesLauncher" / "Data")
        installed.append(
            Path(program_data) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat"
        )
    for directory in epic:
        manifests.extend((directory / "Manifests", directory / "Data" / "Manifests"))
    return DiscoverySources(
        tuple(steam), tuple(manifests), tuple(installed), tuple(game_roots), warnings
    )


class InstallationSearch:
    """Keep partial results when a library is absent, inaccessible or malformed."""

    def __init__(self, sources: DiscoverySources) -> None:
        self.sources = sources
        self.warnings = sources.warnings
        self.installations: dict[str, GameInstallation] = {}

    def _warn(self, path: Path, error: Exception) -> None:
        self.warnings += 1
        LOGGER.warning("Cannot inspect launcher path %s: %s", path, error)

    def _read(self, path: Path) -> str | None:
        try:
            with path.open("rb") as stream:
                contents = stream.read(MAX_METADATA_SIZE + 1)
            if len(contents) > MAX_METADATA_SIZE:
                raise ValueError("Launcher metadata exceeds size limit")
            return contents.decode("utf-8-sig")
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            self._warn(path, error)
            return None

    def _vdf(self, path: Path) -> KeyValues:
        contents = self._read(path)
        if contents is None:
            return {}
        try:
            return parse_keyvalues(contents)
        except ValueError as error:
            self._warn(path, error)
            return {}

    def _json(self, path: Path) -> object:
        contents = self._read(path)
        if contents is None:
            return None
        try:
            return json.loads(contents)
        except (ValueError, RecursionError) as error:
            self._warn(path, error)
            return None

    def _add(self, launcher: str, directory: Path) -> None:
        try:
            if not directory.is_absolute():
                return
            directory = directory.resolve()
            config = directory / "TAGame" / "Config"
            executable = directory / "Binaries" / "Win64" / "RocketLeague.exe"
            if not executable.is_file() or not config.is_dir():
                return
            config_file = None
            for name in ("TAStatsAPI.ini", "DefaultStatsAPI.ini"):
                candidate = config / name
                if candidate.is_file():
                    config_file = candidate
                    break
            key = os.path.normcase(str(directory))
            self.installations.setdefault(key, GameInstallation(launcher, directory, config_file))
        except (OSError, ValueError) as error:
            self._warn(directory, error)

    def _steam(self) -> None:
        libraries = set(self.sources.steam_roots)
        for root in self.sources.steam_roots:
            for relative in ("steamapps/libraryfolders.vdf", "config/libraryfolders.vdf"):
                folders = self._vdf(root / relative).get("libraryfolders", {})
                if not isinstance(folders, dict):
                    continue
                for number, entry in folders.items():
                    if not number.isdecimal():
                        continue
                    path = entry
                    if isinstance(entry, dict):
                        path = entry.get("path", "")
                    if isinstance(path, str) and path.strip():
                        library = Path(path)
                        if library.is_absolute():
                            libraries.add(library)
        for library in sorted(libraries):
            common = library / "steamapps" / "common"
            state = self._vdf(library / "steamapps" / "appmanifest_252950.acf").get("appstate", {})
            if isinstance(state, dict):
                name = state.get("installdir")
                if isinstance(name, str) and name.strip():
                    try:
                        candidate = (common / name).resolve()
                        if candidate.is_relative_to(common.resolve()):
                            self._add("Steam", candidate)
                    except (OSError, ValueError) as error:
                        self._warn(common / name, error)
            self._add("Steam", common / "rocketleague")

    def _epic_location(self, entry: object) -> None:
        if not isinstance(entry, dict):
            return
        location = entry.get("InstallLocation")
        if isinstance(location, str) and location.strip():
            self._add("Epic Games", Path(location))

    def _epic(self) -> None:
        for directory in set(self.sources.epic_manifest_directories):
            try:
                for manifest in sorted(directory.iterdir()):
                    if manifest.suffix == ".item":
                        self._epic_location(self._json(manifest))
            except FileNotFoundError:
                continue
            except OSError as error:
                self._warn(directory, error)
        for path in set(self.sources.epic_installed_files):
            contents = self._json(path)
            if isinstance(contents, dict):
                entries = contents.get("InstallationList", [])
                if isinstance(entries, list):
                    for entry in entries:
                        self._epic_location(entry)
        for directory in self.sources.epic_game_roots:
            for name in ("rocketleague", "RocketLeague", "Rocket League"):
                self._add("Epic Games", directory / name)

    def run(self) -> DiscoveryReport:
        self._steam()
        self._epic()
        installations = sorted(
            self.installations.values(), key=lambda item: (item.launcher, str(item.directory))
        )
        return DiscoveryReport(tuple(installations), self.warnings)


def detect_installations(sources: DiscoverySources | None = None) -> DiscoveryReport:
    """Search declared libraries only; no automatic calls, network or writes."""
    if sources is None:
        if sys.platform != "win32":
            return DiscoveryReport(supported=False)
        sources = windows_sources()
    return InstallationSearch(sources).run()
