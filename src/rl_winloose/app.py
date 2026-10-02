"""Application entry point and platform-native local data directory."""

import logging
import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox

from rl_winloose.storage import MatchStore
from rl_winloose.window import MainWindow


def main() -> int:
    """Run the tracker, closing its database when the Qt loop exits."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("RLWinLoss")
    app.setOrganizationName("RLWinLoss")
    store = None
    try:
        location = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation
        )
        if location == "":
            raise OSError("No writable application data directory")
        data_directory = Path(location)
        data_directory.mkdir(parents=True, exist_ok=True)
        store = MatchStore(data_directory / "matches.sqlite3")
        window = MainWindow(store)
        window.show()
        window.start()
        return app.exec()
    except (OSError, sqlite3.Error):
        logging.getLogger(__name__).error("Cannot open the local match database")
        QMessageBox.critical(
            None,
            "RL Win/Loss",
            "Impossible d’ouvrir les données locales. "
            "Vérifie les droits du dossier de l’application.",
        )
        return 1
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
