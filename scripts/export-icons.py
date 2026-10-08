"""Export the vector icon to PNG sizes and a PNG-backed Windows ICO."""

import os
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
ASSET_DIRECTORY = PROJECT_DIRECTORY / "src" / "rocket_lantern" / "assets"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_icon(renderer: QSvgRenderer, size: int) -> QImage:
    """Supersample each size directly from the vector, without any cropping."""
    image = QImage(size * 4, size * 4, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    return image.scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


def png_bytes(image: QImage) -> bytes:
    """Encode image data for both standalone PNGs and ICO directory entries."""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise OSError("Cannot encode the application icon")
    return bytes(buffer.data())


def windows_icon(images: dict[int, bytes]) -> bytes:
    """Build a multi-image ICONDIR; byte dimensions use zero for 256 pixels."""
    offset = 6 + 16 * len(images)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    for size, payload in images.items():
        dimension = size % 256
        directory.extend(
            struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(payload), offset)
        )
        offset += len(payload)
    return bytes(directory) + b"".join(images.values())


def save_preview(images: dict[int, QImage]) -> None:
    """Show actual pixel sizes against both light and dark desktop surfaces."""
    preview = QImage(880, 360, QImage.Format.Format_ARGB32_Premultiplied)
    preview.fill(QColor("#f3f4f6"))
    painter = QPainter(preview)
    try:
        painter.setFont(QFont("Segoe UI", 10))
        painter.fillRect(QRectF(0, 180, 880, 180), QColor("#20242b"))
        for row, color in ((0, "#20242b"), (1, "#f3f4f6")):
            painter.setPen(QColor(color))
            x = 20
            for size in (16, 20, 24, 32, 40, 48, 64, 128):
                width = max(size, 60) + 15
                painter.drawImage(
                    x + (width - size) // 2, row * 180 + (145 - size) // 2, images[size]
                )
                painter.drawText(
                    QRectF(x, row * 180 + 145, width, 25),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{size} px",
                )
                x += width
    finally:
        painter.end()
    destination = PROJECT_DIRECTORY / "assets" / "branding" / "rocket-lantern-sizes.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not preview.save(str(destination)):
        raise OSError(f"Cannot save icon preview: {destination}")


def main() -> int:
    """Regenerate committed icon exports using the project's existing Qt dependency."""
    app = QApplication(["export-icons", "-platform", "offscreen"])
    if sys.platform == "win32" and "WINDIR" in os.environ:
        # Offscreen Qt does not enumerate Windows fonts automatically.
        font_path = Path(os.environ["WINDIR"]) / "Fonts" / "segoeui.ttf"
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    renderer = QSvgRenderer(str(ASSET_DIRECTORY / "rocket-lantern.svg"))
    if not renderer.isValid():
        raise ValueError("Invalid RocketLantern SVG source")
    images: dict[int, QImage] = {}
    encoded: dict[int, bytes] = {}
    for size in (*ICON_SIZES, 512, 1024):
        image = render_icon(renderer, size)
        payload = png_bytes(image)
        (ASSET_DIRECTORY / f"rocket-lantern-{size}.png").write_bytes(payload)
        if size in ICON_SIZES:
            images[size] = image
            encoded[size] = payload
    (ASSET_DIRECTORY / "rocket-lantern.ico").write_bytes(windows_icon(encoded))
    save_preview(images)
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
