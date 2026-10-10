"""Preview-bound orchestration, independent of any game or frontend."""

import json
from pathlib import Path
from typing import Mapping

from .models import Adapter, Plan, Snapshot, canonical_json, digest
from .transaction import write_audit, write_modified


class Editor:
    def __init__(self, adapter: Adapter, backup_root):
        self.adapter = adapter
        # An explicit game directory prevents two adapters sharing backups.
        self.backup_root = Path(backup_root).resolve() / adapter.descriptor.id

    def preview(self, snapshot: Snapshot, operations):
        snapshot.require_current()
        if not isinstance(operations, (list, tuple)) or not operations:
            raise ValueError('At least one operation is required')
        if any(not isinstance(operation, Mapping) for operation in operations):
            raise ValueError('Operations must be JSON objects')
        operations_json = canonical_json(list(operations))
        normalized = json.loads(operations_json)
        evidence_json = canonical_json(self.adapter.compatibility(snapshot))
        before = canonical_json(self.adapter.inspect(snapshot.data))
        modified = bytes(self.adapter.transform(snapshot.data, normalized))
        # Each call receives a fresh operations copy: an adapter cannot mutate
        # the contract seen by another stage.
        self.adapter.validate(snapshot.data, modified, json.loads(operations_json))
        after = canonical_json(self.adapter.inspect(modified))
        if canonical_json(self.adapter.compatibility(snapshot)) != evidence_json:
            raise ValueError('Plan compatibility changed during calculation; create a new preview')
        snapshot.require_current()
        return Plan(snapshot, self.adapter.descriptor.id, self.adapter.descriptor.version,
                    operations_json, evidence_json, before, after, modified)

    def review(self, document, approval):
        """Rebuild a persisted review against current source and adapter code.

        JSON is never a trusted serialized executable plan. The displayed ID
        must be supplied separately and every byte/digest/evidence is rebuilt.
        """
        if not isinstance(document, dict) or document.get('format') != 'atelier-review-v1':
            raise ValueError('Unsupported review document')
        if not approval or document.get('plan_id') != approval:
            raise ValueError('Explicit approval must match the preview plan_id')
        if document.get('adapter_id') != self.adapter.descriptor.id:
            raise ValueError('Review belongs to a different game adapter')
        if document.get('adapter_version') != self.adapter.descriptor.version:
            raise ValueError('Adapter changed; create a new preview')
        snapshot = Snapshot.capture(document['source'])
        if snapshot.sha256 != document.get('sha256_before'):
            raise RuntimeError('Source save changed since preview; reopen it first')
        plan = self.preview(snapshot, document['operations'])
        if canonical_json(plan.to_review()) != canonical_json(document) or plan.plan_id != approval:
            raise ValueError('Review changed or compatibility changed; create a new preview')
        return plan

    def commit(self, plan: Plan, destination, *, approval: str, mode='export'):
        if mode not in ('export', 'apply'):
            raise ValueError('Mode must be export or apply')
        descriptor = self.adapter.descriptor
        if descriptor.read_only:
            raise PermissionError('This adapter is read-only')
        if descriptor.synthetic and mode == 'apply':
            raise PermissionError('Synthetic reference adapters only export copies')
        if plan.adapter_id != descriptor.id or plan.adapter_version != descriptor.version:
            raise ValueError('Plan belongs to a different adapter or version')
        if approval != plan.plan_id:
            raise ValueError('Explicit approval must match the preview plan_id')
        destination = Path(destination).absolute()
        if mode == 'export' and destination.resolve() == plan.snapshot.source:
            raise ValueError('Export must use a new destination')
        if mode == 'apply' and destination.resolve() != plan.snapshot.source:
            raise ValueError('Apply must target the opened source save')

        def validate():
            # Rebuild transforms too: accepting a constructed/modified Plan
            # object must not bypass the preview validation boundary.
            current = self.preview(plan.snapshot, plan.operations)
            if canonical_json(current.to_review()) != canonical_json(plan.to_review()):
                raise ValueError('Plan or compatibility changed; create a new preview')
            self.adapter.runtime(plan.snapshot, mode)
            if canonical_json(self.adapter.compatibility(plan.snapshot)) != plan.evidence_json:
                raise ValueError('Plan compatibility changed; create a new preview')

        cleanup_warnings = []
        backup = write_modified(plan.snapshot.source, plan.snapshot.data, plan.modified,
                                destination, self.backup_root, validate=validate,
                                cleanup_warnings=cleanup_warnings)
        report = {
            'format': 'atelier-audit-v1', 'adapter_id': descriptor.id,
            'adapter_version': descriptor.version, 'plan_id': plan.plan_id, 'mode': mode,
            'source': str(plan.snapshot.source), 'output': str(destination), 'backup': str(backup),
            'sha256_before': plan.snapshot.sha256, 'sha256_after': digest(plan.modified),
            'operations': plan.operations, 'compatibility': json.loads(plan.evidence_json),
        }
        if cleanup_warnings:
            report['warnings'] = cleanup_warnings
        try:
            report['audit'] = str(write_audit(backup, report))
        except OSError as error:
            # The edit already succeeded; report its path/backup truthfully.
            report['audit_error'] = str(error)
        return report
