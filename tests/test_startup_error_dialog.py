"""Copyable, bilingual startup errors without dependence on branded assets."""

import sqlite3
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from rocket_lantern import branding, i18n, startup_error_dialog
from rocket_lantern.i18n import language_manager, render
from rocket_lantern.startup_error_dialog import (
    StartupErrorDialog,
    StartupStage,
    diagnostic_text,
    error_description,
)


@pytest.mark.parametrize("stage", [StartupStage.RESOURCES, StartupStage.TRANSLATIONS])
def test_resource_error_should_recommend_full_extraction_instead_of_database_permissions(
    application: QApplication, stage: StartupStage
) -> None:
    language_manager().set_language("fr")
    message, hint = error_description(stage, FileNotFoundError("missing.png"))

    assert "fichiers de RocketLantern" in render(message)
    assert "archive portable" in render(hint)
    assert "antivirus" in render(hint)
    assert "base" not in render(message)


def test_permission_error_should_identify_data_directory_not_installation_directory(
    application: QApplication,
) -> None:
    language_manager().set_language("fr")
    message, hint = error_description(StartupStage.DATABASE, PermissionError("denied"))

    assert "Accès refusé" in render(message)
    assert "distinct du dossier d’installation" in render(hint)


@pytest.mark.parametrize("code", [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, 517])
def test_locked_database_should_suggest_closing_other_instances(
    application: QApplication, code: int
) -> None:
    language_manager().set_language("fr")
    failure = sqlite3.OperationalError("database is locked")
    failure.sqlite_errorcode = code
    message, hint = error_description(StartupStage.DATABASE, failure)

    assert "verrouillée" in render(message)
    assert "autres instances" in render(hint)


def test_migration_error_should_not_recommend_deleting_existing_data(
    application: QApplication,
) -> None:
    language_manager().set_language("fr")
    message, hint = error_description(StartupStage.MIGRATION, OSError("copy failed"))

    assert "migration" in render(message)
    assert "Ne supprime pas" in render(hint)


def test_diagnostic_should_include_exact_error_path_stage_version_and_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(startup_error_dialog, "version", lambda package: "1.2.0")
    missing = tmp_path / "assets" / "missing.png"
    try:
        raise FileNotFoundError(2, "file is missing", str(missing))
    except FileNotFoundError as failure:
        diagnostic = diagnostic_text(StartupStage.RESOURCES, failure, missing.parent)

    assert "RocketLantern 1.2.0" in diagnostic
    assert "Stage: application_resources" in diagnostic
    assert f"Target: {missing.parent}" in diagnostic
    assert str(missing) in diagnostic
    assert "FileNotFoundError" in diagnostic
    assert "Traceback" in diagnostic


def test_diagnostic_should_keep_sqlite_error_code_and_name() -> None:
    failure = sqlite3.DatabaseError("file is not a database")
    failure.sqlite_errorcode = sqlite3.SQLITE_NOTADB
    failure.sqlite_errorname = "SQLITE_NOTADB"

    diagnostic = diagnostic_text(StartupStage.DATABASE, failure, Path("matches.sqlite3"))

    assert "SQLite: SQLITE_NOTADB (26)" in diagnostic
    assert "DatabaseError: file is not a database" in diagnostic


@pytest.mark.parametrize("failure", [PackageNotFoundError("rocket-lantern"), OSError("denied")])
def test_diagnostic_should_survive_missing_or_unreadable_package_metadata(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    monkeypatch.setattr(startup_error_dialog, "version", Mock(side_effect=failure))

    diagnostic = diagnostic_text(StartupStage.RESOURCES, OSError("missing assets"), None)

    assert "RocketLantern unknown" in diagnostic
    assert "OSError: missing assets" in diagnostic
    assert "Target:" not in diagnostic


def test_copy_button_should_copy_entire_diagnostic_without_dismissing_the_dialog(
    application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    clipboard = Mock()
    monkeypatch.setattr(QApplication, "clipboard", Mock(return_value=clipboard))
    dialog = StartupErrorDialog(StartupStage.DATABASE, OSError("cannot open"), Path("data"))
    dialog.show()

    dialog.copy_button.click()

    clipboard.setText.assert_called_once_with(dialog.details.toPlainText())
    assert dialog.isVisible()
    assert dialog.details.isReadOnly()
    dialog.close()


def test_error_dialog_should_render_without_application_assets_or_translation_files(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(branding, "ASSET_DIRECTORY", tmp_path / "missing-assets")
    monkeypatch.setattr(i18n, "TRANSLATION_DIRECTORY", tmp_path / "missing-translations")
    monkeypatch.setattr(i18n.QCoreApplication, "translate", lambda context, source, *args: source)
    dialog = StartupErrorDialog(StartupStage.TRANSLATIONS, OSError("missing.qm"), tmp_path)

    assert "fichiers de RocketLantern" in dialog.message.text()
    assert "missing.qm" in dialog.details.toPlainText()
    assert dialog.copy_button.text() == "Copier le diagnostic"
    dialog.close()


def test_error_dialog_should_display_english_when_the_english_catalog_is_active(
    application: QApplication,
) -> None:
    manager = language_manager()
    manager.set_language("en")
    try:
        dialog = StartupErrorDialog(StartupStage.RESOURCES, OSError("missing icon"), None)
        assert dialog.message.text() == "Cannot load RocketLantern files."
        assert "entire portable archive" in dialog.hint.text()
        assert dialog.copy_button.text() == "Copy diagnostic"
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons.button(QDialogButtonBox.StandardButton.Close).text() == "Close"
        dialog.close()
    finally:
        manager.set_language("fr")


def test_database_error_reporter_should_use_system_language_before_preferences_are_available(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = language_manager()
    manager.set_language("fr")
    execute = Mock()
    monkeypatch.setattr(StartupErrorDialog, "exec", execute)
    monkeypatch.setattr(startup_error_dialog, "system_language", lambda: "en")
    try:
        startup_error_dialog.show_startup_error(StartupStage.DATABASE, OSError("cannot open"), None)

        assert manager.language == "en"
        execute.assert_called_once()
    finally:
        manager.set_language("fr")


def test_error_reporter_should_still_open_when_translation_loading_fails(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = Mock()
    monkeypatch.setattr(StartupErrorDialog, "exec", execute)
    monkeypatch.setattr(
        startup_error_dialog, "language_manager", Mock(side_effect=OSError("missing.qm"))
    )

    startup_error_dialog.show_startup_error(StartupStage.TRANSLATIONS, OSError("missing.qm"), None)

    execute.assert_called_once()
