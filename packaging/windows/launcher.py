"""Entry point for the Windows application bundle."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from rl_winloose.app import main
from rl_winloose.storage import MatchStore
from rl_winloose.window import MainWindow


def smoke_test() -> int:
    """Check bundled Qt widgets and SQLite without accessing real user data."""
    app = QApplication([sys.argv[0], "-platform", "offscreen"])
    with TemporaryDirectory(prefix="rl-winloss-smoke-") as directory:
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
