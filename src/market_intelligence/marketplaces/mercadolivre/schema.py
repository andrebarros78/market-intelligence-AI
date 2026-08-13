from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


def _collect_paths(value: Any, prefix: str = "$", *, depth: int = 0) -> set[str]:
    if depth > 12:
        return {f"{prefix}:depth-limit"}
    if isinstance(value, dict):
        paths = {f"{prefix}:object"}
        for key in sorted(str(item) for item in value):
            paths.add(f"{prefix}.{key}")
            paths.update(_collect_paths(value[key], f"{prefix}.{key}", depth=depth + 1))
        return paths
    if isinstance(value, list):
        paths = {f"{prefix}:array"}
        for item in value[:20]:
            paths.update(_collect_paths(item, f"{prefix}[]", depth=depth + 1))
        return paths
    return {f"{prefix}:{type(value).__name__}"}


def schema_paths(payload: Any) -> frozenset[str]:
    return frozenset(_collect_paths(payload))


def schema_fingerprint(payload: Any) -> str:
    material = "\n".join(sorted(schema_paths(payload))).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class SchemaDrift:
    baseline_created: bool
    changed: bool
    fingerprint: str
    previous_fingerprint: str | None
    added_paths: tuple[str, ...] = ()
    removed_paths: tuple[str, ...] = ()


class SchemaBaselineRegistry:
    """In-memory R1.4 registry. Persistence/versioning is a later capability."""

    def __init__(self) -> None:
        self._baselines: dict[str, frozenset[str]] = {}
        self._fingerprints: dict[str, str] = {}

    def observe(self, capability: str, payload: Any) -> SchemaDrift:
        current_paths = schema_paths(payload)
        current_fingerprint = schema_fingerprint(payload)
        previous_paths = self._baselines.get(capability)
        previous_fingerprint = self._fingerprints.get(capability)
        if previous_paths is None:
            self._baselines[capability] = current_paths
            self._fingerprints[capability] = current_fingerprint
            return SchemaDrift(
                baseline_created=True,
                changed=False,
                fingerprint=current_fingerprint,
                previous_fingerprint=None,
            )
        added = tuple(sorted(current_paths - previous_paths))
        removed = tuple(sorted(previous_paths - current_paths))
        changed = bool(added or removed)
        if changed:
            self._baselines[capability] = current_paths
            self._fingerprints[capability] = current_fingerprint
        return SchemaDrift(
            baseline_created=False,
            changed=changed,
            fingerprint=current_fingerprint,
            previous_fingerprint=previous_fingerprint,
            added_paths=added,
            removed_paths=removed,
        )
