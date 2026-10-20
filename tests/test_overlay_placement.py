"""Placement transactions, screen-relative coordinates and explicit editor lifecycle."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from rocket_lantern.game_installations import DiscoveryReport, GameInstallation
from rocket_lantern.game_installations_panel import ConfigurationCheck
from rocket_lantern.i18n import language_manager
from rocket_lantern.overlay_placement import (
    OverlayPlacement,
    parse_placement,
    placement_from_position,
)
from rocket_lantern.packet_configuration import RateConfiguration
from rocket_lantern.storage import MatchStore, Summary
from rocket_lantern.window import MainWindow


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    widget = MainWindow(store)
    widget.show()
    yield widget
    widget.close()
    store.close()


def test_placement_should_round_trip_custom_position_on_negative_coordinate_monitor() -> None:
    bounds = QRect(-1920, -1080, 1920, 1080)
    size = QSize(200, 46)
    point = QPoint(-1600, -900)

    placement = placement_from_position("left", "top_left", bounds, size, point)
    restored = parse_placement(placement.serialize())

    assert restored.position(bounds, size) == point
    assert restored.screen == "left"


def test_placement_should_keep_custom_overlay_inside_screen_after_resolution_and_width_change() -> (
    None
):
    placement = OverlayPlacement("right", "top_right", 1.0, 1.0)

    assert placement.position(QRect(100, 50, 800, 600), QSize(300, 46)) == QPoint(600, 604)
    assert placement.position(QRect(100, 50, 20, 10), QSize(300, 46)) == QPoint(100, 50)


@pytest.mark.parametrize(
    "value",
    [
        "not-json",
        "[]",
        '{"corner":"unknown"}',
        '{"screen":4}',
        '{"x_ratio":true,"y_ratio":0}',
        '{"x_ratio":1.1,"y_ratio":0}',
        '{"x_ratio":0.1}',
        '{"x_ratio":NaN,"y_ratio":0}',
    ],
)
def test_placement_should_reject_invalid_saved_coordinates(value: str) -> None:
    with pytest.raises(ValueError):
        parse_placement(value)


def test_editor_should_save_dragged_position_without_enabling_overlay(window: MainWindow) -> None:
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor
    assert editor is not None and editor.isVisible()
    assert window.overlay.window is None
    editor.preview.place(QPoint(120, 180))
    selected = editor.selected_position()

    editor.save_button.click()

    assert window.overlay.editor is None
    assert not window.settings.overlay.enabled.isChecked()
    assert window.settings.overlay.corner.currentData() == "custom"
    saved = parse_placement(window.store.setting("overlay_placement"))
    window.settings.overlay.enabled.setChecked(True)
    assert window.overlay.window.pos() == selected
    reopened = MainWindow(window.store)
    try:
        assert reopened.settings.overlay.enabled.isChecked()
        assert reopened.settings.overlay.corner.currentData() == "custom"
        assert reopened.overlay._placement == saved
    finally:
        reopened.close()


def test_editor_should_cancel_without_persisting_and_restore_click_through_hud(
    window: MainWindow,
) -> None:
    window.settings.overlay.enabled.setChecked(True)
    overlay = window.overlay.window
    original = overlay.pos()
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor
    assert not overlay.isVisible()
    editor.preview.place(QPoint(200, 100))

    editor.cancel_button.click()

    assert window.overlay.editor is None
    assert window.store.setting("overlay_placement") == ""
    assert overlay.pos() == original
    assert overlay.isVisible()
    assert overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput


def test_editor_should_support_mouse_dragging_and_clamp_to_screen_edges(
    window: MainWindow,
    application: QApplication,
) -> None:
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor
    preview = editor.preview
    QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    target = editor.mapToGlobal(QPoint(150, 180))
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(preview.mapFromGlobal(target)),
        QPointF(target),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    QApplication.sendEvent(preview, move)
    QTest.mouseRelease(preview, Qt.MouseButton.LeftButton)

    assert preview.pos() == QPoint(145, 175)
    preview.place(QPoint(-100, -100))
    assert preview.pos() == QPoint(0, 0)
    preview.place(QPoint(10000, 10000))
    assert preview.geometry().right() < editor.width()
    assert preview.geometry().bottom() < editor.height()


def test_editor_should_restore_saved_position_when_escape_is_pressed(window: MainWindow) -> None:
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor

    QTest.keyClick(editor, Qt.Key.Key_Escape)

    assert window.overlay.editor is None
    assert window.store.setting("overlay_placement") == ""


def test_editor_should_refresh_preview_without_writing_or_duplicating_real_hud(
    window: MainWindow,
) -> None:
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor
    window.settings.overlay.place_button.click()
    assert window.overlay.editor is editor

    window.matches.counters.set_summary(Summary(12, 3, 0))

    assert editor.preview.wins.text() == "12"
    assert editor.preview.balance.text() == "+9"
    assert window.overlay.window is None
    assert window.store.setting("overlay_placement") == ""


def test_editor_should_report_storage_error_and_keep_previous_placement(
    window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = window.overlay._placement
    failed = Mock()
    window.overlay.failed.connect(failed)
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor
    editor.preview.place(QPoint(120, 100))
    monkeypatch.setattr(
        window.store, "set_setting", Mock(side_effect=sqlite3.OperationalError("full"))
    )

    editor.save_button.click()

    failed.assert_called_once_with()
    assert window.overlay._placement == original


def test_editor_should_close_without_recreating_overlay_during_shutdown(window: MainWindow) -> None:
    window.settings.overlay.enabled.setChecked(True)
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor

    window.close()

    assert not editor.isVisible()
    assert window.overlay.editor is None
    assert window.overlay.window is None


def test_settings_should_keep_sections_independent_when_background_results_arrive(
    window: MainWindow,
    application: QApplication,
    tmp_path: Path,
) -> None:
    window.settings.show()
    application.processEvents()
    original_height = window.settings.height()
    installations = (GameInstallation("Steam", tmp_path, None),)
    result = ConfigurationCheck(
        DiscoveryReport(installations), (RateConfiguration(installations[0], rate=10),)
    )
    window.settings.game_installations._completed(result)
    application.processEvents()
    assert window.settings.height() == original_height
    window.settings.sections.setCurrentWidget(window.settings.overlay_section)
    application.processEvents()
    assert window.settings.overlay.place_button.isVisible()
    assert not window.settings.port.isVisible()
    window.settings.sections.setCurrentWidget(window.settings.general_section)
    application.processEvents()
    assert window.settings.height() == original_height
    assert not window.settings.overlay.place_button.isVisible()
    assert window.settings.sections.count() == 4


def test_editor_and_settings_should_translate_without_resetting_preview_position(
    window: MainWindow,
    application: QApplication,
) -> None:
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor
    editor.preview.place(QPoint(200, 150))

    language_manager().set_language("en")
    application.processEvents()

    try:
        assert window.settings.sections.tabText(0) == "General"
        assert window.settings.sections.tabText(3) == "Shortcuts"
        assert window.settings.manage_labels.text() == "Manage labels…"
        assert editor.save_button.text() == "Save"
        assert editor.cancel_button.text() == "Cancel"
        assert editor.preview.pos() == QPoint(200, 150)
    finally:
        language_manager().set_language("fr")
