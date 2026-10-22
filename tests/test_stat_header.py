"""Render real Qt headers to catch left-aligned or illegible statistic icons."""

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QHeaderView

from rocket_lantern.branding import ASSET_DIRECTORY
from rocket_lantern.live_team_table import LiveTeamTable

ICON_FIELDS = (
    "score",
    "goals",
    "assists",
    "saves",
    "shots",
    "posts",
    "demos",
    "touches",
    "car_touches",
)


def test_stat_icons_should_render_from_packaged_svg_assets_with_transparent_corners(
    application: QApplication,
) -> None:
    table = LiveTeamTable()
    for column, field in enumerate(ICON_FIELDS, start=1):
        path = ASSET_DIRECTORY / f"stat-{field}.svg"
        renderer = QSvgRenderer(str(path))
        assert renderer.isValid(), f"Missing or invalid statistic asset: {field}"
        assert renderer.defaultSize() == QSize(24, 24)
        icon = table.horizontalHeaderItem(column).icon()
        for size in (20, 40):
            image = icon.pixmap(size, size).toImage()
            assert not image.isNull(), f"The {field} icon did not render at {size}px"
            assert image.pixelColor(0, 0).alpha() == 0
            assert image.pixelColor(image.width() - 1, image.height() - 1).alpha() == 0
    table.close()


@pytest.mark.parametrize(
    ("foreground", "background"),
    [("#171b21", "#eeeeee"), ("#edf1f7", "#252d38")],
)
def test_stat_header_should_keep_icons_centered_after_resize_and_follow_the_text_color(
    application: QApplication, foreground: str, background: str
) -> None:
    table = LiveTeamTable()
    table.resize(1100, 250)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
    header.setFixedHeight(36)
    palette = header.palette()
    color = QColor(foreground)
    palette.setColor(QPalette.ColorRole.ButtonText, color)
    palette.setColor(QPalette.ColorRole.Button, QColor(background))
    header.setPalette(palette)
    table.show()

    for width in (48, 104):
        for column in range(table.columnCount()):
            table.setColumnWidth(column, width)
        items = [table.horizontalHeaderItem(column) for column in range(1, table.columnCount())]
        icons = [QIcon(item.icon()) for item in items]
        for item in items:
            item.setIcon(QIcon())
        application.processEvents()
        background_image = header.grab().toImage()
        for item, icon in zip(items, icons, strict=True):
            item.setIcon(icon)
        application.processEvents()
        image = header.grab().toImage()
        ratio = image.devicePixelRatio()
        for column, field in enumerate(ICON_FIELDS, start=1):
            left = header.sectionViewportPosition(column)
            section_width = header.sectionSize(column)
            pixels = []
            solid_foreground = False
            for y in range(image.height()):
                for x in range(round(left * ratio), round((left + section_width) * ratio)):
                    if image.pixelColor(x, y) == color:
                        solid_foreground = True
                    # Include antialiased strokes, not only fully opaque icon pixels.
                    if image.pixelColor(x, y) != background_image.pixelColor(x, y):
                        pixels.append((x, y))
            assert solid_foreground, f"The {field} icon must use the header's foreground color"
            assert pixels, f"The {field} icon must be visible"
            center_x = (min(x for x, _ in pixels) + max(x for x, _ in pixels)) / 2
            center_y = (min(y for _, y in pixels) + max(y for _, y in pixels)) / 2
            expected_x = (left + section_width / 2) * ratio
            assert abs(center_x - expected_x) <= 2 * ratio, f"Off-center {field} at {width}px"
            assert abs(center_y - image.height() / 2) <= 2 * ratio, f"Off-center {field} vertically"
    table.close()
