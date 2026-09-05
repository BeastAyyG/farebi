"""Pure upload-validation rules.

Everything here is a pure function over bytes. No I/O, no decode, no config
lookups — limits are passed in by the caller. That makes the security boundary
trivially testable and impossible to bypass by reordering a pipeline.

Two independent checks are always applied:

1. **Declared** media type (from the client) must be on the allowlist.
2. **Actual** media type (from the file's magic bytes) must match the declared
   one. Trusting the client's ``Content-Type`` is the single most common upload
   vulnerability; trusting the filename is the second.

Dimensions are parsed straight out of the container header (JPEG SOF / PNG
IHDR) so an oversized image is rejected *before* it is decoded — a
decompression bomb must never reach PIL.

Layer: L0 (may not import anything internal).
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

from farebi.core.constants import (
    ALLOWED_MEDIA_TYPES,
    MAGIC_SIGNATURES,
    RejectionCode,
)

__all__ = [
    "UploadLimits",
    "UploadRejected",
    "UploadValidation",
    "is_safe_filename",
    "random_filename",
    "sniff_media_type",
    "validate_upload",
]

# Control characters, path separators, and NUL: a filename is untrusted input
# even when we never use it as a path, because it ends up in logs and in the UI.
_UNSAFE_FILENAME = re.compile(r"[\x00-\x1f/\\]")


class UploadRejected(Exception):
    """An upload was refused. Carries the machine-readable rejection code.

    Defined here rather than in ``utils.image_io`` so that ``core`` never has
    to import from ``utils``; the dependency runs one way only.
    """

    def __init__(self, code: RejectionCode, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class UploadLimits:
    """Bounds applied before decoding. Typically built from ``Settings.upload``."""

    max_bytes: int
    max_pixels: int
    max_edge_px: int
    allowed_media_types: frozenset[str]
    allow_multiframe: bool = False


@dataclass(frozen=True, slots=True)
class UploadValidation:
    """Outcome of :func:`validate_upload`.

    ``ok`` is the only field callers should branch on; ``code`` is for metrics
    and for the reviewer-facing message.
    """

    ok: bool
    code: RejectionCode
    detail: str
    media_type: str | None = None
    width: int | None = None
    height: int | None = None

    def raise_for_status(self) -> None:
        """Raise :class:`UploadRejected` when the upload was refused."""
        if not self.ok:
            raise UploadRejected(self.code, self.detail)


def sniff_media_type(data: bytes) -> str | None:
    """Identify a file by its leading bytes. Returns ``None`` if unrecognised."""
    for signature, media_type in MAGIC_SIGNATURES.items():
        if data.startswith(signature):
            return media_type
    return None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """Parse width/height from JPEG SOF markers without decoding pixels.

    Walks the marker chain skipping non-SOF segments. Returns ``None`` when the
    header is truncated or malformed; the caller treats that as a rejection.
    """
    # SOF markers: C0-C3, C5-C7, C9-CB, CD-CF (C4=DHT, C8=JPG, CC=DAC).
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    offset = 2  # skip SOI (FFD8)
    length = len(data)
    while offset + 9 < length:
        if data[offset] != 0xFF:
            return None
        marker = data[offset + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # standalone markers
            offset += 2
            continue
        if marker in sof_markers:
            height = int.from_bytes(data[offset + 5 : offset + 7], "big")
            width = int.from_bytes(data[offset + 7 : offset + 9], "big")
            return (width, height) if width > 0 and height > 0 else None
        if marker == 0xDA:  # start of scan: no SOF found before image data
            return None
        segment_length = int.from_bytes(data[offset + 2 : offset + 4], "big")
        if segment_length < 2:
            return None
        offset += 2 + segment_length
    return None


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    """Parse width/height from the PNG IHDR chunk."""
    # 8-byte signature, 4-byte length, 4-byte type, then 4-byte width + height.
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return (width, height) if width > 0 and height > 0 else None


def _header_dimensions(data: bytes, media_type: str) -> tuple[int, int] | None:
    return _jpeg_dimensions(data) if media_type == "image/jpeg" else _png_dimensions(data)


def is_safe_filename(filename: str | None) -> bool:
    """Reject filenames containing control characters, NUL, or path separators."""
    if not filename:
        return True  # no filename supplied is fine; we generate our own
    return (
        len(filename) <= 255
        and _UNSAFE_FILENAME.search(filename) is None
        and filename not in {".", ".."}
        and not filename.startswith("~")
    )


def random_filename(extension: str = ".bin") -> str:
    """Generate the name we will actually use on disk.

    The uploaded filename is never used as a storage path.
    """
    if not extension.startswith("."):
        extension = "." + extension
    return f"{secrets.token_hex(16)}{extension}"


def validate_upload(
    data: bytes,
    *,
    declared_media_type: str | None,
    filename: str | None = None,
    limits: UploadLimits,
) -> UploadValidation:
    """Validate an upload. Pure: no I/O, no decode, no exceptions.

    Args:
        data: Raw upload bytes.
        declared_media_type: Client-supplied ``Content-Type``. Untrusted.
        filename: Client-supplied filename. Untrusted; validated, never used
            as a path.
        limits: Bounds from configuration.

    Returns:
        An :class:`UploadValidation`. Never raises for bad input.
    """
    if not data:
        return UploadValidation(False, RejectionCode.EMPTY_UPLOAD, "upload contained no bytes")

    if len(data) > limits.max_bytes:
        return UploadValidation(
            False,
            RejectionCode.FILE_TOO_LARGE,
            f"upload is {len(data)} bytes; limit is {limits.max_bytes}",
        )

    if not is_safe_filename(filename):
        return UploadValidation(
            False,
            RejectionCode.UNSAFE_FILENAME,
            "filename contains control characters or path separators",
        )

    # 1. Declared type must be allowed.
    if declared_media_type not in limits.allowed_media_types:
        return UploadValidation(
            False,
            RejectionCode.MEDIA_TYPE_NOT_ALLOWED,
            f"declared media type {declared_media_type!r} is not allowed; "
            f"accepted: {sorted(limits.allowed_media_types)}",
        )

    # 2. Actual type (magic bytes) must match the declared type.
    actual = sniff_media_type(data)
    if actual is None:
        return UploadValidation(
            False,
            RejectionCode.MAGIC_BYTES_MISMATCH,
            "file content does not match any accepted image signature "
            "(a renamed non-image file is the usual cause)",
        )
    if actual != declared_media_type:
        return UploadValidation(
            False,
            RejectionCode.MAGIC_BYTES_MISMATCH,
            f"declared {declared_media_type!r} but content is {actual!r}",
            media_type=actual,
        )

    # 3. Dimensions from the header, before any decode.
    dimensions = _header_dimensions(data, actual)
    if dimensions is None:
        return UploadValidation(
            False,
            RejectionCode.HEADER_TRUNCATED,
            "image header is truncated or malformed",
            media_type=actual,
        )
    width, height = dimensions

    if width > limits.max_edge_px or height > limits.max_edge_px:
        return UploadValidation(
            False,
            RejectionCode.DIMENSIONS_TOO_LARGE,
            f"image is {width}x{height}; longest edge must be <= {limits.max_edge_px}px",
            media_type=actual,
            width=width,
            height=height,
        )

    if width * height > limits.max_pixels:
        return UploadValidation(
            False,
            RejectionCode.PIXEL_BOMB,
            f"image would decode to {width * height} pixels; limit is {limits.max_pixels}",
            media_type=actual,
            width=width,
            height=height,
        )

    return UploadValidation(
        True,
        RejectionCode.OK,
        "accepted",
        media_type=actual,
        width=width,
        height=height,
    )


#: Default limits used when no configuration is supplied (e.g. in a REPL).
DEFAULT_LIMITS = UploadLimits(
    max_bytes=10 * 1024 * 1024,
    max_pixels=40_000_000,
    max_edge_px=4096,
    allowed_media_types=ALLOWED_MEDIA_TYPES,
    allow_multiframe=False,
)
