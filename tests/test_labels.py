"""Stable catalogs, independent match choices and lossless migration from schema 3."""

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from rocket_lantern.evaluation_repository import migrate_evaluations
from rocket_lantern.label_repository import migrate_labels
from rocket_lantern.labels import DEFAULT_LIST, Label, LabelList
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult

GROUP = "custom:00000000-0000-0000-0000-000000000001"
ITEM = "custom:00000000-0000-0000-0000-000000000002"
OTHER = "custom:00000000-0000-0000-0000-000000000003"
TIMESTAMP = "2026-10-19T12:00:00+00:00"


@pytest.fixture
def store() -> Iterator[MatchStore]:
    database = MatchStore(":memory:")
    yield database
    database.close()


def test_catalog_should_keep_default_ids_and_allow_independent_custom_choices(
    store: MatchStore,
) -> None:
    assert store.labels.lists() == (LabelList(DEFAULT_LIST, "Suspicion de smurf"),)
    store.labels.save_list(LabelList(GROUP, "Mon jeu"))
    store.labels.save_label(Label(ITEM, GROUP, "À revoir", "#123456"))
    store.set_evaluation("game", "possible", TIMESTAMP)
    store.labels.choose("game", GROUP, ITEM, TIMESTAMP)

    assert store.labels.choices("game") == {DEFAULT_LIST: "possible", GROUP: ITEM}
    assert store.labels.choices("new-match") == {}
    assert store.summary("player").unknown == 0
    assert store.connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_catalog_should_rename_recolor_and_disable_without_losing_historical_choices(
    store: MatchStore,
) -> None:
    group = LabelList(GROUP, "Before")
    label = Label(ITEM, GROUP, "Old", "#123456")
    store.labels.save_list(group)
    store.labels.save_label(label)
    store.labels.choose("game", GROUP, ITEM, TIMESTAMP)
    store.labels.save_label(replace(label, name="Renamed", color="#aabbcc", enabled=False))
    store.labels.save_list(replace(group, name="After", enabled=False))

    assert store.labels.choices("game")[GROUP] == ITEM
    assert next(item for item in store.labels.labels() if item.id == ITEM).name == "Renamed"
    with pytest.raises(ValueError, match="enabled"):
        store.labels.choose("other", GROUP, ITEM, TIMESTAMP)


def test_catalog_should_require_membership_and_keep_other_lists_when_clearing(
    store: MatchStore,
) -> None:
    store.labels.save_list(LabelList(GROUP, "Custom"))
    store.labels.save_label(Label(ITEM, GROUP, "Custom"))
    with pytest.raises(ValueError, match="belong"):
        store.labels.choose("game", DEFAULT_LIST, ITEM, TIMESTAMP)
    store.set_evaluation("game", "strong", TIMESTAMP)
    store.labels.choose("game", GROUP, ITEM, TIMESTAMP)
    store.labels.choose("game", GROUP, "", TIMESTAMP)
    assert store.labels.choices("game") == {DEFAULT_LIST: "strong"}
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        store.connection.execute(
            "UPDATE match_labels SET label_id=? WHERE list_id=?", (ITEM, DEFAULT_LIST)
        )
    store.connection.rollback()


@pytest.mark.parametrize("color", ["red", "#123", "#12345678", "#xxxxxx"])
def test_catalog_should_reject_invalid_colors_without_creating_labels(
    store: MatchStore, color: str
) -> None:
    with pytest.raises(ValueError, match="color"):
        store.labels.save_label(Label(ITEM, DEFAULT_LIST, "Custom", color))
    assert len(store.labels.labels()) == 4


@pytest.mark.parametrize("name", ["", "   ", "a" * 81, "Name\nOther"])
def test_catalog_should_reject_invalid_names(store: MatchStore, name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        store.labels.save_list(LabelList(GROUP, name))


def test_catalog_should_reject_custom_identifiers_that_are_not_uuids(store: MatchStore) -> None:
    with pytest.raises(ValueError, match="UUID"):
        store.labels.save_list(LabelList("custom:a-name", "Custom"))
    with pytest.raises(ValueError, match="custom:"):
        store.labels.save_label(Label("user-name", DEFAULT_LIST, "Custom"))


def make_legacy_database(path: Path, shortcuts: str) -> None:
    store = MatchStore(path)
    store.save(MatchResult("game", "player", TIMESTAMP, 11, "win"))
    with store.connection:
        store.connection.execute("DROP TABLE match_labels")
        store.connection.execute("DROP TABLE labels")
        store.connection.execute("DROP TABLE label_lists")
        store.connection.execute("PRAGMA user_version=2")
    migrate_evaluations(store.connection)
    with store.connection:
        key = store.detail("game")["id"]
        store.connection.execute(
            "INSERT INTO match_evaluations VALUES (?, 'possible', ?)", (key, TIMESTAMP)
        )
    store.set_settings({"evaluation_hotkeys": shortcuts, "evaluation_hotkeys_enabled": "1"})
    store.close()


def test_migration_should_preserve_evaluations_match_ids_timestamps_and_shortcut_assignments(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.sqlite3"
    shortcuts = ("", "Alt+Shift+A", "Ctrl+Shift+P", "Ctrl+Shift+S")
    make_legacy_database(path, json.dumps(shortcuts))
    store = MatchStore(path)
    try:
        assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 4
        assert store.evaluation("game") == "possible"
        assert store.summary("player").wins == 1
        assert tuple(item.shortcut for item in store.labels.labels()) == shortcuts
        assert (
            store.connection.execute("SELECT updated_at FROM match_labels").fetchone()[0]
            == TIMESTAMP
        )
        assert len(store.sessions("player")) == 1
        store.labels.save_list(LabelList(GROUP, "Preserved"))
    finally:
        store.close()
    reopened = MatchStore(path)
    try:
        assert len(reopened.labels.lists()) == 2
        assert reopened.evaluation("game") == "possible"
        assert reopened.connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        reopened.close()


def test_migration_should_disable_corrupt_legacy_shortcuts_instead_of_enabling_defaults(
    tmp_path: Path,
) -> None:
    path = tmp_path / "corrupt-shortcuts.sqlite3"
    make_legacy_database(path, "[42]")
    store = MatchStore(path)
    try:
        assert store.setting("evaluation_hotkeys_enabled") == "0"
        assert store.evaluation("game") == "possible"
    finally:
        store.close()


def test_migration_should_roll_back_catalog_and_keep_legacy_votes_on_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rollback.sqlite3"
    make_legacy_database(path, "")
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")

    def deny_drop(
        action: int,
        first: str | None,
        second: str | None,
        database: str | None,
        trigger: str | None,
    ) -> int:
        if action == sqlite3.SQLITE_DROP_TABLE and first == "match_evaluations":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(deny_drop)
    try:
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            migrate_labels(connection)
        connection.set_authorizer(None)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert (
            connection.execute("SELECT evaluation FROM match_evaluations").fetchone()[0]
            == "possible"
        )
        assert (
            connection.execute("SELECT name FROM sqlite_master WHERE name='labels'").fetchone()
            is None
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
