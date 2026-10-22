"""Pure orthographic 3D projection and a schematic standard Soccar arena."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from rocket_lantern.event_map_data import Position

SIDE_WALL = 4096.0
BACK_WALL = 5120.0
CEILING = 2044.0
GOAL_HALF_WIDTH = 892.755
GOAL_HEIGHT = 642.775
GOAL_DEPTH = 880.0
CORNER = 1152.0
WORLD_SCALE = 6000.0

FLOOR: tuple[Position, ...] = (
    (-SIDE_WALL, -BACK_WALL + CORNER, 0),
    (-SIDE_WALL + CORNER, -BACK_WALL, 0),
    (SIDE_WALL - CORNER, -BACK_WALL, 0),
    (SIDE_WALL, -BACK_WALL + CORNER, 0),
    (SIDE_WALL, BACK_WALL - CORNER, 0),
    (SIDE_WALL - CORNER, BACK_WALL, 0),
    (-SIDE_WALL + CORNER, BACK_WALL, 0),
    (-SIDE_WALL, BACK_WALL - CORNER, 0),
)


def goal_vertices(team: int) -> tuple[Position, ...]:
    """Return the opening and back of one goal in the unchanged world frame."""
    direction = -1 if team == 0 else 1
    front = direction * BACK_WALL
    back = direction * (BACK_WALL + GOAL_DEPTH)
    return tuple(
        (x, y, z)
        for y in (front, back)
        for x, z in (
            (-GOAL_HALF_WIDTH, 0),
            (GOAL_HALF_WIDTH, 0),
            (GOAL_HALF_WIDTH, GOAL_HEIGHT),
            (-GOAL_HALF_WIDTH, GOAL_HEIGHT),
        )
    )


def arena_bounds() -> tuple[Position, ...]:
    return FLOOR + tuple((x, y, CEILING) for x, y, _ in FLOOR) + goal_vertices(0) + goal_vertices(1)


@dataclass
class MapCamera:
    """A bounded orbit camera, with a top view that deliberately removes height."""

    yaw: float = -35.0
    elevation: float = 38.0
    zoom: float = 1.0
    target: Position | None = None

    def rotate(self, horizontal: float, vertical: float) -> None:
        self.yaw = (self.yaw + horizontal) % 360
        self.elevation = max(12.0, min(90.0, self.elevation + vertical))

    def zoom_by(self, factor: float) -> None:
        self.zoom = max(0.5, min(6.0, self.zoom * factor))

    def project(self, position: Position) -> tuple[float, float, float]:
        x, y, z = (value / WORLD_SCALE for value in position)
        yaw = math.radians(self.yaw)
        elevation = math.radians(self.elevation)
        horizontal = x * math.cos(yaw) - y * math.sin(yaw)
        depth = x * math.sin(yaw) + y * math.cos(yaw)
        vertical = depth * math.sin(elevation) - z * math.cos(elevation)
        distance = depth * math.cos(elevation) + z * math.sin(elevation)
        return horizontal, vertical, distance

    def unproject(self, horizontal: float, vertical: float, depth: float) -> Position:
        """Convert camera-space coordinates back to the unchanged world frame."""
        yaw = math.radians(self.yaw)
        elevation = math.radians(self.elevation)
        along_ground = vertical * math.sin(elevation) + depth * math.cos(elevation)
        x = horizontal * math.cos(yaw) + along_ground * math.sin(yaw)
        y = -horizontal * math.sin(yaw) + along_ground * math.cos(yaw)
        z = -vertical * math.cos(elevation) + depth * math.sin(elevation)
        return x * WORLD_SCALE, y * WORLD_SCALE, z * WORLD_SCALE


@dataclass(frozen=True)
class MapProjection:
    """Fit the full scene by default, or honor a user-selected orbit target."""

    camera: MapCamera
    scale: float
    center_x: float
    center_y: float
    screen_x: float
    screen_y: float

    @classmethod
    def fit(
        cls, camera: MapCamera, positions: Sequence[Position], width: int, height: int
    ) -> "MapProjection":
        projected = [camera.project(point) for point in (*arena_bounds(), *positions)]
        left = min(point[0] for point in projected)
        right = max(point[0] for point in projected)
        top = min(point[1] for point in projected)
        bottom = max(point[1] for point in projected)
        scale = min(
            max(1, width - 80) / max(0.01, right - left),
            max(1, height - 72) / max(0.01, bottom - top),
        )
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        if camera.target is not None:
            center_x, center_y, _ = camera.project(camera.target)
        return cls(
            camera,
            scale * camera.zoom,
            center_x,
            center_y,
            width / 2,
            height / 2,
        )

    def panned_target(self, horizontal_pixels: float, vertical_pixels: float) -> Position:
        """Move the scene with the pointer while retaining a real world-space orbit target."""
        target = self.camera.target
        if target is None:
            target = (0, 0, CEILING / 2)
        depth = self.camera.project(target)[2]
        return self.camera.unproject(
            self.center_x - horizontal_pixels / self.scale,
            self.center_y - vertical_pixels / self.scale,
            depth,
        )

    def project(self, position: Position) -> tuple[float, float, float]:
        x, y, depth = self.camera.project(position)
        return (
            self.screen_x + (x - self.center_x) * self.scale,
            self.screen_y + (y - self.center_y) * self.scale,
            depth,
        )
