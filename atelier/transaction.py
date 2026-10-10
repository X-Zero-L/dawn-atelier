"""File transaction shared by adapters, without application configuration."""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

from .models import Snapshot


def _write_new(path, data):
    created = False
    try:
        with path.open('xb') as output:
            created = True
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except BaseException as error:
        if created:
            try:
                path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                error.add_note(f'Partial file could not be removed: {path}: {cleanup_error}')
        raise


def _publish_export(temporary, destination):
    """Return whether a successfully published temporary link remains."""
    if os.name == 'nt':
        # Windows rename is atomic and fails if the destination already exists,
        # including on removable FAT/exFAT drives without hard-link support.
        os.rename(temporary, destination)
        return False
    os.link(temporary, destination)
    return True


def _occupied(path):
    # Path.exists() alone misses dangling symbolic links.
    return path.exists() or path.is_symlink()


def write_modified(source, original, modified, destination, backup_root, validate=None, cleanup_warnings=None):
    """Return a verified backup after safely publishing modified bytes.

    validate, when provided, is called before staging and again immediately
    before publication. Exports use Windows no-replace rename or an exclusive
    hard link elsewhere, so a competing destination is not overwritten. In-place edits
    use atomic replacement after a final source check. No OS primitive can
    make the game process participate in this transaction; adapters must guard
    against a running game before applying.
    """
    snapshot = Snapshot(source, original)
    destination = Path(destination).absolute()
    backups = Path(backup_root).resolve()
    source = snapshot.source
    if destination.is_symlink():
        raise FileExistsError('Output must not be a symbolic link')
    same_file = destination.resolve() == source
    if not same_file and _occupied(destination):
        raise FileExistsError('Output file exists; choose another filename')
    snapshot.require_current()
    if validate is not None:
        validate()
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = backups / f'{source.name}.{stamp}.bak'
    _write_new(backup, snapshot.data)
    if backup.read_bytes() != snapshot.data:
        raise RuntimeError('Backup readback mismatch; output was not written')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.' + stamp + '.tmp')
    staged = False
    published = False
    try:
        _write_new(temporary, modified)
        staged = True
        if temporary.read_bytes() != modified:
            raise RuntimeError('Staged file readback mismatch')
        if validate is not None:
            validate()
        snapshot.require_current()
        if destination.is_symlink():
            raise FileExistsError('Output must not be a symbolic link')
        if same_file:
            temporary.replace(destination)
            staged = False
        else:
            staged = _publish_export(temporary, destination)
        published = True
    finally:
        if staged and temporary.exists():
            try:
                temporary.unlink()
            except OSError as error:
                if not published:
                    raise
                message = f'Output saved; temporary file cleanup failed: {temporary}: {error}'
                if cleanup_warnings is not None:
                    cleanup_warnings.append(message)
                else:
                    logging.getLogger(__name__).warning(message)
    return backup


def write_audit(backup, report):
    """Keep the portable audit beside the immutable original backup."""
    target = Path(str(backup) + '.json')
    payload = {**report, 'recorded_at': datetime.now(timezone.utc).isoformat()}
    _write_new(target, (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    return target
