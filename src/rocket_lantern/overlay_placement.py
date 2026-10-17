"""Validated screen-relative placement, independent of monitor origin and overlay width."""

import json
import math
from dataclasses import asdict, dataclass

from PySide6.QtCore import QPoint, QRect, QSize

from rocket_lantern.summary_overlay import overlay_position

CORNERS = ("top_left", "top_right", "bottom_left", "bottom_right")


@dataclass(frozen=True)
class OverlayPlacement:
    screen: str = ""
    corner: str = "top_left"
    x_ratio: float | None = None
    y_ratio: float | None = None

    def position(self, bounds: QRect, size: QSize) -> QPoint:
        if self.x_ratio is None or self.y_ratio is None:
            return overlay_position(bounds, size, self.corner)
        x = bounds.left() + round(self.x_ratio * max(0, bounds.width() - size.width()))
        y = bounds.top() + round(self.y_ratio * max(0, bounds.height() - size.height()))
        return QPoint(x, y)

    def serialize(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True, allow_nan=False)


def placement_from_position(
    screen: str, corner: str, bounds: QRect, size: QSize, point: QPoint
) -> OverlayPlacement:
    """Store fractions of available travel, keeping the entire HUD within the screen."""
    width = max(1, bounds.width() - size.width())
    height = max(1, bounds.height() - size.height())
    x = max(0.0, min(1.0, (point.x() - bounds.left()) / width))
    y = max(0.0, min(1.0, (point.y() - bounds.top()) / height))
    return OverlayPlacement(screen, corner, x, y)


def parse_placement(value: str) -> OverlayPlacement:
    """Reject malformed saved data; callers decide whether to report and reset it."""
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("Overlay placement must be an object")
    screen = data.get("screen", "")
    corner = data.get("corner", "top_left")
    if not isinstance(screen, str) or corner not in CORNERS:
        raise ValueError("Invalid overlay screen or corner")
    x = data.get("x_ratio")
    y = data.get("y_ratio")
    if x is None and y is None:
        return OverlayPlacement(screen, corner)
    for ratio in (x, y):
        if type(ratio) not in (int, float) or not 0 <= ratio <= 1 or not math.isfinite(ratio):
            raise ValueError("Overlay ratios must be finite numbers between zero and one")
    return OverlayPlacement(screen, corner, float(x), float(y))
