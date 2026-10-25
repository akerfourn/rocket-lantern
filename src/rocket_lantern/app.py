"""Application entry point and platform-native local data directory."""

import logging
import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from rocket_lantern.branding import APP_NAME, ASSET_DIRECTORY, LEGACY_DATA_NAME, application_icon
from rocket_lantern.data_migration import migrate_data_directory
from rocket_lantern.i18n import TRANSLATION_DIRECTORY, language_manager, system_language
from rocket_lantern.startup_error_dialog import StartupStage, show_startup_error
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow


def configure_application(app: QApplication) -> None:
    """Use RocketLantern for both visible branding and native data organization."""
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(application_icon())


def local_data_directory() -> Path:
    """Return the native RocketLantern data directory without filesystem changes."""
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    if location == "":
        raise OSError("No writable application data directory")
    return Path(location)


def legacy_data_directory(directory: Path) -> Path:
    """Reconstruct the historical Qt organization/application path on this platform."""
    if directory.parent.name == APP_NAME:
        return directory.parent.with_name(LEGACY_DATA_NAME) / LEGACY_DATA_NAME
    return directory.with_name(LEGACY_DATA_NAME)


def main() -> int:
    """Run the tracker, closing its database when the Qt loop exits."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    store = None
    window = None
    stage = StartupStage.RESOURCES
    target: Path | None = ASSET_DIRECTORY
    try:
        configure_application(app)
        stage = StartupStage.DATA_DIRECTORY
        target = None
        data_directory = local_data_directory()
        stage = StartupStage.MIGRATION
        target = data_directory
        migrate_data_directory(legacy_data_directory(data_directory), data_directory)
        stage = StartupStage.DATABASE
        target = data_directory / "matches.sqlite3"
        data_directory.mkdir(parents=True, exist_ok=True)
        store = MatchStore(target)
        saved_language = store.setting("language")
        stage = StartupStage.TRANSLATIONS
        target = TRANSLATION_DIRECTORY
        language_manager().set_language(
            saved_language if saved_language in ("fr", "en") else system_language()
        )
        stage = StartupStage.INTERFACE
        target = ASSET_DIRECTORY
        window = MainWindow(store)
        stage = StartupStage.LAUNCH
        target = None
        window.show()
        window.start()
        window.updates.start()
        window.offer_onboarding()
        return app.exec()
    except (OSError, sqlite3.Error) as error:
        logging.getLogger(__name__).exception(
            "Startup failed at stage %s (target %s)", stage.value, target
        )
        if window is not None:
            window.close()
        if store is not None:
            store.close()
            store = None
        show_startup_error(stage, error, target)
        return 1
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
