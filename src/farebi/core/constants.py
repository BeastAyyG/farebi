"""Canonical enums and hard limits.

Nothing in this module reads configuration: these are the constants that the
configuration is *expressed in terms of*. Limits live in ``configs/app.yaml``
and arrive via ``farebi.core.config``; the values here are the enums and the
byte-level signatures that cannot be expressed as data.

Layer: L0 (may not import anything internal).
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "ALLOWED_MEDIA_TYPES",
    "FUSION_ELIGIBLE_STATUSES",
    "JPEG_SOI",
    "MAGIC_SIGNATURES",
    "PNG_SIGNATURE",
    "CaptureType",
    "ConfidenceLevel",
    "HarnessStatus",
    "RejectionCode",
    "Verdict",
]


class Verdict(str, Enum):
    """The four outcomes. ``uncertain`` is a product feature, not an apology."""

    LIKELY_REAL = "likely_real"
    LIKELY_FAKE = "likely_fake"
    UNCERTAIN = "uncertain"
    UNABLE_TO_ASSESS = "unable_to_assess"


class CaptureType(str, Enum):
    """How the image was submitted. Affects which signals are applicable."""

    SELFIE = "selfie"
    ID_PHOTO = "id_photo"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    """How stable/reliable a prediction appears — NOT the class probability.

    ``fake_probability`` and ``confidence_level`` are always separate fields.
    The UI must never merge them into "98% guaranteed fake".
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RejectionCode(str, Enum):
    """Distinct, machine-readable reasons an upload was refused.

    Distinct codes matter: security monitoring needs to tell a corrupt file
    from a multi-frame GIF renamed to ``.jpg``, and the two must never share a
    bucket.
    """

    OK = "ok"
    EMPTY_UPLOAD = "empty_upload"
    FILE_TOO_LARGE = "file_too_large"
    MEDIA_TYPE_NOT_ALLOWED = "media_type_not_allowed"
    MAGIC_BYTES_MISMATCH = "magic_bytes_mismatch"
    HEADER_TRUNCATED = "header_truncated"
    DIMENSIONS_TOO_LARGE = "dimensions_too_large"
    MULTI_FRAME_REJECTED = "multi_frame_rejected"
    DECODE_FAILED = "decode_failed"
    PIXEL_BOMB = "pixel_bomb"
    UNSAFE_FILENAME = "unsafe_filename"


class HarnessStatus(str, Enum):
    """The go/no-go verdict the harness writes for a signal (``FAREBI.md`` §7).

    ``unmeasured`` is the important one: a signal nobody has evaluated must not
    be trusted by default. It is the registry's starting state and it blocks
    fusion, so shipping a new signal can never silently change a live verdict.
    """

    KEEP = "keep"
    BENCH = "bench"  # fires only when applicable, quality-gated
    KILL = "kill"  # excluded from fusion; deleted from the tree
    UNMEASURED = "unmeasured"


#: The only statuses allowed to contribute features to fusion. ``FAREBI.md`` §7
#: and ``PLANS/02``: "a signal with status != keep|bench is not wired into
#: fusion". Enforced in code by ``SignalRegistry.fusion_eligible`` and asserted
#: by ``tests/unit/test_registry.py``.
FUSION_ELIGIBLE_STATUSES: frozenset[HarnessStatus] = frozenset(
    {HarnessStatus.KEEP, HarnessStatus.BENCH}
)


# --- File signatures -------------------------------------------------------
# Verified against real file content, never against the client-declared
# Content-Type or the uploaded filename.

JPEG_SOI = b"\xff\xd8\xff"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: Maps a leading byte signature to its canonical media type.
#: Order matters only for readability; matching is by prefix test.
MAGIC_SIGNATURES: dict[bytes, str] = {
    JPEG_SOI: "image/jpeg",
    PNG_SIGNATURE: "image/png",
}

#: The only media types accepted in Phase 01. Widened only with a deliberate,
#: reviewed change (WebP/HEIC need their own signature and decoder review).
ALLOWED_MEDIA_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png"})
