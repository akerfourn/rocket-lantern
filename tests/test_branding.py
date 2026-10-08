"""Branding, packaged icon resolutions and compatibility with existing data."""

import struct
from pathlib import Path

import pytest
from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtWidgets import QApplication, QLabel

from rocket_lantern import branding
from rocket_lantern.app import configure_application, local_data_directory
from rocket_lantern.branding import APP_NAME, ASSET_DIRECTORY, ICON_SIZES, application_icon
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow


def test_window_should_show_rocket_lantern_name_and_logo(application: QApplication) -> None:
    store = MatchStore(":memory:")
    window = MainWindow(store)
    try:
        assert window.windowTitle() == APP_NAME
        assert not window.windowIcon().isNull()
        logo = window.findChild(QLabel, "application_logo")
        assert logo is not None
        assert not logo.pixmap().isNull()
        assert any(label.text() == APP_NAME for label in window.findChildren(QLabel))
    finally:
        window.close()
        store.close()


def test_icon_should_include_explicit_sizes_and_transparent_corners(
    application: QApplication,
) -> None:
    icon = application_icon()
    assert {size.width() for size in icon.availableSizes()} == set(ICON_SIZES)
    for size in (*ICON_SIZES, 512, 1024):
        image = QImage(str(ASSET_DIRECTORY / f"rocket-lantern-{size}.png"))
        assert (image.width(), image.height()) == (size, size)
        assert image.hasAlphaChannel()
        assert image.pixelColor(0, 0).alpha() == 0
        assert image.pixelColor(size - 1, size - 1).alpha() == 0
        assert image.pixelColor(size // 2, size // 2).alpha() == 255


def test_icon_should_keep_the_lantern_centered_with_balanced_margins() -> None:
    image = QImage(str(ASSET_DIRECTORY / "rocket-lantern-256.png"))
    points: list[tuple[int, int]] = []
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() > 240 and max(color.red(), color.green(), color.blue()) > 100:
                points.append((x, y))
    left = min(x for x, y in points)
    right = max(x for x, y in points)
    top = min(y for x, y in points)
    bottom = max(y for x, y in points)

    assert abs(left + right - 255) <= 2
    assert abs(top + bottom - 255) <= 2
    assert left >= 24 and right <= 231
    assert top >= 24 and bottom <= 231


def test_windows_icon_should_contain_all_png_resolutions(application: QApplication) -> None:
    path = ASSET_DIRECTORY / "rocket-lantern.ico"
    data = path.read_bytes()
    assert struct.unpack_from("<HHH", data) == (0, 1, len(ICON_SIZES))
    for index, size in enumerate(ICON_SIZES):
        width, height, colors, reserved, planes, bits, length, offset = struct.unpack_from(
            "<BBBBHHII", data, 6 + index * 16
        )
        assert (width or 256, height or 256) == (size, size)
        assert (colors, reserved, planes, bits) == (0, 0, 1, 32)
        assert (
            data[offset : offset + length]
            == (ASSET_DIRECTORY / f"rocket-lantern-{size}.png").read_bytes()
        )
    assert QImageReader(str(path)).imageCount() == len(ICON_SIZES)


def test_icon_should_fail_explicitly_when_assets_are_missing(
    application: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(branding, "ASSET_DIRECTORY", tmp_path)
    with pytest.raises(FileNotFoundError, match="Missing application icon"):
        application_icon()


def test_renaming_should_keep_the_existing_qt_data_directory(application: QApplication) -> None:
    previous_name = application.applicationName()
    previous_display_name = application.applicationDisplayName()
    previous_organization = application.organizationName()
    previous_icon = application.windowIcon()
    try:
        application.setApplicationName("RLWinLoss")
        application.setOrganizationName("RLWinLoss")
        expected = Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        )

        configure_application(application)

        assert application.applicationName() == APP_NAME
        assert application.applicationDisplayName() == APP_NAME
        assert not application.windowIcon().isNull()
        assert local_data_directory() == expected
    finally:
        application.setApplicationName(previous_name)
        application.setApplicationDisplayName(previous_display_name)
        application.setOrganizationName(previous_organization)
        application.setWindowIcon(previous_icon)


def test_data_directory_should_reopen_existing_sqlite_after_rename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    legacy = tmp_path / "RLWinLoss" / "RLWinLoss"
    legacy.mkdir(parents=True)
    path = legacy / "matches.sqlite3"
    store = MatchStore(path)
    store.set_setting("player_id", "test-player")
    store.close()
    modern_location = tmp_path / "RLWinLoss" / APP_NAME
    monkeypatch.setattr(QStandardPaths, "writableLocation", lambda location: str(modern_location))

    reopened = MatchStore(local_data_directory() / "matches.sqlite3")
    try:
        assert reopened.setting("player_id") == "test-player"
        assert not modern_location.exists()
    finally:
        reopened.close()


def test_data_directory_should_reject_an_empty_qt_location(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(QStandardPaths, "writableLocation", lambda location: "")
    with pytest.raises(OSError, match="No writable application data directory"):
        local_data_directory()
