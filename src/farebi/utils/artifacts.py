"""Versioned load/save for the ``artifacts/`` directory.

The offline factory writes here; the online API reads only from here
(``FAREBI.md`` §8). Every save writes a sidecar ``<name>.meta.json`` recording
the git SHA, package versions, timestamp and the payload hash, so that any
production result can be reproduced from ``model_version`` +
``threshold_version`` + ``calibration_version`` alone.

Layer: L0 (may not import anything internal).
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
import pickle
import platform
import subprocess
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from farebi.utils.hashing import sha256_file

__all__ = [
    "ArtifactError",
    "artifact_path",
    "build_metadata",
    "git_sha",
    "load_json",
    "load_pickle",
    "save_json",
    "save_pickle",
]

_TRACKED_PACKAGES = ("numpy", "torch", "torchvision", "opencv-python-headless", "mediapipe")


class ArtifactError(RuntimeError):
    """Raised when an artifact is missing, unreadable, or fails validation."""


def git_sha() -> str | None:
    """Current git commit, or ``None`` when not in a repository.

    Never raises: an artifact save must not fail because git is absent.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = result.stdout.strip()
    return sha or None


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in _TRACKED_PACKAGES:
        try:
            versions[package] = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def build_metadata(payload_path: Path, **extra: Any) -> dict[str, Any]:
    """Assemble the provenance block written alongside every artifact."""
    metadata: dict[str, Any] = {
        "artifact": payload_path.name,
        "sha256": sha256_file(payload_path),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": _package_versions(),
    }
    metadata.update(extra)
    return metadata


def artifact_path(name: str, *, base_dir: str | Path = "artifacts") -> Path:
    """Resolve ``name`` under the artifacts directory, creating parents."""
    path = Path(base_dir) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_sidecar(payload_path: Path, **extra: Any) -> Path:
    sidecar = payload_path.with_suffix(payload_path.suffix + ".meta.json")
    sidecar.write_text(
        json.dumps(build_metadata(payload_path, **extra), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return sidecar


def save_json(name: str, payload: Any, *, base_dir: str | Path = "artifacts", **extra: Any) -> Path:
    """Write a JSON artifact plus its provenance sidecar. Returns the payload path."""
    path = artifact_path(name, base_dir=base_dir)
    try:
        serialisable = (
            asdict(payload) if is_dataclass(payload) and not isinstance(payload, type) else payload
        )
        path.write_text(json.dumps(serialisable, indent=2, sort_keys=True), encoding="utf-8")
    except (TypeError, ValueError) as exc:
        raise ArtifactError(f"{name} is not JSON-serialisable: {exc}") from exc
    _write_sidecar(path, **extra)
    return path


def load_json(name: str, *, base_dir: str | Path = "artifacts") -> Any:
    """Read a JSON artifact. Raises :class:`ArtifactError` when absent."""
    path = Path(base_dir) / name
    if not path.exists():
        raise ArtifactError(f"artifact {name!r} does not exist at {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"artifact {name!r} is not valid JSON: {exc}") from exc


def save_pickle(
    name: str, payload: Any, *, base_dir: str | Path = "artifacts", **extra: Any
) -> Path:
    """Write a pickle artifact (fitted fusion models, calibration objects).

    Pickle is a deserialisation risk: only ever load artifacts that this
    repository wrote, and never load one from an untrusted location.
    """
    path = artifact_path(name, base_dir=base_dir)
    try:
        with path.open("wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    except (pickle.PicklingError, TypeError, AttributeError) as exc:
        # AttributeError covers "cannot pickle local object", which is what
        # lambdas and nested functions raise.
        raise ArtifactError(f"{name} cannot be pickled: {exc}") from exc
    _write_sidecar(path, **extra)
    return path


def load_pickle(name: str, *, base_dir: str | Path = "artifacts") -> Any:
    """Read a pickle artifact. See the security note on :func:`save_pickle`."""
    path = Path(base_dir) / name
    if not path.exists():
        raise ArtifactError(f"artifact {name!r} does not exist at {path}")
    try:
        with path.open("rb") as handle:
            return pickle.load(handle)
    except (pickle.UnpicklingError, EOFError) as exc:
        raise ArtifactError(f"artifact {name!r} could not be unpickled: {exc}") from exc
