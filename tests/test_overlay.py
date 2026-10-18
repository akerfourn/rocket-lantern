"""External HUD lifecycle, safe window flags and exact filtered-result mirroring."""

import json
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QLabel, QToolButton

from rocket_lantern.i18n import language_manager
from rocket_lantern.overlay_monitor import OverlayMonitor
from rocket_lantern.storage import MatchStore, Summary
from rocket_lantern.summary_overlay import SummaryOverlay, overlay_position
from rocket_lantern.tracker import MatchResult
from rocket_lantern.window import MainWindow


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    store.set_setting("player_id", "player")
    widget = MainWindow(store)
    widget.show()
    application.processEvents()
    yield widget
    widget.close()
    store.close()
    language_manager().set_language("fr")


@pytest.mark.parametrize(
    ("corner", "expected"),
    [
        ("top_left", QPoint(-1900, 20)),
        ("top_right", QPoint(-320, 20)),
        ("bottom_left", QPoint(-1900, 1000)),
        ("bottom_right", QPoint(-320, 1000)),
    ],
)
def test_overlay_position_should_use_selected_corner_on_negative_coordinate_monitor(
    corner: str,
    expected: QPoint,
) -> None:
    assert overlay_position(QRect(-1920, 0, 1920, 1080), QSize(300, 60), corner) == expected


def test_overlay_position_should_clamp_to_screen_when_available_area_is_small() -> None:
    assert overlay_position(QRect(50, 80, 100, 40), QSize(300, 60), "bottom_right") == QPoint(
        50, 80
    )


@pytest.mark.parametrize(
    ("summary", "delta"),
    [(Summary(0, 0, 4), "+0"), (Summary(12, 3, 0), "+9"), (Summary(2, 5, 0), "-3")],
)
def test_overlay_should_display_only_wins_losses_and_signed_delta(
    application: QApplication,
    summary: Summary,
    delta: str,
) -> None:
    overlay = SummaryOverlay()

    overlay.set_summary(summary)

    assert overlay.wins.text() == str(summary.wins)
    assert overlay.losses.text() == str(summary.losses)
    assert overlay.balance.text() == delta
    assert not overlay.balance_symbol.pixmap().isNull()
    assert overlay.width() < 450
    overlay.close()


def test_overlay_should_be_click_through_non_activating_and_independent_of_main_window(
    application: QApplication,
) -> None:
    overlay = SummaryOverlay()
    flags = overlay.windowFlags()

    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert flags & Qt.WindowType.WindowTransparentForInput
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert not overlay.testAttribute(Qt.WidgetAttribute.WA_QuitOnClose)
    assert overlay.parentWidget() is None
    assert overlay.focusPolicy() == Qt.FocusPolicy.NoFocus
    overlay.close()


def test_overlay_should_allocate_only_when_enabled_and_stop_showing_when_disabled(
    window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controls = window.settings.overlay
    assert not controls.enabled.isChecked()
    assert window.overlay.window is None
    assert not controls.options.isHidden()
    reader = Mock(side_effect=AssertionError("Overlay must not reload history"))
    monkeypatch.setattr(window.store, "filtered_history", reader)
    window.matches.counters.set_summary(Summary(3, 1, 1))

    controls.enabled.setChecked(True)

    overlay = window.overlay.window
    assert overlay is not None and overlay.isVisible()
    assert overlay.wins.text() == "3"
    assert overlay.losses.text() == "1"
    assert overlay.balance.text() == "+2"
    reader.assert_not_called()
    controls.enabled.setChecked(False)
    assert not overlay.isVisible()


def test_overlay_should_follow_filter_changes_and_new_results(window: MainWindow) -> None:
    window.store.save(MatchResult("trios", "player", "2026-01-01T18:00:00+00:00", 13, "win"))
    window.store.save(MatchResult("duos", "player", "2026-01-01T18:10:00+00:00", 11, "loss"))
    window.store.save(MatchResult("unknown", "player", "2026-01-01T18:20:00+00:00", 13, "unknown"))
    window._refresh()
    window.matches.period.setCurrentIndex(window.matches.period.findData("all"))
    window.matches.playlist_filter.setCurrentIndex(window.matches.playlist_filter.findData("all"))
    window.settings.overlay.enabled.setChecked(True)
    overlay = window.overlay.window
    assert overlay.wins.text() == "1"
    assert overlay.losses.text() == "1"
    assert overlay.balance.text() == "+0"

    window.matches.playlist_filter.setCurrentIndex(window.matches.playlist_filter.findData(13))

    assert overlay.wins.text() == "1"
    assert overlay.losses.text() == "0"
    assert overlay.balance.text() == "+1"
    window.store.save(MatchResult("next", "player", "2026-01-01T18:30:00+00:00", 13, "win"))
    window._refresh()
    assert overlay.balance.text() == "+2"


def test_overlay_should_move_to_selected_screen_and_corner(
    window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = Mock()
    first.name.return_value = "DISPLAY1"
    first.availableGeometry.return_value = QRect(0, 0, 1920, 1080)
    second = Mock()
    second.name.return_value = "DISPLAY2"
    second.availableGeometry.return_value = QRect(-1600, 0, 1600, 900)
    monkeypatch.setattr(QGuiApplication, "screens", lambda: [first, second])
    monkeypatch.setattr(QGuiApplication, "primaryScreen", lambda: first)
    window.overlay._refresh_screens()
    controls = window.settings.overlay
    controls.enabled.setChecked(True)
    controls.monitor.setCurrentIndex(controls.monitor.findData("DISPLAY2"))
    controls.corner.setCurrentIndex(controls.corner.findData("bottom_right"))
    overlay = window.overlay.window

    assert overlay.pos() == overlay_position(
        second.availableGeometry(), overlay.size(), "bottom_right"
    )

    monkeypatch.setattr(QGuiApplication, "screens", lambda: [first])
    window.overlay._refresh_screens()
    assert controls.monitor.currentData() == "DISPLAY1"
    assert overlay.pos() == overlay_position(
        first.availableGeometry(), overlay.size(), "bottom_right"
    )


def test_overlay_should_stay_visible_when_main_window_is_minimized_and_close_with_app(
    window: MainWindow,
    application: QApplication,
) -> None:
    window.settings.overlay.enabled.setChecked(True)
    overlay = window.overlay.window

    window.showMinimized()
    application.processEvents()

    assert overlay.isVisible()
    window.close()
    assert not overlay.isVisible()
    assert window.overlay.window is None


def test_overlay_should_translate_controls_and_accessibility_without_resetting_counts(
    window: MainWindow,
    application: QApplication,
) -> None:
    window.settings.overlay.enabled.setChecked(True)
    window.matches.counters.set_summary(Summary(3, 1, 0))

    language_manager().set_language("en")
    application.processEvents()

    assert window.settings.overlay.enabled.text() == "Show overlay"
    assert window.settings.overlay.corner.currentText() == "Top left"
    assert window.overlay.window.accessibleName() == "3 wins · 1 losses · delta +2"
    assert window.overlay.window.balance.text() == "+2"


def test_overlay_should_refresh_hidden_counts_before_showing_again(window: MainWindow) -> None:
    controls = window.settings.overlay
    controls.enabled.setChecked(True)
    overlay = window.overlay.window
    controls.enabled.setChecked(False)

    window.matches.counters.set_summary(Summary(5, 7, 2))
    controls.enabled.setChecked(True)

    assert window.overlay.window is overlay
    assert overlay.isVisible()
    assert overlay.wins.text() == "5"
    assert overlay.losses.text() == "7"
    assert overlay.balance.text() == "-2"


def test_overlay_should_hide_and_disable_controls_when_no_screen_is_available(
    window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controls = window.settings.overlay
    controls.enabled.setChecked(True)
    overlay = window.overlay.window
    monkeypatch.setattr(QGuiApplication, "screens", lambda: [])
    monkeypatch.setattr(QGuiApplication, "primaryScreen", lambda: None)

    window.overlay._refresh_screens()

    assert not overlay.isVisible()
    assert controls.enabled.isChecked()
    assert not controls.enabled.isEnabled()


def test_overlay_should_ignore_late_updates_after_shutdown(window: MainWindow) -> None:
    window.settings.overlay.enabled.setChecked(True)
    window.overlay.shutdown()
    window.settings.overlay.enabled.setChecked(False)

    window.settings.overlay.enabled.setChecked(True)
    window.matches.counters.set_summary(Summary(2, 1, 0))

    assert window.overlay.window is None


def test_overlay_should_keep_last_game_diagnostic_without_player_or_unrelated_app_details(
    window: MainWindow,
    application: QApplication,
) -> None:
    window.settings.overlay.enabled.setChecked(True)
    api = Mock()
    api.foreground_window.return_value = 10
    api.process_id.return_value = 100
    api.process_name.return_value = "RocketLeague.exe"
    api.window_rect.return_value = (0, 0, 1920, 1080)
    api.extended_style.return_value = 0x08080028
    api.is_above.return_value = True
    window.overlay.monitor = OverlayMonitor(api, window.overlay)
    window.overlay.monitor.start(20)
    api.foreground_window.return_value = 30
    api.process_name.return_value = "private-application.exe"
    window.overlay.monitor.check()

    diagnostic = window.overlay.diagnostic()
    result = json.loads(diagnostic)

    assert result["last_game_observation"]["game_window"] == 10
    assert result["last_game_observation"]["above_after"] is True
    assert "private-application" not in diagnostic
    assert "player_id" not in diagnostic
    assert "player_name" not in diagnostic
    window.settings.overlay.enabled.setChecked(False)
    assert not window.overlay.monitor.timer.isActive()


def test_overlay_settings_should_show_one_useful_display_tip_without_development_controls(
    window: MainWindow, application: QApplication
) -> None:
    settings = window.settings
    settings.show()
    settings.sections.setCurrentWidget(settings.overlay_section)
    for index in (0, 1):
        settings.overlay_tabs.setCurrentIndex(index)
        application.processEvents()
        assert settings.overlay_display_hint.isVisible()
        page = settings.overlay_tabs.currentWidget()
        assert page.findChildren(QToolButton) == []
        labels = [label.text() for label in page.findChildren(QLabel)]
        assert "Écran :" in labels
        assert "Position :" in labels
        assert not any("mémoris" in label for label in labels)
        assert not any("Diagnostic" in label for label in labels)
    hint = settings.overlay_display_hint.text()
    assert "Sans bords ou Fenêtré" in hint
    assert "plein écran" in hint
    assert "Risque de bannissement" in settings.boost_overlay.warning.text()
    assert sum(label.text() == hint for label in settings.overlay_section.findChildren(QLabel)) == 1

    language_manager().set_language("en")
    application.processEvents()

    assert "Borderless or Windowed" in settings.overlay_display_hint.text()
    assert "Risk of a ban" in settings.boost_overlay.warning.text()
