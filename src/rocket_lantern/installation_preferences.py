"""Remember discovery paths and onboarding choices, never cached INI contents."""

import json
import logging
from pathlib import Path

from rocket_lantern.game_installations import DiscoveryReport, GameInstallation
from rocket_lantern.storage import MatchStore

LOGGER = logging.getLogger(__name__)
CACHE_KEY = "known_game_installations"
ONBOARDING_KEY = "onboarding_status"


def needs_onboarding(store: MatchStore) -> bool:
    """Offer setup to new users without interrupting an existing match tracker."""
    if store.setting(ONBOARDING_KEY) in ("completed", "skipped"):
        return False
    if store.setting("player_id") != "":
        return False
    return store.connection.execute("SELECT 1 FROM matches LIMIT 1").fetchone() is None


def load_installations(store: MatchStore) -> tuple[GameInstallation, ...]:
    """Read unverified paths from SQLite without probing launchers or game files."""
    encoded = store.setting(CACHE_KEY)
    if encoded == "":
        return ()
    try:
        entries = json.loads(encoded)
        if not isinstance(entries, list):
            raise ValueError("Expected an installation list")
        installations = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Invalid installation entry")
            launcher = entry.get("launcher")
            directory = entry.get("directory")
            if not isinstance(launcher, str) or launcher == "" or not isinstance(directory, str):
                raise ValueError("Invalid installation fields")
            if "\x00" in directory or not Path(directory).is_absolute():
                raise ValueError("Invalid installation directory")
            installations.append(GameInstallation(launcher, Path(directory), None))
        return tuple(installations)
    except (ValueError, RecursionError) as error:
        LOGGER.warning("Ignoring invalid saved installations: %s", error)
        return ()


def remember_discovery(store: MatchStore, report: DiscoveryReport) -> tuple[GameInstallation, ...]:
    """Replace complete discoveries, but preserve paths when sources were unreadable."""
    if not report.supported:
        return load_installations(store)
    installations: dict[Path, GameInstallation] = {}
    if report.warnings > 0:
        for installation in load_installations(store):
            installations[installation.directory] = installation
    for installation in report.installations:
        installations[installation.directory] = GameInstallation(
            installation.launcher, installation.directory, None
        )
    entries = [
        {"launcher": item.launcher, "directory": str(item.directory)}
        for item in installations.values()
    ]
    store.set_setting(CACHE_KEY, json.dumps(entries, ensure_ascii=False))
    return tuple(installations.values())
