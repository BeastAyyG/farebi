"""Named region-of-interest extraction from a 478-point face mesh.

Signals never index landmarks by raw number. They ask for a region by name —
``sclera_left``, ``cheek_right``, ``forehead`` — so that when the index sets are
refined (they will be, during Phase 04) exactly one file changes.

Conventions:
* "Left" and "right" mean the **subject's** left/right, which is the image
  right/left. This matches MediaPipe's own naming.
* Landmarks arrive normalised to ``[0, 1]``; every method here converts to
  pixel space using the image shape, because all signal thresholds
  (``min_eye_width_px``, ``min_face_px``) are expressed in pixels.

Layer: L1 (may import L0 only).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import cv2
import numpy as np
import numpy.typing as npt

__all__ = [
    "IRIS_LEFT",
    "IRIS_RIGHT",
    "LANDMARK_REGIONS",
    "FaceRegion",
    "LandmarkSet",
    "eye_centre_px",
    "interocular_distance_px",
]

# ---------------------------------------------------------------------------
# Index groups
#
# NOTE: these are the widely used canonical MediaPipe face-mesh groupings.
# They are approximate at the margins (particularly the cheek and forehead
# bands) and are expected to be tightened with visual inspection during
# Phase 04 signal work. That is deliberate: the whole point of centralising
# them here is that tightening them touches one file.
# ---------------------------------------------------------------------------

IRIS_LEFT: tuple[int, ...] = (468, 469, 470, 471, 472)
IRIS_RIGHT: tuple[int, ...] = (473, 474, 475, 476, 477)

EYE_LEFT: tuple[int, ...] = (
    33,
    7,
    163,
    144,
    145,
    153,
    154,
    155,
    133,
    246,
    161,
    160,
    159,
    158,
    157,
    173,
)
EYE_RIGHT: tuple[int, ...] = (
    362,
    382,
    381,
    380,
    374,
    373,
    390,
    249,
    263,
    466,
    388,
    387,
    386,
    385,
    384,
    398,
)

FOREHEAD: tuple[int, ...] = (
    10,
    108,
    109,
    151,
    337,
    338,
    9,
    8,
    107,
    66,
    105,
    63,
    70,
    336,
    296,
    334,
    293,
    300,
)
CHEEK_LEFT: tuple[int, ...] = (
    50,
    101,
    118,
    119,
    117,
    111,
    143,
    34,
    127,
    234,
    93,
    132,
    205,
)
CHEEK_RIGHT: tuple[int, ...] = (
    280,
    330,
    347,
    348,
    346,
    340,
    372,
    264,
    356,
    454,
    323,
    361,
    425,
)
NOSE_BRIDGE: tuple[int, ...] = (6, 197, 195, 5, 4, 1, 19, 94)
NOSE_TIP: tuple[int, ...] = (1, 2, 98, 327, 168, 6, 197, 195, 5, 4)
NOSE_WINGS: tuple[int, ...] = (98, 327, 64, 294, 220, 440)
CHIN: tuple[int, ...] = (
    175,
    199,
    200,
    18,
    83,
    182,
    106,
    43,
    57,
    212,
    214,
    210,
    211,
    32,
    208,
    152,
)
LIPS_OUTER: tuple[int, ...] = (
    61,
    146,
    91,
    181,
    84,
    17,
    314,
    405,
    321,
    375,
    291,
    308,
    324,
    318,
    402,
    317,
    14,
    87,
    178,
    88,
    95,
)
FACE_OVAL: tuple[int, ...] = (
    10,
    338,
    297,
    332,
    284,
    251,
    389,
    356,
    454,
    323,
    361,
    288,
    397,
    365,
    379,
    378,
    400,
    377,
    152,
    148,
    176,
    149,
    150,
    136,
    172,
    58,
    132,
    93,
    234,
    127,
    162,
    21,
    54,
    103,
    67,
    109,
)


class FaceRegion(str, Enum):
    """Regions a signal may request."""

    IRIS_LEFT = "iris_left"
    IRIS_RIGHT = "iris_right"
    EYE_LEFT = "eye_left"
    EYE_RIGHT = "eye_right"
    SCLERA_LEFT = "sclera_left"
    SCLERA_RIGHT = "sclera_right"
    FOREHEAD = "forehead"
    CHEEK_LEFT = "cheek_left"
    CHEEK_RIGHT = "cheek_right"
    NOSE_BRIDGE = "nose_bridge"
    NOSE_TIP = "nose_tip"
    NOSE_WINGS = "nose_wings"
    CHIN = "chin"
    LIPS_OUTER = "lips_outer"
    FACE_OVAL = "face_oval"


#: Region -> landmark indices. ``SCLERA_*`` has no static group: it is derived
#: at runtime as the eye region minus the iris region.
LANDMARK_REGIONS: dict[FaceRegion, tuple[int, ...]] = {
    FaceRegion.IRIS_LEFT: IRIS_LEFT,
    FaceRegion.IRIS_RIGHT: IRIS_RIGHT,
    FaceRegion.EYE_LEFT: EYE_LEFT,
    FaceRegion.EYE_RIGHT: EYE_RIGHT,
    FaceRegion.FOREHEAD: FOREHEAD,
    FaceRegion.CHEEK_LEFT: CHEEK_LEFT,
    FaceRegion.CHEEK_RIGHT: CHEEK_RIGHT,
    FaceRegion.NOSE_BRIDGE: NOSE_BRIDGE,
    FaceRegion.NOSE_TIP: NOSE_TIP,
    FaceRegion.NOSE_WINGS: NOSE_WINGS,
    FaceRegion.CHIN: CHIN,
    FaceRegion.LIPS_OUTER: LIPS_OUTER,
    FaceRegion.FACE_OVAL: FACE_OVAL,
}

_SCLERA_PARTS: dict[FaceRegion, tuple[FaceRegion, FaceRegion]] = {
    FaceRegion.SCLERA_LEFT: (FaceRegion.EYE_LEFT, FaceRegion.IRIS_LEFT),
    FaceRegion.SCLERA_RIGHT: (FaceRegion.EYE_RIGHT, FaceRegion.IRIS_RIGHT),
}


@dataclass(frozen=True, slots=True)
class LandmarkSet:
    """A face mesh bound to the image it was detected in.

    Constructed from a :class:`~farebi.capture.face_mesh.FaceDetection` plus the
    image shape; stores pixel coordinates once, so signals never repeat the
    normalised -> pixel conversion.
    """

    points_px: npt.NDArray[np.float32]  # (N, 2) pixel coordinates
    points_xyz: npt.NDArray[np.float32]  # (N, 3) normalised, including z
    image_width: int
    image_height: int

    @classmethod
    def from_detection(
        cls, landmarks: npt.NDArray[np.float32], width: int, height: int
    ) -> LandmarkSet:
        """Build from an ``(N, 3)`` normalised landmark array."""
        if landmarks.ndim != 2 or landmarks.shape[1] != 3:
            raise ValueError(f"expected (N, 3) landmarks, got shape {landmarks.shape}")
        if width <= 0 or height <= 0:
            raise ValueError(f"image dimensions must be positive, got {width}x{height}")

        points_px = landmarks[:, :2].copy()
        points_px[:, 0] *= width
        points_px[:, 1] *= height
        return cls(
            points_px=points_px.astype(np.float32, copy=False),
            points_xyz=landmarks.astype(np.float32, copy=False),
            image_width=width,
            image_height=height,
        )

    @property
    def num_points(self) -> int:
        return int(self.points_px.shape[0])

    @property
    def has_iris(self) -> bool:
        return self.num_points >= 478

    # -- indexing -----------------------------------------------------------
    def indices(self, region: FaceRegion) -> tuple[int, ...]:
        """Landmark indices for a region.

        Raises:
            ValueError: the region needs iris points the mesh does not have, or
                the mesh is smaller than the region's largest index.
        """
        if region in _SCLERA_PARTS:
            eye_region, _iris_region = _SCLERA_PARTS[region]
            return LANDMARK_REGIONS[eye_region]  # iris is removed via the mask

        group = LANDMARK_REGIONS[region]
        if max(group) >= self.num_points:
            raise ValueError(
                f"region {region.value} needs index {max(group)} but the mesh has "
                f"{self.num_points} points (iris refinement off?)"
            )
        return group

    def points(self, region: FaceRegion) -> npt.NDArray[np.float32]:
        """Pixel coordinates ``(M, 2)`` for a region."""
        return self.points_px[list(self.indices(region))]

    def bbox(self, region: FaceRegion, padding_ratio: float = 0.0) -> tuple[int, int, int, int]:
        """Clipped pixel bbox ``(x1, y1, x2, y2)`` for a region."""
        pts = self.points(region)
        if pts.size == 0:
            return 0, 0, 0, 0
        x1, y1 = pts.min(axis=0)
        x2, y2 = pts.max(axis=0)

        if padding_ratio > 0:
            pad_x = (x2 - x1) * padding_ratio
            pad_y = (y2 - y1) * padding_ratio
            x1, x2 = x1 - pad_x, x2 + pad_x
            y1, y2 = y1 - pad_y, y2 + pad_y

        return (
            int(max(0, np.floor(x1))),
            int(max(0, np.floor(y1))),
            int(min(self.image_width, np.ceil(x2))),
            int(min(self.image_height, np.ceil(y2))),
        )

    def mask(
        self, region: FaceRegion, shape: tuple[int, int] | None = None
    ) -> npt.NDArray[np.uint8]:
        """Filled convex-hull mask (``0``/``255``) for a region.

        For ``SCLERA_*`` the iris hull is subtracted from the eye hull.
        """
        height, width = shape or (self.image_height, self.image_width)
        canvas = np.zeros((height, width), dtype=np.uint8)

        # `type: ignore[call-overload]`: opencv-python's stubs reject the
        # unsigned-int canvas dtype even though `fillConvexPoly` accepts it at
        # runtime (a known stub/numpy-2 typing gap). The call is correct.
        if region in _SCLERA_PARTS:
            eye_region, _iris_region = _SCLERA_PARTS[region]
            eye_hull = cv2.convexHull(self.points(eye_region).astype(np.float32))
            iris_hull = cv2.convexHull(self.points(_iris_region).astype(np.float32))
            cv2.fillConvexPoly(canvas, np.int32(eye_hull), 255)  # type: ignore[call-overload]
            cv2.fillConvexPoly(canvas, np.int32(iris_hull), 0)  # type: ignore[call-overload]
            return canvas

        hull = cv2.convexHull(self.points(region).astype(np.float32))
        cv2.fillConvexPoly(canvas, np.int32(hull), 255)  # type: ignore[call-overload]
        return canvas

    def crop(
        self,
        image: npt.NDArray[np.uint8],
        region: FaceRegion,
        padding_ratio: float = 0.15,
    ) -> npt.NDArray[np.uint8]:
        """Crop a region out of ``image``, clipped to the frame.

        Returns an empty ``(0, 0, 3)`` array when the region falls entirely
        outside the image — callers must check, because a zero-area crop is a
        legitimate outcome on a tightly framed face, not an error.
        """
        x1, y1, x2, y2 = self.bbox(region, padding_ratio=padding_ratio)
        if x2 <= x1 or y2 <= y1:
            return np.empty((0, 0, 3), dtype=np.uint8)
        return np.ascontiguousarray(image[y1:y2, x1:x2])

    def region_size_px(self, region: FaceRegion) -> tuple[int, int]:
        """Width and height in pixels of a region's bounding box."""
        x1, y1, x2, y2 = self.bbox(region)
        return max(0, x2 - x1), max(0, y2 - y1)


def eye_centre_px(
    landmarks: LandmarkSet,
    region: FaceRegion,
) -> tuple[float, float]:
    """Pixel centre of an iris region."""
    pts = landmarks.points(region)
    if pts.size == 0:
        raise ValueError(f"region {region.value} produced no points")
    return float(pts[:, 0].mean()), float(pts[:, 1].mean())


def interocular_distance_px(landmarks: LandmarkSet) -> float:
    """Distance in pixels between the two iris centres.

    The standard proxy for face scale. Requires iris refinement; raises clearly
    when it is absent so the caller can emit ``LANDMARKS_UNAVAILABLE`` rather
    than silently reporting a bogus number.
    """
    if not landmarks.has_iris:
        raise ValueError(
            "interocular distance requires iris landmarks (478-point mesh); "
            f"mesh has {landmarks.num_points} points"
        )
    lx, ly = eye_centre_px(landmarks, FaceRegion.IRIS_LEFT)
    rx, ry = eye_centre_px(landmarks, FaceRegion.IRIS_RIGHT)
    return float(np.hypot(lx - rx, ly - ry))
