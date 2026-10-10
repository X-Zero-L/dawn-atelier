"""Small immutable contracts shared by game adapters and editor frontends."""

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    """Canonical, finite JSON is also the boundary for portable review files."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True)
class Capability:
    id: str
    title: str
    description: str = ''


@dataclass(frozen=True)
class GameDescriptor:
    id: str
    title: str
    version: str
    capabilities: tuple[Capability, ...] = ()
    read_only: bool = False
    synthetic: bool = False

    def __post_init__(self):
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', self.id):
            raise ValueError('Adapter ID must be a lowercase slug')
        if not self.title or not self.version:
            raise ValueError('Adapter title and version are required')
        object.__setattr__(self, 'capabilities', tuple(self.capabilities))
        ids = [capability.id for capability in self.capabilities]
        if len(set(ids)) != len(ids):
            raise ValueError('Capability IDs must be unique')

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'version': self.version,
            'read_only': self.read_only, 'synthetic': self.synthetic,
            'capabilities': [vars(capability) for capability in self.capabilities],
        }


@dataclass(frozen=True)
class Snapshot:
    source: Path
    data: bytes = field(repr=False)
    sha256: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, 'source', Path(self.source).resolve())
        object.__setattr__(self, 'data', bytes(self.data))
        object.__setattr__(self, 'sha256', digest(self.data))

    @classmethod
    def capture(cls, source):
        source = Path(source).resolve(strict=True)
        return cls(source, source.read_bytes())

    def require_current(self):
        if self.source.read_bytes() != self.data:
            raise RuntimeError('Source save changed since it was opened; reopen it first')


class Adapter:
    """Implement format knowledge here; keep filesystem writes in the editor.

    Operations are adapter-owned JSON objects. validate must verify requested
    changes and preservation of unrelated fields/bytes. compatibility should
    return JSON evidence that changes when installation/schema safety changes.
    runtime is rechecked immediately before publishing a file.
    """

    descriptor: GameDescriptor

    def inspect(self, data: bytes) -> Mapping[str, Any]:
        raise NotImplementedError

    def transform(self, data: bytes, operations: Sequence[Mapping[str, Any]]) -> bytes:
        raise NotImplementedError

    def validate(self, original: bytes, modified: bytes, operations: Sequence[Mapping[str, Any]]) -> None:
        raise NotImplementedError

    def compatibility(self, snapshot: Snapshot) -> Mapping[str, Any]:
        return {'adapter_version': self.descriptor.version}

    def runtime(self, snapshot: Snapshot, mode: str) -> None:
        """Reject unsafe apply/export states (for example, a running game)."""


@dataclass(frozen=True)
class Plan:
    snapshot: Snapshot
    adapter_id: str
    adapter_version: str
    operations_json: str
    evidence_json: str
    before_json: str
    after_json: str
    modified: bytes = field(repr=False)
    plan_id: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, 'modified', bytes(self.modified))
        object.__setattr__(self, 'plan_id', digest(canonical_json(self._binding()).encode('utf-8')))

    @property
    def operations(self):
        return json.loads(self.operations_json)

    def _binding(self):
        return {
            'format': 'atelier-review-v1', 'adapter_id': self.adapter_id,
            'adapter_version': self.adapter_version, 'source': str(self.snapshot.source),
            'sha256_before': self.snapshot.sha256, 'sha256_after': digest(self.modified),
            'operations': self.operations, 'compatibility': json.loads(self.evidence_json),
            'before': json.loads(self.before_json), 'after': json.loads(self.after_json),
        }

    def to_review(self):
        return {**self._binding(), 'plan_id': self.plan_id}
