"""Render documentation screenshots with fictional data and no game connection."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from rocket_lantern.app import configure_application
from rocket_lantern.i18n import language_manager, text
from rocket_lantern.match_data import MatchCollector
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult
from rocket_lantern.window import MainWindow

OUTPUT_DIRECTORY = Path(__file__).resolve().parents[1] / "docs/images"
PLAYER_ID = "demo-nova"
STARTED_AT = datetime(2026, 10, 10, 19, tzinfo=UTC)


def configure_preview_theme(app: QApplication) -> None:
    """Use Qt's real dark widgets, loading a local font for offscreen rendering."""
    app.setStyle("Fusion")
    windows_directory = os.environ.get("WINDIR")
    if windows_directory is not None:
        font_path = Path(windows_directory) / "Fonts/segoeui.ttf"
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
            app.setFont(QFont("Segoe UI", 10))
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#202124",
        QPalette.ColorRole.WindowText: "#eeeeee",
        QPalette.ColorRole.Base: "#282a2e",
        QPalette.ColorRole.AlternateBase: "#303237",
        QPalette.ColorRole.Text: "#eeeeee",
        QPalette.ColorRole.Button: "#303237",
        QPalette.ColorRole.ButtonText: "#eeeeee",
        QPalette.ColorRole.Highlight: "#1976b8",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: "#303237",
        QPalette.ColorRole.ToolTipText: "#eeeeee",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#777777"))
    app.setPalette(palette)


def demo_player(primary_id: str, name: str, team: int, boost: int, goals: int) -> dict[str, object]:
    """Provide all displayed counters using fictional player identities."""
    return {
        "PrimaryId": primary_id,
        "Name": name,
        "TeamNum": team,
        "Boost": boost,
        "Score": 120 + goals * 100,
        "Goals": goals,
        "Assists": 1,
        "Saves": 2,
        "Shots": goals + 2,
        "Touches": 12 + goals * 4,
        "CarTouches": 3,
        "Demos": 1,
    }


def populate_history(store: MatchStore) -> int:
    """Seed one fixed session, including partial and unknown observations."""
    collector = MatchCollector()
    outcomes = ("win", "loss", "win", "win", "loss", "win", "win", "loss", "win", "win")
    for index, outcome in enumerate(outcomes):
        observed_at = (STARTED_AT + timedelta(minutes=index * 5)).isoformat()
        guid = f"demo-match-{index}"
        blue_score = 3
        orange_score = 1
        if outcome == "loss":
            blue_score = 1
            orange_score = 2
        snapshot = collector.observe(
            {
                "Event": "UpdateState",
                "Data": {
                    "MatchGuid": guid,
                    "Game": {
                        "PlaylistId": 13,
                        "Arena": "Stadium_P",
                        "bHasWinner": True,
                        "bOvertime": index == 3,
                        "Teams": [
                            {"TeamNum": 0, "Score": blue_score},
                            {"TeamNum": 1, "Score": orange_score},
                        ],
                    },
                    "Players": [demo_player(PLAYER_ID, "Nova", 0, 45, blue_score - 1)],
                },
            },
            observed_at,
        )
        if snapshot is None:
            raise RuntimeError("Synthetic match was not collected")
        store.save_details(snapshot)
        store.save(MatchResult(guid, PLAYER_ID, observed_at, 13, outcome))
    store.save(MatchResult("demo-unknown", PLAYER_ID, "2026-10-10T19:50:00+00:00", 13, "unknown"))
    return store.sessions(PLAYER_ID)[0]["id"]


def live_message() -> dict[str, object]:
    """Show a selected player and teammates at contrasting boost levels."""
    return {
        "Event": "UpdateState",
        "Data": {
            "MatchGuid": "demo-live",
            "Game": {
                "PlaylistId": 13,
                "Arena": "Stadium_P",
                "TimeSeconds": 123,
                "bOvertime": False,
                "Teams": [{"TeamNum": 0, "Score": 2}, {"TeamNum": 1, "Score": 1}],
                "Ball": {"Speed": 1850, "TeamNum": 0},
            },
            "Players": [
                demo_player(PLAYER_ID, "Nova", 0, 45, 1),
                demo_player("demo-orbit", "Orbit", 0, 76, 1),
                demo_player("demo-comet", "Comet", 0, 18, 0),
                demo_player("demo-eclipse", "Eclipse", 1, 62, 1),
                demo_player("demo-pulse", "Pulse", 1, 34, 0),
                demo_player("demo-drift", "Drift", 1, 12, 0),
            ],
        },
    }


def main() -> None:
    """Save real widget captures; never call start() or open the user's database."""
    app = QApplication(["screenshots", "-platform", "offscreen"])
    configure_application(app)
    configure_preview_theme(app)
    language_manager().set_language("en")
    store = MatchStore(":memory:")
    store.set_setting("evaluation_hotkeys_enabled", "0")
    store.set_setting("player_id", PLAYER_ID)
    store.set_setting("player_name", "Nova")
    session_id = populate_history(store)
    window = MainWindow(store)
    try:
        window.resize(1280, 800)
        window.show()
        message = live_message()
        window.matches.observe(message, "Match suivi ; en attente du résultat.")
        window.live.observe(message, "2026-10-10T19:55:00+00:00", False)
        window.matches.period.setCurrentIndex(window.matches.period.findData(session_id))
        window.client._status(text("Connecté • événements reçus"))
        OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
        for tab, filename in ((1, "rocket-lantern.png"), (0, "rocket-lantern-matches.png")):
            window.tabs.setCurrentIndex(tab)
            app.processEvents()
            app.processEvents()
            screenshot = window.grab()
            if not screenshot.save(str(OUTPUT_DIRECTORY / filename)):
                raise OSError(f"Cannot save screenshot: {filename}")
    finally:
        window.close()
        store.close()


if __name__ == "__main__":
    main()
