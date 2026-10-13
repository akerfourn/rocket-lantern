"""Temporary-directory migration tests; real application data is never touched."""

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from rocket_lantern import app, data_migration
from rocket_lantern.data_migration import DATABASE_NAME, MIGRATION_MANIFEST, migrate_data_directory
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult


def legacy_database(directory: Path) -> None:
    directory.mkdir(parents=True)
    store = MatchStore(directory / DATABASE_NAME)
    try:
        store.set_setting("player_id", "demo-player")
        store.set_setting("language", "fr")
        store.save(MatchResult("demo-match", "demo-player", "2026-10-10T19:00:00+00:00", 13, "win"))
    finally:
        store.close()


def test_migration_should_preserve_history_preferences_and_extra_files_before_removing_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "RLWinLoss/RLWinLoss"
    destination = tmp_path / "RocketLantern/RocketLantern"
    legacy_database(source)
    extra = source / "backups/preferences.txt"
    extra.parent.mkdir()
    extra.write_text("local preferences", encoding="utf-8")

    migrate_data_directory(source, destination)

    store = MatchStore(destination / DATABASE_NAME)
    try:
        assert store.setting("player_id") == "demo-player"
        assert store.setting("language") == "fr"
        assert store.summary("demo-player").wins == 1
        assert len(store.sessions("demo-player")) == 1
    finally:
        store.close()
    assert (destination / "backups/preferences.txt").read_text(
        encoding="utf-8"
    ) == "local preferences"
    assert not source.exists()
    assert not (destination / MIGRATION_MANIFEST).exists()
    assert not list(destination.parent.glob(".rocket-lantern-migration-*"))


def test_migration_should_leave_existing_new_database_and_legacy_data_unchanged(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    legacy_database(source)
    legacy_database(destination)
    store = MatchStore(destination / DATABASE_NAME)
    store.set_setting("player_id", "new-player")
    store.close()
    before_source = data_migration.directory_files(source)
    before_target = data_migration.directory_files(destination)

    migrate_data_directory(source, destination)

    assert data_migration.directory_files(source) == before_source
    assert data_migration.directory_files(destination) == before_target


def test_migration_should_do_nothing_when_no_legacy_database_exists(tmp_path: Path) -> None:
    destination = tmp_path / "modern"
    migrate_data_directory(tmp_path / "missing", destination)
    assert not destination.exists()


def test_migration_should_use_existing_empty_destination(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    legacy_database(source)
    destination.mkdir()
    migrate_data_directory(source, destination)
    assert (destination / DATABASE_NAME).is_file()
    assert not source.exists()


def test_migration_should_preserve_source_when_destination_contains_unrelated_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    legacy_database(source)
    destination.mkdir()
    (destination / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(OSError, match="not empty"):
        migrate_data_directory(source, destination)
    assert (source / DATABASE_NAME).is_file()
    assert (destination / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_migration_should_preserve_source_when_copy_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    legacy_database(source)
    before = data_migration.directory_files(source)
    monkeypatch.setattr(shutil, "copytree", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        migrate_data_directory(source, destination)
    assert data_migration.directory_files(source) == before
    assert not destination.exists()


def test_migration_should_preserve_source_when_copied_bytes_are_corrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    legacy_database(source)
    copytree = shutil.copytree

    def corrupt_copy(source_path: Path, target: Path) -> Path:
        result = copytree(source_path, target)
        (target / DATABASE_NAME).write_bytes(b"corrupt copy")
        return result

    monkeypatch.setattr(shutil, "copytree", corrupt_copy)
    with pytest.raises(OSError, match="copy verification failed"):
        migrate_data_directory(source, destination)
    assert (source / DATABASE_NAME).is_file()
    assert not destination.exists()


def test_migration_should_preserve_source_when_original_database_is_invalid(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    source.mkdir()
    (source / DATABASE_NAME).write_bytes(b"not a database")
    with pytest.raises(sqlite3.DatabaseError, match="not a database"):
        migrate_data_directory(source, destination)
    assert (source / DATABASE_NAME).read_bytes() == b"not a database"
    assert not destination.exists()


def test_migration_should_preserve_source_when_it_changes_during_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    legacy_database(source)
    consolidate = data_migration.consolidate_database

    def change_source(staged: Path) -> None:
        consolidate(staged)
        store = MatchStore(source / DATABASE_NAME)
        store.set_setting("language", "en")
        store.close()

    monkeypatch.setattr(data_migration, "consolidate_database", change_source)
    with pytest.raises(OSError, match="Legacy data changed during migration"):
        migrate_data_directory(source, destination)
    assert (source / DATABASE_NAME).is_file()
    assert not destination.exists()


def test_migration_should_resume_cleanup_after_a_file_cannot_be_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    legacy_database(source)
    (source / "a-preferences.txt").write_text("preserved", encoding="utf-8")
    original_unlink = Path.unlink

    def blocked_unlink(path: Path, missing_ok: bool = False) -> None:
        if path == source / DATABASE_NAME:
            raise PermissionError("old application is running")
        original_unlink(path, missing_ok=missing_ok)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", blocked_unlink)
        with pytest.raises(PermissionError, match="old application is running"):
            migrate_data_directory(source, destination)
    assert (source / DATABASE_NAME).exists()
    assert (destination / DATABASE_NAME).exists()
    assert (destination / MIGRATION_MANIFEST).exists()
    assert not (source / "a-preferences.txt").exists(), "Cleanup may be partially completed"
    assert (destination / "a-preferences.txt").read_text(encoding="utf-8") == "preserved"

    migrate_data_directory(source, destination)

    assert not source.exists()
    assert not (destination / MIGRATION_MANIFEST).exists()
    store = MatchStore(destination / DATABASE_NAME)
    assert store.summary("demo-player").wins == 1
    store.close()


def test_migration_should_not_delete_changed_source_during_resumed_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    legacy_database(source)
    cleanup = data_migration.finish_cleanup
    monkeypatch.setattr(data_migration, "finish_cleanup", Mock(side_effect=OSError("interrupted")))
    with pytest.raises(OSError, match="interrupted"):
        migrate_data_directory(source, destination)
    monkeypatch.setattr(data_migration, "finish_cleanup", cleanup)
    store = MatchStore(source / DATABASE_NAME)
    store.set_setting("language", "en")
    store.close()

    with pytest.raises(OSError, match="Legacy data changed"):
        migrate_data_directory(source, destination)
    assert (source / DATABASE_NAME).exists()


def test_migration_should_recover_committed_wal_data_left_by_an_abrupt_exit(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    legacy_database(source)
    child_script = """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('PRAGMA journal_mode = WAL')
connection.execute("UPDATE settings SET value = 'en' WHERE key = 'language'")
connection.commit()
os._exit(0)
"""
    subprocess.run(
        [sys.executable, "-c", child_script, str(source / DATABASE_NAME)], check=True, timeout=10
    )
    assert (source / f"{DATABASE_NAME}-wal").is_file()

    migrate_data_directory(source, destination)

    store = MatchStore(destination / DATABASE_NAME)
    assert store.setting("language") == "en", "Committed WAL changes must not be lost"
    store.close()
    assert not source.exists()


@pytest.mark.parametrize("name", ["../outside.txt", "/outside.txt", "C:/outside.txt"])
def test_manifest_should_reject_paths_outside_the_legacy_directory(name: str) -> None:
    if name.startswith("C:") and sys.platform != "win32":
        pytest.skip("Windows absolute path validation")
    with pytest.raises(OSError, match="Unsafe path"):
        data_migration.checked_manifest_files({name: "0" * 64})


def test_manifest_should_preserve_data_when_recorded_source_does_not_match(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    legacy_database(source)
    destination.mkdir()
    (destination / MIGRATION_MANIFEST).write_text(json.dumps({"source": "other"}), encoding="utf-8")
    with pytest.raises(OSError, match="Unexpected source"):
        migrate_data_directory(source, destination)
    assert (source / DATABASE_NAME).exists()


def test_startup_should_migrate_automatically_before_opening_the_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application: QApplication,
) -> None:
    source = tmp_path / "RLWinLoss/RLWinLoss"
    destination = tmp_path / "RocketLantern/RocketLantern"
    legacy_database(source)
    qt_app = Mock()
    qt_app.exec.return_value = 0
    monkeypatch.setattr(app, "QApplication", Mock(return_value=qt_app))
    monkeypatch.setattr(app, "configure_application", Mock())
    monkeypatch.setattr(app, "local_data_directory", lambda: destination)
    monkeypatch.setattr(app, "MainWindow", Mock())

    def open_migrated_store(path: Path) -> MatchStore:
        assert path == destination / DATABASE_NAME
        assert path.exists(), "Migration must complete before MatchStore is created"
        assert not source.exists()
        return MatchStore(path)

    monkeypatch.setattr(app, "MatchStore", open_migrated_store)
    assert app.main() == 0
    app.MainWindow.return_value.start.assert_called_once()


def test_startup_should_stop_without_opening_a_new_database_when_migration_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "RocketLantern/RocketLantern"
    monkeypatch.setattr(app, "QApplication", Mock())
    monkeypatch.setattr(app, "configure_application", Mock())
    monkeypatch.setattr(app, "local_data_directory", lambda: destination)
    monkeypatch.setattr(app, "migrate_data_directory", Mock(side_effect=OSError("copy failed")))
    database_factory = Mock()
    error_dialog = Mock()
    monkeypatch.setattr(app, "MatchStore", database_factory)
    monkeypatch.setattr(app, "show_startup_error", error_dialog)

    assert app.main() == 1
    database_factory.assert_not_called()
    error_dialog.assert_called_once()
    assert not destination.exists(), "A failed migration must not create an empty history"


def test_migration_should_preserve_older_database_schema_and_let_store_upgrade_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    source.mkdir()
    connection = sqlite3.connect(source / DATABASE_NAME)
    try:
        connection.executescript(
            """
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO settings VALUES ('player_id', 'demo-player');
            CREATE TABLE matches (
                match_id TEXT NOT NULL, player_id TEXT NOT NULL, ended_at TEXT NOT NULL,
                playlist INTEGER, outcome TEXT NOT NULL, PRIMARY KEY (match_id, player_id)
            );
            INSERT INTO matches VALUES (
                'old', 'demo-player', '2026-10-10T19:00:00+00:00', 11, 'win'
            );
            """
        )
    finally:
        connection.close()

    migrate_data_directory(source, destination)
    store = MatchStore(destination / DATABASE_NAME)
    try:
        assert store.setting("player_id") == "demo-player"
        assert store.summary("demo-player").wins == 1
        assert len(store.sessions("demo-player")) == 1
    finally:
        store.close()


def test_migration_should_refuse_cleanup_when_the_published_copy_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "modern"
    legacy_database(source)
    cleanup = data_migration.finish_cleanup
    with monkeypatch.context() as patch:
        patch.setattr(data_migration, "finish_cleanup", Mock(side_effect=OSError("interrupted")))
        with pytest.raises(OSError, match="interrupted"):
            migrate_data_directory(source, destination)
    assert data_migration.finish_cleanup is cleanup
    (destination / DATABASE_NAME).write_bytes(b"damaged copy")

    with pytest.raises(OSError, match="Migrated files changed"):
        migrate_data_directory(source, destination)
    assert (source / DATABASE_NAME).exists()


def test_migration_should_reject_overlapping_directories_without_changing_data(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy"
    legacy_database(source)
    with pytest.raises(OSError, match="separate directories"):
        migrate_data_directory(source, source / "nested")
    assert (source / DATABASE_NAME).exists()
