"""Synthetic image and hostile-upload generators.

Kept in one place because the smoke script and the test suite must exercise the
*same* inputs — a rejection matrix that differs between CI and the smoke script
is a rejection matrix that proves nothing.

No real face photographs are used anywhere in the repository. Synthetic faces
are privacy-safe, deterministic, and reproducible without a data download.
"""

from __future__ import annotations

import io
import zlib

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw

from farebi.core.constants import RejectionCode
from farebi.core.security import UploadLimits

__all__ = [
    "encode_grayscale_png",
    "encode_jpeg",
    "encode_png",
    "hostile_bytes_jpeg",
    "hostile_cases",
    "hostile_oversized",
    "hostile_png_dimensions",
    "hostile_truncated_jpeg",
    "make_apng",
    "synthetic_face_rgb",
]

_EXIF_ORIENTATION_TAG = 274

# A 1x1 GIF. Content is irrelevant; only the signature matters.
_GIF_BYTES = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
    b"\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00"
    b"\x02\x02\x44\x01\x00\x3b"
)

_PDF_BYTES = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def synthetic_face_rgb(size: int = 512, *, seed: int = 7) -> npt.NDArray[np.uint8]:
    """Draw a crude front-facing face: skin oval, eyes with iris, mouth, hair.

    It is not photorealistic and MediaPipe may or may not detect it — that
    variance is fine. What it reliably provides is a valid, non-uniform,
    correctly-shaped RGB image for the decode/quality/capture path.
    """
    rng = np.random.default_rng(seed)
    image = Image.new("RGB", (size, size), (198, 205, 214))
    draw = ImageDraw.Draw(image)

    cx, cy = size // 2, size // 2
    face_w, face_h = int(size * 0.42), int(size * 0.54)

    # Neck and shoulders.
    draw.ellipse(
        [cx - face_w * 0.55, cy + face_h * 0.65, cx + face_w * 0.55, cy + face_h * 1.5],
        fill=(196, 150, 128),
    )
    # Hair behind the face.
    draw.ellipse(
        [cx - face_w, cy - face_h * 1.05, cx + face_w, cy + face_h * 0.25],
        fill=(58, 40, 32),
    )
    # Face.
    draw.ellipse(
        [cx - face_w // 2, cy - face_h // 2, cx + face_w // 2, cy + face_h // 2],
        fill=(226, 178, 148),
    )

    eye_dx = int(face_w * 0.22)
    eye_y = cy - int(face_h * 0.10)
    eye_r = int(face_w * 0.13)

    for sign in (-1, 1):
        ex = cx + sign * eye_dx
        draw.ellipse([ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r], fill=(250, 250, 248))
        iris_r = int(eye_r * 0.48)
        draw.ellipse([ex - iris_r, eye_y - iris_r, ex + iris_r, eye_y + iris_r], fill=(62, 48, 40))
        pupil_r = int(iris_r * 0.45)
        draw.ellipse(
            [ex - pupil_r, eye_y - pupil_r, ex + pupil_r, eye_y + pupil_r], fill=(16, 12, 10)
        )

    # Nose and mouth.
    draw.line([cx, eye_y, cx, cy + face_h * 0.14], fill=(200, 150, 124), width=max(2, size // 128))
    draw.arc(
        [cx - int(face_w * 0.20), cy + face_h * 0.12, cx + int(face_w * 0.20), cy + face_h * 0.34],
        start=15,
        end=165,
        fill=(168, 92, 84),
        width=max(2, size // 128),
    )

    array = np.asarray(image, dtype=np.uint8)
    # A little sensor-like noise: pure flat regions make blur measurement
    # meaningless, and the Laplacian variance collapses to exactly zero.
    noise = rng.integers(-4, 5, size=array.shape, dtype=np.int16)
    return np.clip(array.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def encode_png(rgb: npt.NDArray[np.uint8]) -> bytes:
    """Encode an RGB array as PNG bytes."""
    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def encode_jpeg(
    rgb: npt.NDArray[np.uint8],
    *,
    quality: int = 92,
    exif_orientation: int | None = None,
) -> bytes:
    """Encode an RGB array as JPEG bytes, optionally with an EXIF orientation tag."""
    buffer = io.BytesIO()
    image = Image.fromarray(rgb)

    # Pillow >= 12 rejects an explicit `exif=None`, so the kwarg is only passed
    # when there is actually an orientation tag to write.
    save_kwargs: dict[str, object] = {"format": "JPEG", "quality": quality}
    if exif_orientation is not None:
        exif = image.getexif()
        exif[_EXIF_ORIENTATION_TAG] = int(exif_orientation)
        save_kwargs["exif"] = exif

    image.save(buffer, **save_kwargs)  # type: ignore[arg-type]
    return buffer.getvalue()


def encode_grayscale_png(rgb: npt.NDArray[np.uint8]) -> bytes:
    """Encode as single-channel PNG, to exercise the grayscale conversion path."""
    buffer = io.BytesIO()
    Image.fromarray(rgb).convert("L").save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Hostile inputs
# ---------------------------------------------------------------------------


def hostile_oversized(limits: UploadLimits) -> bytes:
    """Bytes longer than the configured limit, with a valid JPEG signature."""
    return b"\xff\xd8\xff" + b"\x00" * (limits.max_bytes + 1)


def hostile_truncated_jpeg() -> bytes:
    """JPEG signature + a partial APP0 segment: no SOF marker is reachable."""
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"


def hostile_png_dimensions(width: int, height: int) -> bytes:
    """A structurally valid PNG header claiming absurd dimensions.

    Only IHDR + IEND: no pixel data at all. This must be rejected on the header
    alone, never decoded.
    """

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            len(payload).to_bytes(4, "big")
            + tag
            + payload
            + zlib.crc32(tag + payload).to_bytes(4, "big")
        )

    ihdr = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + bytes([8, 2, 0, 0, 0])  # bit depth 8, colour type 2 (truecolour)
    )
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


def hostile_bytes_jpeg(valid_jpeg: bytes) -> bytes:
    """Valid JPEG header, payload replaced with zeros: header ok, decode fails."""
    cut = int(len(valid_jpeg) * 0.55)
    return valid_jpeg[:cut] + b"\x00" * (len(valid_jpeg) - cut)


def make_apng(rgb: npt.NDArray[np.uint8]) -> bytes | None:
    """Build a genuinely multi-frame PNG, or ``None`` if Pillow cannot.

    GIF renamed to ``.jpg`` is caught by the magic-byte check, so it never
    reaches the frame counter. APNG is the only way to exercise
    ``MULTI_FRAME_REJECTED`` through an allowed media type.
    """
    buffer = io.BytesIO()
    base = Image.fromarray(rgb).resize((128, 128))
    second = base.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    try:
        base.save(buffer, format="PNG", save_all=True, append_images=[second], duration=100, loop=0)
    except (ValueError, OSError):
        return None
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as probe:
        if int(getattr(probe, "n_frames", 1) or 1) < 2:
            return None
    return data


def hostile_cases(
    limits: UploadLimits, valid_jpeg: bytes
) -> dict[str, tuple[bytes, str, str, RejectionCode]]:
    """The rejection matrix.

    Returns ``{case_name: (data, declared_media_type, filename, expected_code)}``.
    Every code in :class:`RejectionCode` that an attacker can trigger appears
    here, and each case must produce a **distinct** failure.
    """
    return {
        "empty_upload": (b"", "image/jpeg", "empty.jpg", RejectionCode.EMPTY_UPLOAD),
        "oversized": (
            hostile_oversized(limits),
            "image/jpeg",
            "huge.jpg",
            RejectionCode.FILE_TOO_LARGE,
        ),
        "gif_renamed_jpg": (
            _GIF_BYTES,
            "image/jpeg",
            "animated.jpg",
            RejectionCode.MAGIC_BYTES_MISMATCH,
        ),
        "pdf_renamed_png": (
            _PDF_BYTES,
            "image/png",
            "document.png",
            RejectionCode.MAGIC_BYTES_MISMATCH,
        ),
        "png_declared_jpeg": (
            hostile_png_dimensions(8, 8),
            "image/jpeg",
            "confused.jpg",
            RejectionCode.MAGIC_BYTES_MISMATCH,
        ),
        "truncated_header": (
            hostile_truncated_jpeg(),
            "image/jpeg",
            "truncated.jpg",
            RejectionCode.HEADER_TRUNCATED,
        ),
        "oversized_dimensions": (
            hostile_png_dimensions(20000, 20000),
            "image/png",
            "bomb.png",
            RejectionCode.DIMENSIONS_TOO_LARGE,
        ),
        "path_traversal_filename": (
            valid_jpeg,
            "image/jpeg",
            "../../../../etc/passwd.jpg",
            RejectionCode.UNSAFE_FILENAME,
        ),
        "disallowed_media_type": (
            valid_jpeg,
            "application/pdf",
            "document.pdf",
            RejectionCode.MEDIA_TYPE_NOT_ALLOWED,
        ),
        "corrupt_payload": (
            hostile_bytes_jpeg(valid_jpeg),
            "image/jpeg",
            "corrupt.jpg",
            RejectionCode.DECODE_FAILED,
        ),
    }
