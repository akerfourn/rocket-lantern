"""Application entry point and platform-native local data directory."""

import logging
import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox

from rocket_lantern.branding import APP_NAME, LEGACY_DATA_NAME, application_icon
from rocket_lantern.i18n import language_manager, render, system_language
from rocket_lantern.i18n import text as T
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow


def configure_application(app: QApplication) -> None:
    """Apply visible branding while retaining the original data organization."""
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(LEGACY_DATA_NAME)
    app.setWindowIcon(application_icon())


def local_data_directory() -> Path:
    """Keep the pre-rename SQLite directory on every supported Qt platform."""
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    if location == "":
        raise OSError("No writable application data directory")
    return Path(location).with_name(LEGACY_DATA_NAME)


def main() -> int:
    """Run the tracker, closing its database when the Qt loop exits."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    store = None
    try:
        configure_application(app)
        data_directory = local_data_directory()
        data_directory.mkdir(parents=True, exist_ok=True)
        store = MatchStore(data_directory / "matches.sqlite3")
        saved_language = store.setting("language")
        language_manager().set_language(
            saved_language if saved_language in ("fr", "en") else system_language()
        )
        window = MainWindow(store)
        window.show()
        window.start()
        return app.exec()
    except (OSError, sqlite3.Error):
        logging.getLogger(__name__).error("Cannot open the local match database")
        QMessageBox.critical(
            None,
            APP_NAME,
            render(
                T(
                    "Impossible d’ouvrir les données locales. Vérifie les droits du "
                    "dossier de l’application."
                )
            ),
        )
        return 1
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
