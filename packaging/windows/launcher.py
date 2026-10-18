"""Entry point for the Windows application bundle."""

import argparse
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from rocket_lantern.app import configure_application, main
from rocket_lantern.game_presence import GamePresenceMonitor
from rocket_lantern.i18n import language_manager
from rocket_lantern.storage import MatchStore, Summary
from rocket_lantern.window import MainWindow


class SmokeGameApi:
    """Simulate game focus without querying real processes or opening a connection."""

    def __init__(self) -> None:
        self.foreground = 10

    def game_process_ids(self) -> frozenset[int]:
        return frozenset({100})

    def foreground_window(self) -> int:
        return self.foreground

    def process_id(self, window: int) -> int:
        return 100

    def window_visible(self, window: int) -> bool:
        return True


def accept_boost_warning(app: QApplication) -> None:
    """Simulate consent only inside the isolated package smoke test."""
    dialog = app.activeModalWidget()
    if not isinstance(dialog, QMessageBox):
        raise RuntimeError("Bundled boost overlay risk confirmation is missing")
    dialog.button(QMessageBox.StandardButton.Yes).click()


def smoke_test(expected_version: str | None = None) -> int:
    """Check bundled Qt widgets and SQLite without accessing real user data."""
    installed_version = version("rocket-lantern")
    if expected_version is not None and installed_version != expected_version:
        raise RuntimeError(
            f"Bundled version mismatch: expected {expected_version}, found {installed_version}"
        )
    app = QApplication([sys.argv[0], "-platform", "offscreen"])
    configure_application(app)
    if app.windowIcon().isNull():
        raise RuntimeError("Bundled application icon is missing")
    with TemporaryDirectory(prefix="rocket-lantern-smoke-") as directory:
        store = MatchStore(Path(directory) / "matches.sqlite3")
        try:
            game_api = SmokeGameApi()
            presence = GamePresenceMonitor(app, game_api)
            window = MainWindow(store, presence)
            if window.updates.current != installed_version:
                raise RuntimeError("Bundled application version is missing")
            if window.settings_button.icon().isNull():
                raise RuntimeError("Bundled settings icon is missing")
            if window.updates.client.timer.isActive():
                raise RuntimeError("Smoke tests must not start update requests")
            window.show()
            window.offer_onboarding()
            onboarding = window.onboarding.dialog
            if onboarding is None or onboarding.installations.is_busy:
                raise RuntimeError(
                    "Bundled setup guide is missing or starts discovery automatically"
                )
            manager = language_manager()
            for language, title in (("en", "Matches"), ("fr", "Matchs")):
                manager.set_language(language)
                app.processEvents()
                if window.tabs.tabText(0) != title:
                    raise RuntimeError(f"Bundled {language} translations are missing")
                if onboarding.language.currentData() != language:
                    raise RuntimeError(f"Bundled setup guide does not follow {language}")
            onboarding.skip_button.click()
            window.matches.counters.set_summary(Summary(3, 1, 0))
            window.settings.overlay.enabled.setChecked(True)
            overlay = window.overlay.window
            if overlay is None or not overlay.isVisible() or overlay.balance.text() != "+2":
                raise RuntimeError("Bundled overlay is missing or does not mirror the summary")
            window.live.set_player("smoke-player")
            window.live.observe(
                {
                    "Event": "UpdateState",
                    "Data": {
                        "MatchGuid": "smoke-match",
                        "Game": {},
                        "Players": [
                            {"PrimaryId": "smoke-player", "Name": "Me", "TeamNum": 0},
                            {"PrimaryId": "smoke-mate", "Name": "Mate", "TeamNum": 0, "Boost": 75},
                        ],
                    },
                },
                "2026-10-18T18:00:00+00:00",
                False,
            )
            QTimer.singleShot(0, lambda: accept_boost_warning(app))
            window.settings.boost_overlay.scope.setCurrentIndex(2)
            boost_hud = window.boost_overlay.window
            if boost_hud is None or not boost_hud.isVisible():
                raise RuntimeError("Bundled teammate boost overlay is missing")
            if set(boost_hud.gauges) != {"smoke-mate"}:
                raise RuntimeError("Bundled boost overlay does not exclude the selected player")
            game_api.foreground = 0
            presence.check()
            if overlay.isVisible() or boost_hud.isVisible():
                raise RuntimeError("Bundled overlays remain visible outside the game")
            game_api.foreground = 10
            presence.check()
            if not overlay.isVisible() or not boost_hud.isVisible():
                raise RuntimeError("Bundled overlays do not return when game focus is restored")
            window._connection_lost()
            if boost_hud.isVisible():
                raise RuntimeError("Bundled boost overlay retains disconnected telemetry")
            QTimer.singleShot(100, window.close)
            return app.exec()
        finally:
            store.close()


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        parser = argparse.ArgumentParser(description="Validate the Windows application bundle")
        parser.add_argument("--smoke-test", action="store_true")
        parser.add_argument("--expected-version")
        arguments = parser.parse_args()
        raise SystemExit(smoke_test(arguments.expected_version))
    raise SystemExit(main())
