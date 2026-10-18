"""Persist user intent, not temporary visibility or received telemetry."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from rocket_lantern.storage import MatchStore, Summary
from rocket_lantern.window import MainWindow


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    widget = MainWindow(store)
    yield widget
    widget.close()
    store.close()


@pytest.mark.parametrize(
    ("summary_enabled", "boost_enabled"), [(True, False), (False, True), (True, True)]
)
def test_overlays_should_restore_independent_activation_from_a_reopened_database(
    application: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    summary_enabled: bool,
    boost_enabled: bool,
) -> None:
    warning = Mock(return_value=QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    path = tmp_path / "preferences.sqlite3"
    store = MatchStore(path)
    window = MainWindow(store)
    window.settings.overlay.enabled.setChecked(summary_enabled)
    window.settings.boost_overlay.enabled.setChecked(boost_enabled)
    window.close()
    store.close()
    warning.reset_mock()

    restored_store = MatchStore(path)
    save = Mock(wraps=restored_store.set_settings)
    monkeypatch.setattr(restored_store, "set_settings", save)
    restored = MainWindow(restored_store)
    try:
        assert restored.settings.overlay.enabled.isChecked() == summary_enabled
        assert restored.settings.boost_overlay.enabled.isChecked() == boost_enabled
        if summary_enabled:
            assert restored.overlay.window.isVisible()
        else:
            assert restored.overlay.window is None
        assert restored.boost_overlay.window is None, "Wait for live data even when enabled"
        assert restored.boost_overlay._risk_accepted == boost_enabled
        if boost_enabled:
            restored.live.set_player("me")
            restored.live.observe(
                {
                    "Event": "UpdateState",
                    "Data": {
                        "MatchGuid": "live",
                        "Game": {},
                        "Players": [
                            {"PrimaryId": "me", "Name": "Me", "TeamNum": 0},
                            {"PrimaryId": "mate", "Name": "Mate", "TeamNum": 0, "Boost": 40},
                        ],
                    },
                },
                "2026-10-18T18:00:00+00:00",
                False,
            )
            assert restored.boost_overlay.window.isVisible()
            assert set(restored.boost_overlay.window.gauges) == {"mate"}
        save.assert_not_called()
        warning.assert_not_called()
    finally:
        restored.close()
        restored_store.close()


def test_overlays_should_restore_explicitly_disabled_preferences(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=QMessageBox.StandardButton.Yes))
    window.settings.overlay.enabled.setChecked(True)
    window.settings.boost_overlay.enabled.setChecked(True)
    window.settings.overlay.enabled.setChecked(False)
    window.settings.boost_overlay.enabled.setChecked(False)

    restored = MainWindow(window.store)
    try:
        assert not restored.settings.overlay.enabled.isChecked()
        assert not restored.settings.boost_overlay.enabled.isChecked()
        assert restored.overlay.window is None
        assert restored.boost_overlay.window is None
        assert window.store.setting("overlay_enabled") == "0"
        assert window.store.setting("boost_overlay_enabled") == "0"
        assert restored.boost_overlay._risk_accepted
    finally:
        restored.close()


def test_boost_should_require_consent_when_only_an_enabled_flag_was_saved(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.store.set_setting("boost_overlay_enabled", "1")
    warning = Mock(return_value=QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    restored = MainWindow(window.store)
    try:
        assert not restored.settings.boost_overlay.enabled.isChecked()
        warning.assert_not_called()
        restored.settings.boost_overlay.enabled.setChecked(True)
        warning.assert_called_once()
        assert window.store.setting("boost_overlay_risk_accepted") == "1"
    finally:
        restored.close()


def test_boost_should_not_persist_activation_or_consent_when_warning_is_cancelled(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        QMessageBox, "warning", Mock(return_value=QMessageBox.StandardButton.Cancel)
    )

    window.settings.boost_overlay.enabled.setChecked(True)

    assert window.store.setting("boost_overlay_enabled") == ""
    assert window.store.setting("boost_overlay_risk_accepted") == ""


@pytest.mark.parametrize("previously_enabled", [False, True])
def test_overlay_should_restore_previous_ui_and_report_failure_when_preference_cannot_be_saved(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, previously_enabled: bool
) -> None:
    window.settings.overlay.enabled.setChecked(previously_enabled)
    failed = Mock()
    window.overlay.failed.connect(failed)
    monkeypatch.setattr(
        window.store, "set_settings", Mock(side_effect=sqlite3.OperationalError("full"))
    )

    window.settings.overlay.enabled.setChecked(not previously_enabled)

    assert window.settings.overlay.enabled.isChecked() == previously_enabled
    if window.overlay.window is not None:
        assert window.overlay.window.isVisible() == previously_enabled
    failed.assert_called_once_with()


def test_boost_should_save_consent_and_activation_together_without_writing_on_each_packet(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=QMessageBox.StandardButton.Yes))
    save = Mock(wraps=window.store.set_settings)
    monkeypatch.setattr(window.store, "set_settings", save)

    window.settings.boost_overlay.enabled.setChecked(True)

    save.assert_called_once_with({"boost_overlay_enabled": "1", "boost_overlay_risk_accepted": "1"})
    save.reset_mock()
    for _ in range(3):
        window.live.observe(
            {"Event": "UpdateState", "Data": {"MatchGuid": "live", "Game": {}, "Players": []}},
            "2026-10-18T18:00:00+00:00",
            False,
        )
    window.boost_overlay._expire()
    window.matches.counters.set_summary(Summary(2, 1, 0))
    window.close()
    save.assert_not_called()
    assert window.store.setting("boost_overlay_enabled") == "1"


def test_boost_should_not_persist_consent_after_a_failed_preference_write(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(
        window.store, "set_settings", Mock(side_effect=sqlite3.OperationalError("full"))
    )
    failed = Mock()
    window.boost_overlay.failed.connect(failed)

    window.settings.boost_overlay.enabled.setChecked(True)

    assert not window.settings.boost_overlay.enabled.isChecked()
    assert window.store.setting("boost_overlay_enabled") == ""
    assert window.store.setting("boost_overlay_risk_accepted") == ""
    failed.assert_called_once_with()


def test_overlay_should_preserve_activation_when_no_screen_is_temporarily_available(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.settings.overlay.enabled.setChecked(True)
    hud = window.overlay.window
    screens = QGuiApplication.screens()
    primary = QGuiApplication.primaryScreen()
    monkeypatch.setattr(QGuiApplication, "screens", lambda: [])
    monkeypatch.setattr(QGuiApplication, "primaryScreen", lambda: None)

    window.overlay._refresh_screens()

    assert not hud.isVisible()
    assert window.settings.overlay.enabled.isChecked()
    assert window.store.setting("overlay_enabled") == "1"
    monkeypatch.setattr(QGuiApplication, "screens", lambda: screens)
    monkeypatch.setattr(QGuiApplication, "primaryScreen", lambda: primary)
    window.overlay._refresh_screens()
    assert hud.isVisible()
