"""Onboarding choices and remembered paths never stand in for a live INI check."""

import json
from pathlib import Path

import pytest

from rocket_lantern.game_installations import DiscoveryReport, GameInstallation
from rocket_lantern.installation_preferences import (
    CACHE_KEY,
    ONBOARDING_KEY,
    load_installations,
    needs_onboarding,
    remember_discovery,
)
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult


def test_preferences_should_offer_setup_when_database_is_new() -> None:
    store = MatchStore(":memory:")
    try:
        assert needs_onboarding(store)
    finally:
        store.close()


@pytest.mark.parametrize("status", ["completed", "skipped"])
def test_preferences_should_not_offer_setup_when_user_already_answered(status: str) -> None:
    store = MatchStore(":memory:")
    try:
        store.set_setting(ONBOARDING_KEY, status)
        assert not needs_onboarding(store)
    finally:
        store.close()


@pytest.mark.parametrize("existing_usage", ["selected_player", "saved_match"])
def test_preferences_should_not_interrupt_existing_users_when_status_is_absent(
    existing_usage: str,
) -> None:
    store = MatchStore(":memory:")
    try:
        if existing_usage == "selected_player":
            store.set_setting("player_id", "test-player")
        else:
            store.save(MatchResult("match", "player", "2026-10-17T18:00:00+00:00", 11, "win"))
        assert not needs_onboarding(store)
    finally:
        store.close()


def test_preferences_should_restore_paths_without_accessing_game_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "settings.sqlite3"
    installation = GameInstallation("Steam", tmp_path / "game", tmp_path / "private.ini")
    store = MatchStore(database)
    remember_discovery(store, DiscoveryReport((installation,)))
    assert "private.ini" not in store.setting(CACHE_KEY)
    store.close()

    def unexpected_probe(path: Path) -> bool:
        pytest.fail("Loading remembered paths must not probe game files")

    monkeypatch.setattr(Path, "is_file", unexpected_probe)
    monkeypatch.setattr(Path, "is_dir", unexpected_probe)
    reopened = MatchStore(database)
    try:
        assert load_installations(reopened) == (
            GameInstallation("Steam", installation.directory, None),
        )
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "value",
    ["{", "null", "{}", "[null]", '[{"launcher":"Steam","directory":"relative"}]'],
)
def test_preferences_should_ignore_invalid_cache_without_blocking_startup(value: str) -> None:
    store = MatchStore(":memory:")
    try:
        store.set_setting(CACHE_KEY, value)
        assert load_installations(store) == ()
    finally:
        store.close()


def test_preferences_should_merge_partial_discovery_but_replace_complete_results(
    tmp_path: Path,
) -> None:
    steam = GameInstallation("Steam", tmp_path / "steam", None)
    epic = GameInstallation("Epic Games", tmp_path / "epic", None)
    store = MatchStore(":memory:")
    try:
        remember_discovery(store, DiscoveryReport((steam,)))
        assert remember_discovery(store, DiscoveryReport((epic,), warnings=1)) == (steam, epic)
        assert remember_discovery(store, DiscoveryReport((epic,))) == (epic,)
        assert remember_discovery(store, DiscoveryReport(supported=False)) == (epic,)
        assert remember_discovery(store, DiscoveryReport()) == ()
        assert json.loads(store.setting(CACHE_KEY)) == []
    finally:
        store.close()
