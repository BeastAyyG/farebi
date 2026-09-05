"""MediaPipe face-landmark wrapper, with two interchangeable backends.

MediaPipe is used **instead of dlib** because two downstream signals need iris
landmarks: ``corneal.py`` (binocular reflection consistency, Tier-1) and
``scleral.py`` (vessel topology, Tier-3). dlib's 68-point model has no iris
points at all. This decision is made once, here, so it does not get relitigated.

Landmark counts:
* 468 points in the base mesh.
* 478 with iris refinement — indices 468-472 are the left iris, 473-477 the
  right iris. Several signals hard-depend on those ten.

Backends
--------
MediaPipe has shipped two APIs, and which one exists depends entirely on the
installed version:

* ``solutions``  — the legacy ``mp.solutions.face_mesh.FaceMesh`` graph. Present
  in MediaPipe <= ~0.10.2x, **removed** in later releases.
* ``tasks``      — ``mediapipe.tasks.python.vision.FaceLandmarker``. Requires a
  downloaded ``.task`` model asset. This is the only API in recent releases.

Both are supported here, selected by ``capture.face_mesh.backend`` (default
``auto``: solutions if importable, otherwise tasks). Neither is a toy: the
caller gets identical ``FaceDetection`` objects either way.

Degradation
-----------
The dependency is optional and the model asset may be absent. When MediaPipe
is missing, disabled, or has no model to load, :meth:`FaceMeshDetector.detect`
returns ``status=DISABLED`` / ``UNAVAILABLE`` / ``MODEL_MISSING`` and an empty
detection list rather than raising. The caller emits ``LANDMARKS_UNAVAILABLE``
and the pipeline still runs — CI depends on this.

Layer: L1 (may import L0 only).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt

from farebi.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

__all__ = [
    "BASE_LANDMARKS",
    "REFINED_LANDMARKS",
    "FaceDetection",
    "FaceMeshBackendName",
    "FaceMeshDetector",
    "FaceMeshError",
    "FaceMeshResult",
    "FaceMeshStatus",
]

_log = get_logger(__name__)

#: Base mesh size, and the size with iris refinement enabled.
BASE_LANDMARKS = 468
REFINED_LANDMARKS = 478


class FaceMeshStatus(str, Enum):
    """Why a detection call returned what it returned."""

    OK = "ok"  # ran successfully; detections may still be empty
    NO_FACE = "no_face"  # ran, found nothing usable
    DISABLED = "disabled"  # turned off by configuration
    UNAVAILABLE = "unavailable"  # MediaPipe not installed, or no usable backend
    MODEL_MISSING = "model_missing"  # tasks backend selected, .task asset absent
    ERROR = "error"  # the backend raised; see ``detail``


class FaceMeshBackendName(str, Enum):
    """Which MediaPipe API to use."""

    AUTO = "auto"
    SOLUTIONS = "solutions"
    TASKS = "tasks"


class FaceMeshError(RuntimeError):
    """Unrecoverable face-mesh failure. Raised only when explicitly asked for."""

    def __init__(self, detail: str, *, status: FaceMeshStatus = FaceMeshStatus.ERROR) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


class ModelAssetMissing(FileNotFoundError):
    """The tasks backend was selected but the ``.task`` model file is absent."""


@dataclass(frozen=True, slots=True)
class FaceDetection:
    """One detected face.

    ``landmarks`` are normalised to ``[0, 1]`` against the image width/height,
    in MediaPipe's own order. Pixel-space conversion happens in
    :mod:`farebi.capture.landmarks`, which knows the image shape.
    """

    landmarks: npt.NDArray[np.float32]  # (478, 3) — x, y, z
    score: float
    image_width: int
    image_height: int

    @property
    def num_landmarks(self) -> int:
        return int(self.landmarks.shape[0])

    @property
    def has_iris(self) -> bool:
        """True when iris refinement produced the extra 10 points."""
        return self.num_landmarks >= REFINED_LANDMARKS

    def bbox(self, padding_ratio: float = 0.0) -> tuple[int, int, int, int]:
        """Axis-aligned pixel bounding box ``(x1, y1, x2, y2)``, clipped to frame."""
        return _bbox_from_points(
            self.landmarks[:, :2],
            self.image_width,
            self.image_height,
            padding_ratio=padding_ratio,
        )


@dataclass(frozen=True, slots=True)
class FaceMeshResult:
    """Outcome of a detection call. Never raises for expected conditions."""

    detections: tuple[FaceDetection, ...]
    status: FaceMeshStatus
    detail: str = ""
    backend: str = ""

    @property
    def ok(self) -> bool:
        return self.status is FaceMeshStatus.OK and bool(self.detections)


def _bbox_from_points(
    points: npt.NDArray[np.float32],
    width: int,
    height: int,
    *,
    padding_ratio: float = 0.0,
) -> tuple[int, int, int, int]:
    """Convert normalised points to a clipped, optionally padded pixel bbox."""
    if points.size == 0:
        return 0, 0, 0, 0

    xs = points[:, 0] * width
    ys = points[:, 1] * height
    x1, x2 = float(xs.min()), float(xs.max())
    y1, y2 = float(ys.min()), float(ys.max())

    if padding_ratio > 0:
        pad_x = (x2 - x1) * padding_ratio
        pad_y = (y2 - y1) * padding_ratio
        x1, x2 = x1 - pad_x, x2 + pad_x
        y1, y2 = y1 - pad_y, y2 + pad_y

    return (
        int(max(0, np.floor(x1))),
        int(max(0, np.floor(y1))),
        int(min(width, np.ceil(x2))),
        int(min(height, np.ceil(y2))),
    )


def _points_from_landmarks(raw: Sequence[Any], width: int, height: int) -> npt.NDArray[np.float32]:
    """Convert a MediaPipe landmark sequence into an ``(N, 3)`` float32 array."""
    points = np.asarray([(lm.x, lm.y, lm.z) for lm in raw], dtype=np.float32)
    if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] == 0:
        raise ValueError(f"unusable landmark array with shape {points.shape}")
    return points


class _Backend:
    """Minimal backend interface. Both implementations are private."""

    name: str = ""

    def detect(self, image_rgb: npt.NDArray[np.uint8]) -> list[FaceDetection]:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover
        raise NotImplementedError


class _SolutionsBackend(_Backend):
    """Legacy ``mp.solutions.face_mesh.FaceMesh`` graph."""

    name = "solutions"

    def __init__(
        self,
        *,
        max_num_faces: int,
        min_detection_confidence: float,
        refine_landmarks: bool,
    ) -> None:
        import mediapipe as mp

        solutions = getattr(mp, "solutions", None)
        face_mesh = getattr(solutions, "face_mesh", None) if solutions is not None else None
        if face_mesh is None:
            raise ImportError("mp.solutions.face_mesh is not available in this MediaPipe build")

        self._mesh = face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=max_num_faces,
            refine_landmarks=refine_landmarks,
            min_detection_confidence=min_detection_confidence,
        )

    def detect(self, image_rgb: npt.NDArray[np.uint8]) -> list[FaceDetection]:
        height, width = image_rgb.shape[:2]
        output = self._mesh.process(np.ascontiguousarray(image_rgb))
        raw_faces: Sequence[Any] = getattr(output, "multi_face_landmarks", None) or ()
        return [
            FaceDetection(
                landmarks=_points_from_landmarks(face.landmark, width, height),
                score=1.0,  # the Solutions API exposes no per-face confidence
                image_width=width,
                image_height=height,
            )
            for face in raw_faces
        ]

    def close(self) -> None:
        close = getattr(self._mesh, "close", None)
        if callable(close):
            close()


class _TasksBackend(_Backend):
    """``mediapipe.tasks.python.vision.FaceLandmarker`` (MediaPipe >= 0.10)."""

    name = "tasks"

    def __init__(
        self,
        *,
        model_path: str,
        max_num_faces: int,
        min_detection_confidence: float,
    ) -> None:
        from pathlib import Path

        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            FaceLandmarker,
            FaceLandmarkerOptions,
            VisionRunningMode,
        )

        path = Path(model_path)
        if not path.is_file():
            raise ModelAssetMissing(
                f"face landmarker model not found at {path}. "
                "Run `python scripts/fetch_face_landmarker.py` to download it, "
                "or set FAREBI_CAPTURE__FACE_MESH__BACKEND=solutions with an "
                "older MediaPipe, or set ENABLED=false for degraded mode."
            )

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(path)),
            running_mode=VisionRunningMode.IMAGE,
            num_faces=max_num_faces,
            min_face_detection_confidence=min_detection_confidence,
            min_face_presence_confidence=min_detection_confidence,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)

    def detect(self, image_rgb: npt.NDArray[np.uint8]) -> list[FaceDetection]:
        import mediapipe as mp

        height, width = image_rgb.shape[:2]
        frame = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(image_rgb))
        output = self._landmarker.detect(frame)

        detections: list[FaceDetection] = []
        for face in getattr(output, "face_landmarks", None) or ():
            detections.append(
                FaceDetection(
                    landmarks=_points_from_landmarks(face, width, height),
                    score=1.0,
                    image_width=width,
                    image_height=height,
                )
            )
        return detections

    def close(self) -> None:
        close = getattr(self._landmarker, "close", None)
        if callable(close):
            close()


class FaceMeshDetector:
    """Dependency-isolated face landmarker with graceful degradation.

    The underlying MediaPipe object holds native resources; use the context
    manager or call :meth:`close` explicitly in long-lived workers.

    Example:
        >>> with FaceMeshDetector() as detector:            # doctest: +SKIP
        ...     result = detector.detect(rgb_image)
        ...     if result.status is FaceMeshStatus.NO_FACE:
        ...         ...
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        max_num_faces: int = 3,
        min_detection_confidence: float = 0.5,
        refine_landmarks: bool = True,
        backend: str | FaceMeshBackendName = FaceMeshBackendName.AUTO,
        model_path: str = "artifacts/models/face_landmarker.task",
    ) -> None:
        if not 0.0 <= min_detection_confidence <= 1.0:
            raise ValueError(
                f"min_detection_confidence must be in [0, 1], got {min_detection_confidence}"
            )
        if max_num_faces < 1:
            raise ValueError(f"max_num_faces must be >= 1, got {max_num_faces}")

        self._enabled = enabled
        self._max_num_faces = max_num_faces
        self._min_detection_confidence = min_detection_confidence
        self._refine_landmarks = refine_landmarks
        self._backend_name = FaceMeshBackendName(backend)
        self._model_path = model_path
        self._backend: _Backend | None = None
        self._initialised = False
        self._init_error: str | None = None

    # -- availability -------------------------------------------------------
    @staticmethod
    def is_installed() -> bool:
        """Whether the ``mediapipe`` package can be imported."""
        try:
            import mediapipe  # noqa: F401
        except ImportError:
            return False
        return True

    @staticmethod
    def available_backends() -> list[str]:
        """Which MediaPipe APIs this installation exposes, in preference order."""
        available: list[str] = []
        try:
            import mediapipe as mp

            if getattr(getattr(mp, "solutions", None), "face_mesh", None) is not None:
                available.append(_SolutionsBackend.name)
        except ImportError:
            pass
        try:
            from mediapipe.tasks.python.vision import FaceLandmarker  # noqa: F401

            available.append(_TasksBackend.name)
        except ImportError:
            pass
        return available

    @property
    def backend_name(self) -> str:
        """Name of the backend actually in use, or ``""`` when none is."""
        return self._backend.name if self._backend is not None else ""

    @property
    def available(self) -> bool:
        """Whether this detector can actually run right now."""
        return self.status is FaceMeshStatus.OK

    @property
    def status(self) -> FaceMeshStatus:
        """Resolve the current status, constructing the backend if needed."""
        if not self._enabled:
            return FaceMeshStatus.DISABLED
        if not self.is_installed():
            return FaceMeshStatus.UNAVAILABLE

        if self._backend is None and not self._initialised:
            try:
                self._ensure_initialised()
            except ModelAssetMissing as exc:
                self._init_error = str(exc)
                return FaceMeshStatus.MODEL_MISSING
            except Exception as exc:
                self._init_error = f"{type(exc).__name__}: {exc}"
                return FaceMeshStatus.UNAVAILABLE

        return FaceMeshStatus.OK if self._backend is not None else FaceMeshStatus.UNAVAILABLE

    # -- lifecycle ----------------------------------------------------------
    def _ensure_initialised(self) -> None:
        """Construct the first usable backend. Raises when none is available."""
        if self._initialised:
            if self._backend is None and self._init_error:
                raise FaceMeshError(self._init_error, status=FaceMeshStatus.UNAVAILABLE)
            return
        if self._backend is not None:
            return

        errors: list[str] = []
        order: list[FaceMeshBackendName] = {
            FaceMeshBackendName.SOLUTIONS: [FaceMeshBackendName.SOLUTIONS],
            FaceMeshBackendName.TASKS: [FaceMeshBackendName.TASKS],
            FaceMeshBackendName.AUTO: [FaceMeshBackendName.SOLUTIONS, FaceMeshBackendName.TASKS],
        }[self._backend_name]

        for candidate in order:
            try:
                if candidate is FaceMeshBackendName.SOLUTIONS:
                    self._backend = _SolutionsBackend(
                        max_num_faces=self._max_num_faces,
                        min_detection_confidence=self._min_detection_confidence,
                        refine_landmarks=self._refine_landmarks,
                    )
                else:
                    self._backend = _TasksBackend(
                        model_path=self._model_path,
                        max_num_faces=self._max_num_faces,
                        min_detection_confidence=self._min_detection_confidence,
                    )
            except ModelAssetMissing:
                # Propagate: this is actionable, unlike a missing API.
                raise
            except Exception as exc:
                errors.append(f"{candidate.value}: {type(exc).__name__}: {exc}")
                continue
            self._initialised = True
            return

        self._initialised = True
        self._init_error = "; ".join(errors) or "no MediaPipe backend available"
        raise FaceMeshError(self._init_error, status=FaceMeshStatus.UNAVAILABLE)

    def close(self) -> None:
        """Release native resources. Idempotent."""
        if self._backend is not None:
            try:
                self._backend.close()
            except Exception as exc:
                _log.warning("face_mesh_close_failed", error=type(exc).__name__)
            self._backend = None
        self._initialised = False
        self._init_error = None

    def __enter__(self) -> FaceMeshDetector:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- detection ----------------------------------------------------------
    def detect(self, image_rgb: npt.NDArray[np.uint8]) -> FaceMeshResult:
        """Run face landmarking on an RGB uint8 image.

        Args:
            image_rgb: ``(H, W, 3)`` uint8 array in RGB order.

        Returns:
            A :class:`FaceMeshResult`. Does not raise for expected conditions
            (disabled, not installed, missing model, no face); backend failures
            surface as ``status=ERROR`` with the exception text in ``detail``.

        Raises:
            ValueError: the input is not an ``(H, W, 3)`` uint8 array. Caller
                error, not an image problem.
        """
        if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
            raise ValueError(f"expected an (H, W, 3) RGB image, got shape {image_rgb.shape}")
        if image_rgb.dtype != np.uint8:
            raise ValueError(f"expected uint8 pixels, got {image_rgb.dtype}")

        if not self._enabled:
            return FaceMeshResult(
                (), FaceMeshStatus.DISABLED, "face mesh disabled by configuration"
            )
        if not self.is_installed():
            return FaceMeshResult(
                (), FaceMeshStatus.UNAVAILABLE, "mediapipe is not installed; degraded mode"
            )

        try:
            self._ensure_initialised()
        except ModelAssetMissing as exc:
            return FaceMeshResult((), FaceMeshStatus.MODEL_MISSING, str(exc))
        except FaceMeshError as exc:
            return FaceMeshResult((), exc.status, exc.detail)
        except Exception as exc:
            return FaceMeshResult((), FaceMeshStatus.UNAVAILABLE, f"{type(exc).__name__}: {exc}")

        assert self._backend is not None  # guaranteed by _ensure_initialised

        try:
            detections = self._backend.detect(image_rgb)
        except Exception as exc:
            _log.warning("face_mesh_failed", error=type(exc).__name__, backend=self._backend.name)
            return FaceMeshResult((), FaceMeshStatus.ERROR, str(exc), backend=self._backend.name)

        if not detections:
            return FaceMeshResult(
                (), FaceMeshStatus.NO_FACE, "no face detected", backend=self._backend.name
            )

        return FaceMeshResult(
            tuple(detections),
            FaceMeshStatus.OK,
            f"{len(detections)} face(s) detected",
            backend=self._backend.name,
        )
