"""Isolated first launches and precise startup failure boundaries."""

import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from rocket_lantern import app, storage
from rocket_lantern.i18n import TRANSLATION_DIRECTORY
from rocket_lantern.startup_error_dialog import StartupStage
from rocket_lantern.storage import MatchStore


@pytest.fixture
def startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, application: QApplication
) -> tuple[Path, Mock, Mock, Mock]:
    directory = tmp_path / "RocketLantern" / "RocketLantern"
    qt_app = Mock()
    qt_app.exec.return_value = 0
    window = Mock()
    reporter = Mock()
    monkeypatch.setattr(app, "QApplication", Mock(return_value=qt_app))
    monkeypatch.setattr(app, "configure_application", Mock())
    monkeypatch.setattr(app, "local_data_directory", lambda: directory)
    monkeypatch.setattr(app, "MainWindow", Mock(return_value=window))
    monkeypatch.setattr(app, "system_language", lambda: "fr")
    monkeypatch.setattr(app, "show_startup_error", reporter)
    return directory, window, reporter, qt_app


@pytest.mark.parametrize("existing_directory", [False, True])
def test_startup_should_create_database_when_no_history_exists(
    startup: tuple[Path, Mock, Mock, Mock], existing_directory: bool
) -> None:
    directory, window, reporter, _ = startup
    if existing_directory:
        directory.mkdir(parents=True)

    assert app.main() == 0

    reporter.assert_not_called()
    window.start.assert_called_once()
    window.updates.start.assert_called_once()
    window.offer_onboarding.assert_called_once()
    store = MatchStore(directory / "matches.sqlite3")
    try:
        assert store.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert store.connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 0
    finally:
        store.close()


def test_startup_should_report_resource_failure_before_accessing_user_data(
    startup: tuple[Path, Mock, Mock, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    directory, _, reporter, _ = startup
    failure = FileNotFoundError("Missing application icon: missing.png")
    monkeypatch.setattr(app, "configure_application", Mock(side_effect=failure))
    resolve = Mock()
    monkeypatch.setattr(app, "local_data_directory", resolve)

    assert app.main() == 1

    reporter.assert_called_once_with(StartupStage.RESOURCES, failure, app.ASSET_DIRECTORY)
    resolve.assert_not_called()
    assert not directory.exists()


def test_startup_should_report_directory_resolution_failure_without_a_guessed_path(
    startup: tuple[Path, Mock, Mock, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, reporter, _ = startup
    failure = OSError("No writable application data directory")
    monkeypatch.setattr(app, "local_data_directory", Mock(side_effect=failure))

    assert app.main() == 1

    reporter.assert_called_once_with(StartupStage.DATA_DIRECTORY, failure, None)


def test_startup_should_report_database_path_when_opening_it_fails(
    startup: tuple[Path, Mock, Mock, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    directory, _, reporter, _ = startup
    failure = sqlite3.OperationalError("unable to open database file")
    monkeypatch.setattr(app, "MatchStore", Mock(side_effect=failure))

    assert app.main() == 1

    reporter.assert_called_once_with(StartupStage.DATABASE, failure, directory / "matches.sqlite3")


def test_startup_should_report_translation_failure_and_close_the_open_database(
    startup: tuple[Path, Mock, Mock, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    directory, _, reporter, _ = startup
    directory.mkdir(parents=True)
    store = MatchStore(directory / "matches.sqlite3")
    monkeypatch.setattr(app, "MatchStore", Mock(return_value=store))
    failure = OSError("Cannot load translation catalog: missing.qm")
    monkeypatch.setattr(app, "language_manager", Mock(side_effect=failure))

    assert app.main() == 1

    reporter.assert_called_once_with(StartupStage.TRANSLATIONS, failure, TRANSLATION_DIRECTORY)
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        store.connection.execute("SELECT 1")


def test_startup_should_not_label_an_interface_failure_as_a_database_problem(
    startup: tuple[Path, Mock, Mock, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, reporter, _ = startup
    failure = OSError("interface resource unavailable")
    monkeypatch.setattr(app, "MainWindow", Mock(side_effect=failure))

    assert app.main() == 1

    reporter.assert_called_once_with(StartupStage.INTERFACE, failure, app.ASSET_DIRECTORY)


def test_startup_should_stop_window_services_before_reporting_launch_failure(
    startup: tuple[Path, Mock, Mock, Mock],
) -> None:
    _, window, reporter, qt_app = startup
    failure = OSError("launch failed")
    qt_app.exec.side_effect = failure

    assert app.main() == 1

    window.close.assert_called_once()
    reporter.assert_called_once_with(StartupStage.LAUNCH, failure, None)


def test_store_should_release_connection_when_schema_initialization_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = sqlite3.connect(tmp_path / "matches.sqlite3")
    monkeypatch.setattr(storage.sqlite3, "connect", Mock(return_value=connection))
    failure = sqlite3.DatabaseError("schema migration failed")
    monkeypatch.setattr(storage, "migrate", Mock(side_effect=failure))

    with pytest.raises(sqlite3.DatabaseError, match="schema migration failed"):
        MatchStore(tmp_path / "matches.sqlite3")

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")
