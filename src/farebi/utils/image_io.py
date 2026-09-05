"""Safe image decoding.

The only place raw upload bytes become a numpy array. Order of operations is
deliberate and matches ``FAREBI.md`` §3.2 steps [1] and [2]:

    validate bytes (core.security, pure)
      -> verify container (PIL.verify, no pixel allocation)
      -> reject multi-frame containers (GIF/APNG/WebP-anim renamed to .jpg)
      -> cap decoded pixel count (decompression-bomb guard)
      -> transpose per EXIF orientation
      -> convert to a contiguous RGB uint8 array

The EXIF orientation transpose matters beyond cosmetics: MediaPipe face
detection is measurably worse on sideways faces, and a silently mis-oriented
image would degrade every downstream signal.

Layer: L0 (may not import anything internal).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from farebi.core.constants import RejectionCode
from farebi.core.security import UploadLimits, UploadRejected, UploadValidation, validate_upload

__all__ = [
    "DecodedImage",
    "ImageDecodeError",
    "decode_image",
    "validate_and_decode",
]

# `UploadRejected` is imported from core.security and re-exported here for
# convenience; it is defined there so that L0 stays acyclic
# (utils -> core, never the reverse).

# Guard against decompression bombs at the PIL level too. We already checked
# the declared dimensions; this catches containers that lie about their size.
Image.MAX_IMAGE_PIXELS = 178_956_970  # PIL's default; we also check explicitly

#: EXIF tag 274. Values 2-8 require a geometric correction; 1 and 0 do not.
_EXIF_ORIENTATION_TAG = 274
_TRANSPOSING_ORIENTATIONS = frozenset({2, 3, 4, 5, 6, 7, 8})


class ImageDecodeError(Exception):
    """The header looked fine but the pixels could not be decoded."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.code = RejectionCode.DECODE_FAILED
        self.detail = detail


@dataclass(frozen=True, slots=True)
class DecodedImage:
    """A decoded, normalised image plus the provenance needed to audit it."""

    array: np.ndarray  # (H, W, 3) uint8, RGB, EXIF-orientation corrected
    width: int
    height: int
    media_type: str
    sha256: str
    orientation_applied: bool
    grayscale: bool

    @property
    def shape(self) -> tuple[int, int, int]:
        height, width = self.array.shape[:2]
        return height, width, 3

    def to_bgr(self) -> np.ndarray:
        """Return a contiguous BGR view for OpenCV consumers.

        Signals that use OpenCV (blur, Laplacian, colour-space work) ask for
        BGR; the canonical in-memory format stays RGB.
        """
        bgr = self.array[:, :, ::-1]
        return np.ascontiguousarray(bgr)


def _sha256(data: bytes) -> str:
    from farebi.utils.hashing import sha256_bytes

    return sha256_bytes(data)


def _count_frames(data: bytes) -> int:
    """Number of frames in the container. ``1`` for genuinely still images."""
    with Image.open(io.BytesIO(data)) as img:
        return int(getattr(img, "n_frames", 1) or 1)


def decode_image(
    data: bytes,
    *,
    declared_media_type: str | None,
    filename: str | None = None,
    limits: UploadLimits,
) -> DecodedImage:
    """Validate and decode an upload, or raise.

    Raises:
        UploadRejected: the bytes fail a pre-decode rule (see ``RejectionCode``).
        ImageDecodeError: the container is valid but the pixels are not
            decodable (truncated scan data, corrupt tile, etc.).
    """
    validation: UploadValidation = validate_upload(
        data,
        declared_media_type=declared_media_type,
        filename=filename,
        limits=limits,
    )
    if not validation.ok:
        raise UploadRejected(validation.code, validation.detail)

    # --- multi-frame rejection -------------------------------------------
    # A GIF or APNG renamed to .jpg has already passed the magic-byte check by
    # now only if it genuinely is a JPEG; this catches APNG and multi-frame
    # TIFF/WebP that also declare an allowed type.
    if not limits.allow_multiframe:
        try:
            frames = _count_frames(data)
        except (UnidentifiedImageError, OSError) as exc:
            raise ImageDecodeError(f"could not inspect container: {exc}") from exc
        if frames > 1:
            raise UploadRejected(
                RejectionCode.MULTI_FRAME_REJECTED,
                f"container holds {frames} frames; only single-frame images are accepted",
            )

    # --- verify before decode --------------------------------------------
    # verify() parses structure without allocating the pixel buffer.
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ImageDecodeError(f"container failed verification: {exc}") from exc

    # --- decode -----------------------------------------------------------
    try:
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            if width * height > limits.max_pixels:
                raise UploadRejected(
                    RejectionCode.PIXEL_BOMB,
                    f"image decodes to {width * height} pixels; limit is {limits.max_pixels}",
                )

            was_grayscale = img.mode in {"L", "LA", "I;16", "I"}

            # Read the orientation tag *before* transposing: exif_transpose
            # strips it from the returned image, and it returns a copy even when
            # no rotation was needed — so "did we get a different object back"
            # is not a usable test.
            exif_orientation = int(img.getexif().get(_EXIF_ORIENTATION_TAG, 1))
            transposed = ImageOps.exif_transpose(img)
            orientation_applied = exif_orientation in _TRANSPOSING_ORIENTATIONS

            rgb = transposed.convert("RGB")
            array = np.asarray(rgb, dtype=np.uint8)
    except UploadRejected:
        raise
    except (OSError, ValueError, SyntaxError) as exc:
        raise ImageDecodeError(f"pixel decoding failed: {exc}") from exc
    except MemoryError as exc:  # pragma: no cover - pathological input
        raise UploadRejected(RejectionCode.PIXEL_BOMB, f"decoding exhausted memory: {exc}") from exc

    if array.ndim != 3 or array.shape[2] != 3:
        raise ImageDecodeError(f"unexpected decoded shape {array.shape}; expected (H, W, 3)")

    return DecodedImage(
        array=np.ascontiguousarray(array),
        width=int(width),
        height=int(height),
        media_type=validation.media_type or "",
        sha256=_sha256(data),
        orientation_applied=bool(orientation_applied),
        grayscale=bool(was_grayscale),
    )


def validate_and_decode(
    data: bytes,
    *,
    declared_media_type: str | None,
    filename: str | None = None,
    limits: UploadLimits,
) -> tuple[DecodedImage | None, UploadValidation | None]:
    """Non-raising variant for callers that want to branch on the code.

    Returns ``(image, None)`` on success and ``(None, validation)`` on a
    pre-decode rejection. Decode failures raise, because by then the input
    passed every security rule and the fault is in our decoder or in a file
    too exotic to describe with a rejection code.
    """
    validation = validate_upload(
        data,
        declared_media_type=declared_media_type,
        filename=filename,
        limits=limits,
    )
    if not validation.ok:
        return None, validation
    image = decode_image(
        data,
        declared_media_type=declared_media_type,
        filename=filename,
        limits=limits,
    )
    return image, None
