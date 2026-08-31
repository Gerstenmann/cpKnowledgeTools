"""Local immutable Source state storage, with strict versioned JSON decoding.

The trusted host chooses the storage root and access policy. Files here are
sensitive Source state, not Knowledge or publishable review artifacts.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import types
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

from cp_knowledge_tools.sources.models import (
    CapturedSource,
    EvidenceAddress,
    NormalizedSourceRepresentation,
    RawContentReference,
    SourceRecord,
    SourceSnapshot,
)


def _decode(expected, value):
    """Closed typed decoder: JSON cannot instantiate arbitrary classes or fields."""
    if get_origin(expected) is types.UnionType:
        for choice in get_args(expected):
            try:
                return _decode(choice, value)
            except ValueError:
                pass
        raise ValueError("invalid source union value")
    if get_origin(expected) is tuple:
        if type(value) is not list:
            raise ValueError("expected source array")
        args = get_args(expected)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(args[0], v) for v in value)
        if len(args) != len(value):
            raise ValueError("invalid tuple shape")
        return tuple(_decode(t, v) for t, v in zip(args, value, strict=True))
    if is_dataclass(expected):
        if type(value) is not dict or set(value) != {f.name for f in fields(expected)}:
            raise ValueError("unknown or missing source contract fields")
        hints = get_type_hints(expected)
        return expected(
            **{key: _decode(hints[key], child) for key, child in value.items()}
        )
    if expected in (str, int, bool, type(None)) and type(value) is expected:
        return value
    raise ValueError("invalid source-neutral value")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate source JSON field")
        result[key] = value
    return result


def evidence_address_from_dict(payload: dict) -> EvidenceAddress:
    """Decode without granting trust; the adapter must still resolve the address."""
    return _decode(EvidenceAddress, payload)


class SourceStore:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, directory: str, ref: str, prefix: str, suffix: str) -> Path:
        if not re.fullmatch(rf"{prefix}-[a-f0-9]{{24}}", ref):
            raise ValueError("invalid source state reference")
        path = self.root / directory / f"{ref}{suffix}"
        if self.root.is_symlink() or path.parent.is_symlink() or path.is_symlink():
            raise ValueError("source store symlink forbidden")
        return path

    @staticmethod
    def _put(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Publish a complete file without clobbering an existing state, including
        # a competing writer's file. A crash can only leave an unreferenced temp.
        fd, temporary = tempfile.mkstemp(prefix=".source-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.is_symlink() or path.read_bytes() != payload:
                    raise ValueError("immutable source state conflict") from None
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def _json(kind: str, payload: dict) -> bytes:
        return (
            json.dumps(
                {"schema_version": "1", "kind": kind, "payload": payload},
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")

    @staticmethod
    def _load(path: Path, kind: str) -> dict:
        try:
            envelope = json.loads(
                path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("source state unavailable or invalid") from exc
        if (
            type(envelope) is not dict
            or set(envelope) != {"schema_version", "kind", "payload"}
            or envelope["schema_version"] != "1"
            or envelope["kind"] != kind
        ):
            raise ValueError("unsupported source storage envelope")
        return envelope["payload"]

    def put_capture(self, captured: CapturedSource) -> None:
        captured.validate()
        raw = self._path("raw", captured.raw_reference.raw_content_ref, "RAW", ".bin")
        manifest = self._path(
            "snapshots", captured.snapshot.snapshot_ref, "SNAP", ".json"
        )
        self._put(raw, captured.raw_content)
        payload = {
            "snapshot": asdict(captured.snapshot),
            "record": asdict(captured.record),
            "raw_reference": asdict(captured.raw_reference),
        }
        self._put(manifest, self._json("capture", payload))

    def load_capture(self, snapshot_ref: str) -> CapturedSource:
        payload = self._load(
            self._path("snapshots", snapshot_ref, "SNAP", ".json"), "capture"
        )
        if type(payload) is not dict or set(payload) != {
            "snapshot",
            "record",
            "raw_reference",
        }:
            raise ValueError("invalid capture manifest")
        snapshot = _decode(SourceSnapshot, payload["snapshot"])
        record = _decode(SourceRecord, payload["record"])
        raw = _decode(RawContentReference, payload["raw_reference"])
        try:
            content = self._path("raw", raw.raw_content_ref, "RAW", ".bin").read_bytes()
        except OSError as exc:
            raise ValueError("raw content dependency unavailable") from exc
        captured = CapturedSource(snapshot, record, raw, content)
        captured.validate()
        if snapshot.snapshot_ref != snapshot_ref:
            raise ValueError("snapshot reference integrity mismatch")
        return captured

    def put_representation(self, rep: NormalizedSourceRepresentation) -> None:
        rep.validate()
        self._validate_dependencies(rep)
        path = self._path("representations", rep.representation_ref, "NSR", ".json")
        self._put(path, self._json("normalized_representation", rep.to_dict()))

    def load_representation(
        self, representation_ref: str
    ) -> NormalizedSourceRepresentation:
        payload = self._load(
            self._path("representations", representation_ref, "NSR", ".json"),
            "normalized_representation",
        )
        rep = _decode(NormalizedSourceRepresentation, payload)
        rep.validate()
        self._validate_dependencies(rep)
        if rep.representation_ref != representation_ref:
            raise ValueError("representation reference integrity mismatch")
        return rep

    def _validate_dependencies(self, rep: NormalizedSourceRepresentation) -> None:
        for raw in rep.raw_references:
            captured = self.load_capture(raw.snapshot_ref)
            if (
                captured.raw_reference != raw
                or captured.record not in rep.source_records
            ):
                raise ValueError("source/snapshot dependency integrity mismatch")
