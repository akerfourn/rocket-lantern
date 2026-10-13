"""Startup diagnostics that remain usable when application assets are missing."""

import sqlite3
import traceback
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QStyle,
    QVBoxLayout,
)

from rocket_lantern.branding import APP_NAME
from rocket_lantern.i18n import Text, render
from rocket_lantern.i18n import text as T


class StartupStage(StrEnum):
    RESOURCES = "application_resources"
    DATA_DIRECTORY = "data_directory"
    MIGRATION = "data_migration"
    DATABASE = "database"
    TRANSLATIONS = "translations"
    INTERFACE = "interface"
    LAUNCH = "launch"


def error_description(stage: StartupStage, error: Exception) -> tuple[Text, Text]:
    """Describe the failed operation without claiming every error is a database failure."""
    if stage in (StartupStage.RESOURCES, StartupStage.TRANSLATIONS):
        return (
            T("Impossible de charger les fichiers de RocketLantern."),
            T(
                "Extrais toute l’archive portable en gardant ses fichiers ensemble, "
                "ou réinstalle l’application. Si un antivirus analyse ces fichiers, "
                "attends son résultat avant de réessayer."
            ),
        )
    if stage == StartupStage.MIGRATION:
        return (
            T("Impossible de terminer la migration des données locales."),
            T(
                "Ferme les autres instances de RocketLantern et vérifie l’accès aux "
                "dossiers de données. Ne supprime pas ces dossiers pour résoudre l’erreur."
            ),
        )
    if stage in (StartupStage.DATA_DIRECTORY, StartupStage.DATABASE):
        if isinstance(error, PermissionError):
            return (
                T("Accès refusé aux données locales de RocketLantern."),
                T(
                    "Vérifie les droits du dossier de données indiqué ci-dessous. "
                    "Ce dossier est distinct du dossier d’installation de l’application."
                ),
            )
        code = getattr(error, "sqlite_errorcode", None)
        if isinstance(code, int) and code & 0xFF in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            return (
                T("La base de données de RocketLantern est verrouillée."),
                T("Ferme les autres instances de RocketLantern, puis réessaie."),
            )
        return (
            T("Impossible de préparer les données locales de RocketLantern."),
            T(
                "Le premier lancement crée normalement la base automatiquement. "
                "Consulte le diagnostic ci-dessous ; ne supprime pas une base existante."
            ),
        )
    return (
        T("Impossible de démarrer RocketLantern."),
        T("Consulte le diagnostic ci-dessous pour identifier l’étape et la cause de l’erreur."),
    )


def diagnostic_text(stage: StartupStage, error: Exception, target: Path | None) -> str:
    """Keep technical details plain and explicit, with no automatic upload."""
    try:
        application_version = version("rocket-lantern")
    except (PackageNotFoundError, OSError):
        application_version = "unknown"
    lines = [f"RocketLantern {application_version}", f"Stage: {stage.value}"]
    if target is not None:
        lines.append(f"Target: {target}")
    filename = getattr(error, "filename", None)
    if filename is not None:
        lines.append(f"File: {filename}")
    destination = getattr(error, "filename2", None)
    if destination is not None:
        lines.append(f"Destination: {destination}")
    code = getattr(error, "sqlite_errorcode", None)
    if code is not None:
        lines.append(f"SQLite: {getattr(error, 'sqlite_errorname', 'unknown')} ({code})")
    lines.append("")
    lines.append("".join(traceback.format_exception(error)).rstrip())
    return "\n".join(lines)


class StartupErrorDialog(QDialog):
    """Show actionable context and a copy button without loading branded assets."""

    def __init__(self, stage: StartupStage, error: Exception, target: Path | None) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(640, 440)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical).pixmap(32, 32)
        )
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        description, hint = error_description(stage, error)
        self.message = QLabel(render(description))
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        header.addWidget(self.message, 1)
        layout.addLayout(header)
        self.hint = QLabel(render(hint))
        self.hint.setTextFormat(Qt.TextFormat.PlainText)
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        layout.addWidget(QLabel(render(T("Diagnostic technique (sélectionnable et copiable) :"))))
        self.details = QPlainTextEdit(diagnostic_text(stage, error, target))
        self.details.setReadOnly(True)
        self.details.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.details, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.copy_button = buttons.addButton(
            render(T("Copier le diagnostic")), QDialogButtonBox.ButtonRole.ActionRole
        )
        self.copy_button.setAutoDefault(False)
        self.copy_button.clicked.connect(self._copy)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(render(T("Fermer")))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.details.toPlainText())


def show_startup_error(stage: StartupStage, error: Exception, target: Path | None) -> None:
    """Use Qt's built-in widgets even if the packaged icons or catalogs cannot load."""
    StartupErrorDialog(stage, error, target).exec()
