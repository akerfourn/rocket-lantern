"""Placement transactions, screen-relative coordinates and explicit editor lifecycle."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, QPointF, QRect, QSize, Qt
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


@pytest.mark.parametrize("settings_open", [False, True])
def test_summary_shortcut_should_open_wl_overlay_settings_without_enabling_it(
    window: MainWindow,
    settings_open: bool,
) -> None:
    settings = window.settings
    settings.sections.setCurrentWidget(settings.general_section)
    settings.overlay_tabs.setCurrentWidget(settings.boost_overlay)
    window.tabs.setCurrentWidget(window.live)
    if settings_open:
        settings.show()
    previous_activation = window.store.setting("overlay_enabled")

    window.matches.counters.overlay_button.click()

    assert settings.isVisible()
    assert settings.sections.currentWidget() is settings.overlay_section
    assert settings.overlay_tabs.currentWidget() is settings.overlay
    assert not settings.overlay.enabled.isChecked()
    assert window.store.setting("overlay_enabled") == previous_activation
    assert window.tabs.currentWidget() is window.live


def test_summary_overlay_shortcut_should_translate_in_place(
    window: MainWindow,
    application: QApplication,
) -> None:
    button = window.matches.counters.overlay_button

    language_manager().set_language("en")
    application.processEvents()

    try:
        assert button.toolTip() == "Configure the W/L summary overlay"
        assert button.accessibleName() == button.toolTip()
    finally:
        language_manager().set_language("fr")


def test_placement_should_keep_custom_overlay_inside_screen_after_resolution_and_width_change() -> (
    None
):
    placement = OverlayPlacement("right", "top_right", 1.0, 1.0)

    assert placement.position(QRect(100, 50, 800, 600), QSize(300, 46)) == QPoint(600, 604)
    assert placement.position(QRect(100, 50, 20, 10), QSize(300, 46)) == QPoint(100, 50)


@pytest.mark.parametrize("anchor,offset", [("left", 0), ("center", 50), ("right", 100)])
def test_placement_should_keep_chosen_reference_fixed_when_width_changes(
    anchor: str, offset: int
) -> None:
    bounds = QRect(-1920, -1080, 1920, 1080)
    point = QPoint(-1300, -900)
    placement = placement_from_position("left", "top_left", bounds, QSize(201, 46), point, anchor)

    restored = parse_placement(placement.serialize())

    assert restored.horizontal_anchor == anchor
    assert restored.position(bounds, QSize(201, 46)) == point
    assert restored.position(bounds, QSize(301, 46)) == point - QPoint(offset, 0)
    assert restored.position(bounds, QSize(101, 46)) == point + QPoint(offset, 0)


@pytest.mark.parametrize("anchor", ["left", "center", "right"])
def test_placement_should_scale_reference_with_screen_and_clamp_to_edges(anchor: str) -> None:
    placement = placement_from_position(
        "screen", "top_left", QRect(0, 0, 1000, 600), QSize(200, 40), QPoint(400, 280), anchor
    )
    expected_x = {"left": 900, "center": 1000, "right": 1100}

    assert placement.position(QRect(100, 50, 2000, 600), QSize(200, 40)) == QPoint(
        expected_x[anchor], 330
    )
    assert placement.position(QRect(100, 50, 20, 10), QSize(300, 46)) == QPoint(100, 50)


def test_placement_should_preserve_legacy_coordinates_without_an_anchor() -> None:
    placement = parse_placement(
        '{"screen":"left","corner":"top_left","x_ratio":0.25,"y_ratio":0.5}'
    )
    bounds = QRect(-1000, 0, 1000, 800)

    assert placement.horizontal_anchor is None
    assert placement.position(bounds, QSize(200, 40)) == QPoint(-800, 380)
    assert placement.position(bounds, QSize(400, 40)) == QPoint(-850, 380)


@pytest.mark.parametrize(
    "placement,anchor",
    [
        (OverlayPlacement(corner="top_right"), "right"),
        (OverlayPlacement(corner="bottom_left"), "left"),
        (OverlayPlacement(x_ratio=0.2, y_ratio=0.5), "left"),
        (OverlayPlacement(x_ratio=0.5, y_ratio=0.5), "center"),
        (OverlayPlacement(x_ratio=0.8, y_ratio=0.5), "right"),
    ],
)
def test_placement_should_suggest_an_anchor_for_legacy_data(
    placement: OverlayPlacement, anchor: str
) -> None:
    assert placement.editor_anchor() == anchor


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
        '{"horizontal_anchor":"unknown"}',
        '{"horizontal_anchor":true}',
        '{"horizontal_anchor":[]}',
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


@pytest.mark.parametrize("anchor", ["left", "center", "right"])
def test_editor_should_keep_preview_and_live_reference_fixed_when_summary_grows(
    window: MainWindow, anchor: str
) -> None:
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor
    editor.preview.place(QPoint(300, 180))
    original = editor.preview.geometry()

    editor.anchor_buttons.buttons[anchor].click()

    assert editor.preview.geometry() == original
    assert window.store.setting("overlay_placement") == ""
    window.matches.counters.set_summary(Summary(12345, 1234, 0))
    enlarged = editor.preview.geometry()
    assert enlarged.width() > original.width()
    if anchor == "left":
        assert enlarged.left() == original.left()
    elif anchor == "center":
        assert enlarged.x() + enlarged.width() // 2 == original.x() + original.width() // 2
    else:
        assert enlarged.right() == original.right()
    assert enlarged.y() == original.y()
    selected = editor.selected_position()
    editor.save_button.click()
    saved = parse_placement(window.store.setting("overlay_placement"))
    assert saved.horizontal_anchor == anchor
    window.settings.overlay.enabled.setChecked(True)
    hud = window.overlay.window
    assert hud.pos() == selected
    width = hud.width()

    window.matches.counters.set_summary(Summary(0, 0, 0))

    shrink = width - hud.width()
    expected_shift = {"left": 0, "center": width // 2 - hud.width() // 2, "right": shrink}
    assert hud.pos() == selected + QPoint(expected_shift[anchor], 0)
    window.settings.overlay.place_button.click()
    assert window.overlay.editor.anchor_buttons.selected_anchor() == anchor


def test_editor_should_preserve_legacy_position_when_saving_new_anchor(window: MainWindow) -> None:
    window.overlay._set_placement(OverlayPlacement(x_ratio=0.8, y_ratio=0.3))
    window.settings.overlay.enabled.setChecked(True)
    original = window.overlay.window.pos()

    window.settings.overlay.place_button.click()
    editor = window.overlay.editor

    assert editor.selected_position() == original
    assert editor.anchor_buttons.selected_anchor() == "right"
    editor.save_button.click()
    assert window.overlay.window.pos() == original
    assert window.overlay._placement.horizontal_anchor == "right"


def test_editor_should_save_independent_anchors_for_boost_and_summary(window: MainWindow) -> None:
    window.settings.overlay.place_button.click()
    window.overlay.editor.anchor_buttons.buttons["center"].click()
    window.overlay.editor.save_button.click()
    window.settings.boost_overlay.place_button.click()
    window.boost_overlay.editor.anchor_buttons.buttons["right"].click()
    window.boost_overlay.editor.save_button.click()

    assert parse_placement(window.store.setting("overlay_placement")).horizontal_anchor == "center"
    assert (
        parse_placement(window.store.setting("boost_overlay_placement")).horizontal_anchor
        == "right"
    )
    window.settings.overlay.place_button.click()
    window.overlay.editor.anchor_buttons.buttons["left"].click()
    window.overlay.editor.cancel_button.click()
    assert parse_placement(window.store.setting("overlay_placement")).horizontal_anchor == "center"


@pytest.mark.parametrize("boost", [False, True])
def test_anchor_buttons_should_be_icon_only_exclusive_and_keyboard_accessible(
    window: MainWindow, boost: bool
) -> None:
    controls = window.settings.overlay
    controller = window.overlay
    if boost:
        controls = window.settings.boost_overlay
        controller = window.boost_overlay
    controls.place_button.click()
    editor = controller.editor
    buttons = editor.anchor_buttons.buttons
    original_geometry = editor.preview.geometry()

    for anchor, button in buttons.items():
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)

        assert editor.anchor_buttons.selected_anchor() == anchor
        assert editor.preview.horizontal_anchor == anchor
        assert [key for key, item in buttons.items() if item.isChecked()] == [anchor]
        assert button.text() == ""
        assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        assert not button.icon().isNull()
        assert button.toolTip() == button.accessibleName()
        assert editor.preview.geometry() == original_geometry
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert button.isChecked(), "The active alignment cannot be unchecked"

    buttons["center"].setFocus()
    QTest.keyClick(buttons["center"], Qt.Key.Key_Space)

    assert editor.anchor_buttons.selected_anchor() == "center"
    assert editor.preview.horizontal_anchor == "center"
    images = [button.icon().pixmap(20, 20).toImage() for button in buttons.values()]
    assert images[0] != images[1] and images[1] != images[2] and images[0] != images[2]
    assert window.store.setting(controller._placement_key) == ""


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


@pytest.mark.parametrize("boost", [False, True])
def test_toolbar_should_fade_only_when_preview_overlaps_without_changing_settings(
    window: MainWindow, boost: bool
) -> None:
    controls = window.settings.overlay
    controller = window.overlay
    if boost:
        controls = window.settings.boost_overlay
        controller = window.boost_overlay
    controls.place_button.click()
    editor = controller.editor
    original = window.store.connection.execute("SELECT * FROM settings ORDER BY key").fetchall()
    editor.preview.place(QPoint(20, editor.toolbar.geometry().bottom() + 20))
    assert editor.toolbar_opacity.opacity() == 1.0
    target = editor.toolbar.pos() + QPoint(10, 10)

    editor.preview.place(target)

    assert editor.preview.pos() == target
    assert editor.toolbar_opacity.opacity() == 0.35
    area = editor.preview.geometry().intersected(editor.toolbar.geometry())
    with_preview = editor.grab(area).toImage()
    editor.preview.hide()
    assert editor.grab(area).toImage() != with_preview, "The preview must show through the panel"
    editor.preview.show()
    QTest.mouseClick(editor.locate_button, Qt.MouseButton.LeftButton)
    assert editor.locate_animation.state() == QAbstractAnimation.State.Running
    editor.preview.place(QPoint(20, editor.toolbar.geometry().bottom() + 20))
    assert editor.toolbar_opacity.opacity() == 1.0
    assert (
        window.store.connection.execute("SELECT * FROM settings ORDER BY key").fetchall()
        == original
    )
    assert not controls.activation_enabled()


def test_toolbar_should_recheck_overlap_when_preview_width_changes(window: MainWindow) -> None:
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor
    editor.set_horizontal_anchor("left")
    editor.preview.place(QPoint(0, editor.toolbar.y() + 10))
    editor.toolbar.setFixedWidth(180)
    editor.toolbar.move(editor.preview.geometry().right() + 1, editor.toolbar.y())
    editor._update_toolbar_opacity()
    assert editor.toolbar_opacity.opacity() == 1.0

    window.matches.counters.set_summary(Summary(12345, 1234, 0))

    assert editor.toolbar.geometry().intersects(editor.preview.geometry())
    assert editor.toolbar_opacity.opacity() == 0.35


@pytest.mark.parametrize("boost", [False, True])
def test_locator_should_animate_both_previews_without_changing_position_or_settings(
    window: MainWindow,
    boost: bool,
) -> None:
    controls = window.settings.overlay
    controller = window.overlay
    if boost:
        controls = window.settings.boost_overlay
        controller = window.boost_overlay
    controls.place_button.click()
    editor = controller.editor
    editor.preview.place(QPoint(120, 210))
    original_geometry = editor.preview.geometry()
    original_settings = window.store.connection.execute(
        "SELECT * FROM settings ORDER BY key"
    ).fetchall()

    editor.locate_button.click()
    editor.locate_animation.setCurrentTime(400)

    assert editor.locate_animation.state() == QAbstractAnimation.State.Running
    assert editor.locate_animation.duration() == 800
    assert editor.locate_animation.loopCount() == 1
    assert editor.preview.geometry() == original_geometry
    assert (
        window.store.connection.execute("SELECT * FROM settings ORDER BY key").fetchall()
        == original_settings
    )
    assert not controls.activation_enabled()
    assert controller.window is None
    editor.locate_button.click()
    assert editor.locate_animation.currentTime() == 0
    editor.locate_animation.setCurrentTime(editor.locate_animation.duration())
    assert editor.locate_animation.state() == QAbstractAnimation.State.Stopped


def test_locator_should_render_one_visible_pulse_and_restore_normal_appearance(
    window: MainWindow,
) -> None:
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor
    editor.preview.place(QPoint(120, 210))
    area = editor.preview.geometry().adjusted(-60, -60, 60, 60).intersected(editor.rect())
    original = editor.grab(area).toImage()

    editor.locate_button.click()
    editor.locate_animation.setCurrentTime(400)
    highlighted = editor.grab(area).toImage()

    assert highlighted != original
    editor.locate_animation.setCurrentTime(650)
    assert editor.grab(area).toImage() != highlighted
    editor.locate_animation.setCurrentTime(editor.locate_animation.duration())
    assert editor.grab(area).toImage() == original


@pytest.mark.parametrize("action", ["save_button", "cancel_button", "shutdown"])
def test_locator_should_stop_when_placement_editor_closes(window: MainWindow, action: str) -> None:
    window.settings.overlay.place_button.click()
    editor = window.overlay.editor
    editor.locate_button.click()

    if action == "shutdown":
        window.close()
    else:
        getattr(editor, action).click()

    assert editor.locate_animation.state() == QAbstractAnimation.State.Stopped
    assert not editor.isVisible()


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
        assert window.settings.sections.count() == 4
        assert window.settings.sections.tabText(3) == "Sound alerts"
        assert window.settings.manage_labels.text() == "Manage labels…"
        assert editor.save_button.text() == "Save"
        assert editor.cancel_button.text() == "Cancel"
        assert editor.locate_button.text() == "Locate"
        assert editor.locate_button.toolTip() == "Show an animated marker around the overlay."
        assert editor.anchor_label.text() == "Horizontal anchor:"
        assert [button.toolTip() for button in editor.anchor_buttons.buttons.values()] == [
            "Left",
            "Center",
            "Right",
        ]
        for button in editor.anchor_buttons.buttons.values():
            assert button.accessibleName() == button.toolTip()
        assert editor.preview.pos() == QPoint(200, 150)
    finally:
        language_manager().set_language("fr")
