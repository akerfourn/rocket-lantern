"""Validated screen-relative placement, independent of monitor origin and overlay width."""

import json
import math
from dataclasses import asdict, dataclass

from PySide6.QtCore import QPoint, QRect, QSize

from rocket_lantern.summary_overlay import overlay_position

CORNERS = ("top_left", "top_right", "bottom_left", "bottom_right")
HORIZONTAL_ANCHORS = ("left", "center", "right")


def horizontal_anchor_offset(width: int, anchor: str) -> int:
    """Return the chosen reference point measured from the overlay's left edge."""
    if anchor == "right":
        return width
    if anchor == "center":
        return width // 2
    return 0


@dataclass(frozen=True)
class OverlayPlacement:
    screen: str = ""
    corner: str = "top_left"
    x_ratio: float | None = None
    y_ratio: float | None = None
    # None retains legacy travel-relative x_ratio; explicit anchors use screen width.
    horizontal_anchor: str | None = None

    def editor_anchor(self) -> str:
        """Suggest an anchor for legacy placements without moving their preview."""
        if self.horizontal_anchor is not None:
            return self.horizontal_anchor
        if self.x_ratio is not None:
            if self.x_ratio < 1 / 3:
                return "left"
            if self.x_ratio > 2 / 3:
                return "right"
            return "center"
        if self.corner.endswith("right"):
            return "right"
        return "left"

    def position(self, bounds: QRect, size: QSize) -> QPoint:
        if self.x_ratio is None or self.y_ratio is None:
            return overlay_position(bounds, size, self.corner)
        x = bounds.left() + round(self.x_ratio * max(0, bounds.width() - size.width()))
        if self.horizontal_anchor is not None:
            offset = horizontal_anchor_offset(size.width(), self.horizontal_anchor)
            x = bounds.left() + round(self.x_ratio * bounds.width()) - offset
            x = max(bounds.left(), min(x, bounds.left() + max(0, bounds.width() - size.width())))
        y = bounds.top() + round(self.y_ratio * max(0, bounds.height() - size.height()))
        return QPoint(x, y)

    def serialize(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True, allow_nan=False)


def placement_from_position(
    screen: str,
    corner: str,
    bounds: QRect,
    size: QSize,
    point: QPoint,
    horizontal_anchor: str | None = None,
) -> OverlayPlacement:
    """Store a screen-relative horizontal anchor and travel-relative vertical position.

    Without an anchor, retain the legacy travel-relative horizontal representation.
    """
    if horizontal_anchor is not None and horizontal_anchor not in HORIZONTAL_ANCHORS:
        raise ValueError("Invalid horizontal overlay anchor")
    width = max(1, bounds.width() - size.width())
    height = max(1, bounds.height() - size.height())
    x = max(0.0, min(1.0, (point.x() - bounds.left()) / width))
    if horizontal_anchor is not None:
        left = max(0, min(point.x() - bounds.left(), max(0, bounds.width() - size.width())))
        offset = horizontal_anchor_offset(size.width(), horizontal_anchor)
        x = max(0.0, min(1.0, (left + offset) / max(1, bounds.width())))
    y = max(0.0, min(1.0, (point.y() - bounds.top()) / height))
    return OverlayPlacement(screen, corner, x, y, horizontal_anchor)


def parse_placement(value: str) -> OverlayPlacement:
    """Reject malformed saved data; callers decide whether to report and reset it."""
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("Overlay placement must be an object")
    screen = data.get("screen", "")
    corner = data.get("corner", "top_left")
    if not isinstance(screen, str) or corner not in CORNERS:
        raise ValueError("Invalid overlay screen or corner")
    anchor = data.get("horizontal_anchor")
    if anchor is not None and anchor not in HORIZONTAL_ANCHORS:
        raise ValueError("Invalid horizontal overlay anchor")
    x = data.get("x_ratio")
    y = data.get("y_ratio")
    if x is None and y is None:
        return OverlayPlacement(screen, corner, horizontal_anchor=anchor)
    for ratio in (x, y):
        if type(ratio) not in (int, float) or not 0 <= ratio <= 1 or not math.isfinite(ratio):
            raise ValueError("Overlay ratios must be finite numbers between zero and one")
    return OverlayPlacement(screen, corner, float(x), float(y), anchor)
