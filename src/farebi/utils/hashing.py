"""Content hashing.

Used for three distinct purposes, deliberately with one function each so the
intent is visible at the call site:

* ``sha256_bytes`` — identity of an uploaded image (audit trail without
  retaining the image itself; non-negotiable #7).
* ``sha256_file`` — identity of a model weights file or dataset shard.
* ``sha256_config`` — identity of a serialisable configuration, so a result can
  be traced to the exact config that produced it.

Layer: L0 (may not import anything internal).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = ["sha256_bytes", "sha256_config", "sha256_file"]

_CHUNK_SIZE = 1 << 20  # 1 MiB


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of a byte string."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path, *, chunked: bool = True) -> str:
    """Hex SHA-256 of a file, streamed so multi-GB weights do not blow memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        if chunked:
            for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
        else:  # pragma: no cover - convenience for small files
            digest.update(handle.read())
    return digest.hexdigest()


def sha256_config(config: Any) -> str:
    """Hex SHA-256 of a JSON-serialisable object.

    Keys are sorted and separators fixed so that two logically identical
    configs hash identically regardless of insertion order. Non-serialisable
    values are rendered via ``repr`` rather than raising: a config hash must
    never break a training run.
    """

    def _default(value: Any) -> str:
        return f"<unserialisable {type(value).__name__}: {value!r}>"

    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=_default)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
