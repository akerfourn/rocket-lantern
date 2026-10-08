"""Application identity and packaged icons, independent of data storage names."""

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

APP_NAME = "RocketLantern"
LEGACY_DATA_NAME = "RLWinLoss"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
ASSET_DIRECTORY = Path(__file__).parent / "assets"


def application_icon() -> QIcon:
    """Load explicit raster sizes without relying on platform ICO plugins."""
    icon = QIcon()
    for size in ICON_SIZES:
        path = ASSET_DIRECTORY / f"rocket-lantern-{size}.png"
        if not path.is_file():
            raise FileNotFoundError(f"Missing application icon: {path}")
        icon.addFile(str(path), QSize(size, size))
    return icon
