"""Artifact provenance and hashing."""

from __future__ import annotations

import json

import pytest

from farebi.utils.artifacts import (
    ArtifactError,
    build_metadata,
    git_sha,
    load_json,
    load_pickle,
    save_json,
    save_pickle,
)
from farebi.utils.hashing import sha256_bytes, sha256_config, sha256_file


class TestHashing:
    def test_sha256_bytes_is_stable_and_correct_length(self) -> None:
        digest = sha256_bytes(b"farebi")
        assert len(digest) == 64
        assert digest == sha256_bytes(b"farebi")
        assert digest != sha256_bytes(b"farebi!")

    def test_sha256_file_matches_sha256_bytes(self, tmp_path) -> None:
        path = tmp_path / "weights.bin"
        payload = b"x" * 300_000  # exceeds the 1 MiB chunk? no, but exercises chunking
        path.write_bytes(payload)
        assert sha256_file(path) == sha256_bytes(payload)

    def test_sha256_file_streams_large_files(self, tmp_path) -> None:
        path = tmp_path / "big.bin"
        payload = b"y" * (2 * 1024 * 1024 + 7)  # > 1 MiB: multiple chunks
        path.write_bytes(payload)
        assert sha256_file(path) == sha256_bytes(payload)

    def test_sha256_config_is_order_independent(self) -> None:
        assert sha256_config({"a": 1, "b": 2}) == sha256_config({"b": 2, "a": 1})

    def test_sha256_config_is_sensitive_to_values(self) -> None:
        assert sha256_config({"a": 1}) != sha256_config({"a": 2})

    def test_sha256_config_tolerates_unserialisable_values(self) -> None:
        """A config hash must never break a training run."""

        class _Opaque:
            def __repr__(self) -> str:
                return "<opaque>"

        digest = sha256_config({"model": _Opaque()})
        assert len(digest) == 64


class TestArtifacts:
    def test_save_and_load_json_roundtrip(self, tmp_path) -> None:
        payload = {"q_lo": 0.31, "q_hi": 0.72, "version": "1.2.3"}
        path = save_json("thresholds.json", payload, base_dir=tmp_path)

        assert path.exists()
        assert load_json("thresholds.json", base_dir=tmp_path) == payload

    def test_every_save_writes_a_provenance_sidecar(self, tmp_path) -> None:
        save_json("thresholds.json", {"a": 1}, base_dir=tmp_path, target_error=0.05)
        sidecar = tmp_path / "thresholds.json.meta.json"

        assert sidecar.exists()
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        assert meta["artifact"] == "thresholds.json"
        assert len(meta["sha256"]) == 64
        assert meta["target_error"] == 0.05, "extra provenance is preserved"
        assert "created_at" in meta
        assert "python" in meta
        assert "packages" in meta

    def test_git_sha_is_present_or_none_but_never_raises(self) -> None:
        value = git_sha()
        assert value is None or len(value) == 40

    def test_build_metadata_records_the_payload_hash(self, tmp_path) -> None:
        path = tmp_path / "model.pt"
        path.write_bytes(b"weights")
        meta = build_metadata(path)

        assert meta["sha256"] == sha256_bytes(b"weights")

    def test_load_missing_artifact_raises_artifact_error(self, tmp_path) -> None:
        with pytest.raises(ArtifactError, match="does not exist"):
            load_json("nope.json", base_dir=tmp_path)

    def test_load_corrupt_json_raises_artifact_error(self, tmp_path) -> None:
        (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(ArtifactError, match="not valid JSON"):
            load_json("bad.json", base_dir=tmp_path)

    def test_pickle_roundtrip(self, tmp_path) -> None:
        obj = {"coefficients": [1.0, 2.0, 3.0], "feature_names": ["a", "b", "c"]}
        save_pickle("fusion.pkl", obj, base_dir=tmp_path)
        assert load_pickle("fusion.pkl", base_dir=tmp_path) == obj
        assert (tmp_path / "fusion.pkl.meta.json").exists()

    def test_unpicklable_object_raises_artifact_error(self, tmp_path) -> None:
        with pytest.raises(ArtifactError, match="cannot be pickled"):
            save_pickle("bad.pkl", lambda x: x, base_dir=tmp_path)

    def test_nested_paths_are_created(self, tmp_path) -> None:
        path = save_json("reports/2026/evaluation.json", {"ok": True}, base_dir=tmp_path)
        assert path.parent.is_dir()
        assert load_json("reports/2026/evaluation.json", base_dir=tmp_path) == {"ok": True}

    def test_dataclass_payloads_are_serialised(self, tmp_path) -> None:
        from dataclasses import dataclass

        @dataclass
        class _Point:
            x: int
            y: int

        save_json("point.json", _Point(1, 2), base_dir=tmp_path)
        assert load_json("point.json", base_dir=tmp_path) == {"x": 1, "y": 2}
