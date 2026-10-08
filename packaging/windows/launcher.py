"""Entry point for the Windows application bundle."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from rocket_lantern.app import configure_application, main
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
            window.show()
            QTimer.singleShot(100, window.close)
            return app.exec()
        finally:
            store.close()


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        raise SystemExit(smoke_test())
    raise SystemExit(main())
