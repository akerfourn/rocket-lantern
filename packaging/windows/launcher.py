"""Entry point for the Windows application bundle."""

import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from rocket_lantern.app import configure_application, main
from rocket_lantern.i18n import language_manager
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow


def smoke_test() -> int:
    """Check bundled Qt widgets and SQLite without accessing real user data."""
    app = QApplication([sys.argv[0], "-platform", "offscreen"])
    configure_application(app)
    if app.windowIcon().isNull():
        raise RuntimeError("Bundled application icon is missing")
    with TemporaryDirectory(prefix="rocket-lantern-smoke-") as directory:
        store = MatchStore(Path(directory) / "matches.sqlite3")
        try:
            window = MainWindow(store)
            if window.updates.current != version("rocket-lantern"):
                raise RuntimeError("Bundled application version is missing")
            if window.settings_button.icon().isNull():
                raise RuntimeError("Bundled settings icon is missing")
            if window.updates.client.timer.isActive():
                raise RuntimeError("Smoke tests must not start update requests")
            window.show()
            manager = language_manager()
            for language, title in (("en", "Matches"), ("fr", "Matchs")):
                manager.set_language(language)
                app.processEvents()
                if window.tabs.tabText(0) != title:
                    raise RuntimeError(f"Bundled {language} translations are missing")
            QTimer.singleShot(100, window.close)
            return app.exec()
        finally:
            store.close()


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        raise SystemExit(smoke_test())
    raise SystemExit(main())
