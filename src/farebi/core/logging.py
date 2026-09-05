"""Structured logging that is PII-safe *by construction*.

Non-negotiable #14: never log raw images or EXIF values containing PII.
This is enforced by :class:`PiiScrubber`, which runs on every log record, not
by reviewer diligence. If a caller logs a key we consider sensitive, the value
is replaced before any formatter sees it.

Layer: L0 (may not import anything internal).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

__all__ = [
    "PiiScrubber",
    "bind",
    "clear",
    "configure_logging",
    "get_logger",
]

# Keys whose *values* are replaced outright. Matching is case-insensitive.
_REDACT_ENTIRELY: frozenset[str] = frozenset(
    {
        "image",
        "image_bgr",
        "image_rgb",
        "image_bytes",
        "raw",
        "raw_bytes",
        "raw_image",
        "b64",
        "base64",
        "heatmap_base64",
        "thumbnail",
        "jpeg",
        "jpg",
        "png_bytes",
        "frames",
        "video_frames",
        "embedding",
        "features_raw",
        "tensor",
    }
)

# Keys holding EXIF / capture metadata. These are not proof of anything and are
# frequently PII (GPS, device serial, capture time).
_REDACT_METADATA: frozenset[str] = frozenset(
    {
        "exif",
        "exif_data",
        "metadata",
        "meta",
        "gps",
        "device",
        "device_id",
        "sdk_meta",
        "user_meta",
    }
)

# Keys holding filesystem or upload paths (FAREBI.md: never log raw paths).
_REDACT_PATH: frozenset[str] = frozenset(
    {"path", "file_path", "image_path", "source_path", "filename", "file_name", "temp_path"}
)

#: Any single string value longer than this is truncated in logs. Image payloads
#: and base64 blobs are far larger; truncation keeps logs cheap and safe.
_MAX_STRING_LEN = 256

_TRUNCATION_NOTE = "...<truncated>"
_REDACTED = "<redacted>"


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return lowered in _REDACT_ENTIRELY or lowered in _REDACT_METADATA or lowered in _REDACT_PATH


def _scrub_value(key: str, value: Any, _depth: int = 0) -> Any:
    """Recursively sanitise a single log value.

    Depth-limited so a pathological object graph cannot stall a request thread.
    """
    if _depth > 4:
        return "<max-depth>"

    # Key-based redaction wins over every value-based branch: an EXIF dict is
    # redacted wholesale, not key by key, and an image passed as bytes is not
    # merely summarised by its length.
    if _is_sensitive(key):
        return _REDACTED

    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<bytes len={len(value)}>"

    if isinstance(value, dict):
        return {k: _scrub_value(k, v, _depth + 1) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_scrub_value(key, v, _depth + 1) for v in value]

    if isinstance(value, str):
        if len(value) > _MAX_STRING_LEN:
            return value[:_MAX_STRING_LEN] + _TRUNCATION_NOTE
        return value

    # Numpy arrays, PIL images, torch tensors: never serialise their contents.
    if hasattr(value, "shape") or (hasattr(value, "size") and not isinstance(value, int)):
        return f"<{type(value).__name__}>"

    return value


class PiiScrubber:
    """A structlog processor that removes image bytes, EXIF and paths.

    Applied to both positional events and the key/value pairs of every record.
    """

    def __call__(
        self,
        _logger: Any,
        _method_name: str,
        event_dict: MutableMapping[str, Any],
    ) -> MutableMapping[str, Any]:
        for key in list(event_dict.keys()):
            event_dict[key] = _scrub_value(key, event_dict[key])
        return event_dict


_request_id: ContextVar[str | None] = ContextVar("farebi_request_id", default=None)


def _inject_request_id(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Stamp every line with the active request id, if one is bound."""
    request_id = _request_id.get()
    if request_id is not None:
        event_dict.setdefault("request_id", request_id)
    return event_dict


_HANDLER_MARKER = "_farebi_structlog_handler"


def configure_logging(level: str = "INFO", *, json_logs: bool = True) -> None:
    """Configure structlog and route the stdlib logging module through it.

    Idempotent: safe to call from an app entrypoint and from a test fixture.
    Handlers already attached to the root logger are left alone — including
    pytest's capture handler — so this never blinds a test to the logs it is
    asserting on.
    """
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _inject_request_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        PiiScrubber(),  # must run before any renderer
        structlog.processors.format_exc_info,
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )

    root = logging.getLogger()
    existing = next(
        (h for h in root.handlers if getattr(h, _HANDLER_MARKER, False)),
        None,
    )
    if existing is None:
        setattr(handler, _HANDLER_MARKER, True)
        root.addHandler(handler)
    else:
        existing.setFormatter(handler.formatter)
    root.setLevel(level.upper())

    # structlog is intentionally chatty at DEBUG; keep third-party noise down.
    for noisy in ("urllib3", "asyncio", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def bind(**kwargs: Any) -> None:
    """Bind context for all subsequent log lines (e.g. ``bind(request_id=...)``)."""
    if "request_id" in kwargs:
        _request_id.set(str(kwargs["request_id"]))
    structlog.contextvars.bind_contextvars(**kwargs)


def clear() -> None:
    """Drop all bound context. Call between requests and between tests."""
    _request_id.set(None)
    structlog.contextvars.clear_contextvars()
