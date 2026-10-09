"""Copy, validate and retire legacy application data without overwriting newer data."""

import hashlib
import json
import logging
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

LOGGER = logging.getLogger(__name__)
DATABASE_NAME = "matches.sqlite3"
MIGRATION_MANIFEST = ".data-migration.json"
DATABASE_SIDECARS = tuple(f"{DATABASE_NAME}{suffix}" for suffix in ("-wal", "-shm", "-journal"))


def file_digest(path: Path) -> str:
    """Validate file contents, not only size or modification time."""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def directory_files(directory: Path) -> dict[str, str]:
    """Refuse links and special files so migration cannot reach outside its roots."""
    if directory.is_symlink():
        raise OSError("Application data migration does not support symbolic links")
    if not directory.exists():
        return {}
    files = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise OSError("Application data migration does not support symbolic links")
        if path.is_dir():
            continue
        if not path.is_file():
            raise OSError("Application data migration requires regular files")
        files[path.relative_to(directory).as_posix()] = file_digest(path)
    return files


def validate_database(path: Path) -> None:
    """Check SQLite integrity, references and the minimum application schema."""
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise sqlite3.DatabaseError("Application database failed its integrity check")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.DatabaseError("Application database contains invalid foreign keys")
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if not {"matches", "settings"} <= tables:
            raise sqlite3.DatabaseError("Application database is missing matches or settings")


def consolidate_database(directory: Path) -> None:
    """Include committed WAL data using SQLite's backup API on the staged copy only."""
    database = directory / DATABASE_NAME
    validate_database(database)
    backup = directory / ".validated-matches.sqlite3"
    if backup.exists():
        raise OSError("Reserved migration backup filename already exists")
    with (
        closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as source,
        closing(sqlite3.connect(backup)) as target,
    ):
        source.backup(target)
    validate_database(backup)
    backup.replace(database)
    for name in DATABASE_SIDECARS:
        (directory / name).unlink(missing_ok=True)


def checked_manifest_files(value: object) -> dict[str, str]:
    """Reject a malformed or path-traversing manifest before any cleanup."""
    if not isinstance(value, dict):
        raise OSError("Invalid application data migration manifest")
    files = {}
    for name, digest in value.items():
        if not isinstance(name, str) or not isinstance(digest, str):
            raise OSError("Invalid application data migration manifest")
        relative = Path(name)
        if relative.anchor != "" or ".." in relative.parts or name in ("", "."):
            raise OSError("Unsafe path in application data migration manifest")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise OSError("Invalid digest in application data migration manifest")
        files[name] = digest
    return files


def finish_cleanup(source: Path, destination: Path) -> None:
    """Resume interrupted removal only while both copies still match their manifest."""
    manifest_path = destination / MIGRATION_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise OSError("Invalid application data migration manifest") from error
    if not isinstance(manifest, dict) or manifest.get("source") != str(source.resolve()):
        raise OSError("Unexpected source in application data migration manifest")
    expected_source = checked_manifest_files(manifest.get("source_files"))
    expected_target = checked_manifest_files(manifest.get("target_files"))
    actual_target = directory_files(destination)
    actual_target.pop(MIGRATION_MANIFEST, None)
    if actual_target != expected_target:
        raise OSError("Migrated files changed; legacy data was preserved")
    validate_database(destination / DATABASE_NAME)
    actual_source = directory_files(source)
    for name, digest in actual_source.items():
        if expected_source.get(name) != digest:
            raise OSError("Legacy data changed; migration cleanup was stopped")
    # Remove only individually validated files, never recursively delete a data root.
    for name in actual_source:
        path = source / name
        if not path.resolve().is_relative_to(source.resolve()):
            raise OSError("Unsafe cleanup path in application data migration")
        if file_digest(path) != expected_source[name]:
            raise OSError("Legacy data changed during cleanup")
        path.unlink()
    if source.exists():
        directories = [path for path in source.rglob("*") if path.is_dir()]
        for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
            directory.rmdir()
        source.rmdir()
    manifest_path.unlink()
    LOGGER.info("Legacy application data copied, validated and removed")


def migrate_data_directory(source: Path, destination: Path) -> None:
    """Publish a verified copy atomically, then retire the original with resumable cleanup."""
    source = source.absolute()
    destination = destination.absolute()
    if source.is_symlink() or destination.is_symlink():
        raise OSError("Application data migration does not support symbolic links")
    source = source.resolve()
    destination = destination.resolve()
    if (
        source == destination
        or source.is_relative_to(destination)
        or destination.is_relative_to(source)
    ):
        raise OSError("Application data migration requires separate directories")
    if (destination / MIGRATION_MANIFEST).exists():
        finish_cleanup(source, destination)
        return
    if (destination / DATABASE_NAME).exists():
        if (source / DATABASE_NAME).exists():
            LOGGER.warning("Both data directories exist; using the new database without merging")
        return
    if not (source / DATABASE_NAME).exists():
        return
    if destination.exists() and any(destination.iterdir()):
        raise OSError("New data directory is not empty; legacy data was preserved")
    source_files = directory_files(source)
    if MIGRATION_MANIFEST in source_files:
        raise OSError("Reserved migration manifest filename already exists in legacy data")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=".rocket-lantern-migration-", dir=destination.parent
    ) as temporary:
        staged = Path(temporary) / "data"
        shutil.copytree(source, staged)
        if directory_files(staged) != source_files:
            raise OSError("Application data copy verification failed; legacy data was preserved")
        consolidate_database(staged)
        if directory_files(source) != source_files:
            raise OSError("Legacy data changed during migration; original data was preserved")
        manifest = {
            "source": str(source.resolve()),
            "source_files": source_files,
            "target_files": directory_files(staged),
        }
        (staged / MIGRATION_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        if destination.exists():
            destination.rmdir()
        staged.rename(destination)
    finish_cleanup(source, destination)
