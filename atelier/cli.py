"""Portable adapter authoring and reviewed save-editing commands."""

import argparse
import json
from pathlib import Path
import sys

from .editor import Editor
from .models import Snapshot
from .reference import JsonReferenceAdapter
from .registry import builtins


def _json_file(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _print(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def _new_file(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as output:
        output.write(text)


def scaffold(target, adapter_id, title):
    # Validate the slug before embedding it in source text.
    from .models import GameDescriptor
    GameDescriptor(adapter_id, title, '1')
    target = Path(target)
    if target.exists():
        raise FileExistsError('Scaffold directory exists; choose a new directory')
    source = '''"""Adapter template. Replace the unimplemented format-specific methods."""
from atelier import Adapter, Capability, Editor, GameDescriptor, Registry, Snapshot


class GameAdapter(Adapter):
    descriptor = GameDescriptor(
        ADAPTER_ID, ADAPTER_TITLE, '1',
        (Capability('set', 'Set a confirmed field'),),
        read_only=True,  # Enable writes only after preservation checks are implemented.
    )

    def inspect(self, data):
        raise NotImplementedError('Decode this game format and expose confirmed fields')

    def transform(self, data, operations):
        raise NotImplementedError('Change only confirmed fields; preserve unrelated bytes')

    def validate(self, original, modified, operations):
        raise NotImplementedError('Verify requested values and preservation of unknown data')

    def compatibility(self, snapshot):
        raise NotImplementedError('Return reviewed format/schema/install evidence or reject')

    def runtime(self, snapshot, mode):
        if mode == 'apply':
            raise RuntimeError('Implement the game-running guard before enabling apply')


def registry():
    result = Registry()
    result.register(GameAdapter())
    return result
'''.replace('ADAPTER_ID', repr(adapter_id)).replace('ADAPTER_TITLE', repr(title))
    # mkdir without exist_ok protects a competing authoring operation.
    target.mkdir(parents=True, exist_ok=False)
    _new_file(target / 'adapter.py', source)
    _new_file(target / 'README.md', f'''# {title} adapter

This is source scaffolding, not a supported game adapter yet.

Implement the five format-specific methods in `adapter.py`. Keep decoding,
compatibility evidence and semantic validation inside the adapter. File writes,
preview bindings and backups belong to `atelier.Editor`.

Register the adapter explicitly in your application, then pass that registry to
`atelier.cli.main(registry=registry())` or use the Python API. The framework does
not load Python from review documents, downloaded manifests or arbitrary paths.

Use disposable fixture saves to verify round trips and unknown-data preservation.
Only remove `read_only=True` once those contracts are implemented. In-place apply
also requires a reliable check that the game is not running.
''')
    return {'directory': str(target.resolve()), 'adapter_id': adapter_id,
            'files': ['adapter.py', 'README.md'], 'read_only': True}


def main(argv=None, *, registry=None):
    parser = argparse.ArgumentParser(description='Atelier save framework: inspect, preview and write reviewed edits.')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List explicitly registered adapters')
    sample = commands.add_parser('sample', help='Create a synthetic JSON reference fixture (not a game save)')
    sample.add_argument('output', type=Path)
    make = commands.add_parser('scaffold', help='Create a read-only adapter source template')
    make.add_argument('directory', type=Path)
    make.add_argument('--id', required=True)
    make.add_argument('--title', required=True)
    for verb in ('inspect', 'preview'):
        command = commands.add_parser(verb)
        command.add_argument('--game', required=True)
        command.add_argument('save', type=Path)
        if verb == 'preview':
            command.add_argument('--operations', type=Path, required=True, help='JSON array of adapter operations')
            command.add_argument('--review', type=Path, required=True, help='New review JSON to write')
    for verb in ('export', 'apply'):
        command = commands.add_parser(verb)
        command.add_argument('--review', type=Path, required=True)
        command.add_argument('--approve', required=True, metavar='PLAN_ID', help='plan_id printed by preview')
        command.add_argument('--backups', type=Path, required=True)
        if verb == 'export':
            command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'sample':
            _new_file(args.output, JsonReferenceAdapter.sample().decode('utf-8'))
            _print({'synthetic': True, 'output': str(args.output.resolve())})
            return 0
        if args.command == 'scaffold':
            _print(scaffold(args.directory, args.id, args.title))
            return 0
        registry = registry if registry is not None else builtins()
        if args.command == 'list':
            _print({'adapters': registry.descriptors()})
            return 0
        if args.command in ('inspect', 'preview'):
            adapter = registry.get(args.game)
            snapshot = Snapshot.capture(args.save)
            if args.command == 'inspect':
                _print({'adapter': adapter.descriptor.to_dict(), 'source': str(snapshot.source),
                        'sha256': snapshot.sha256, 'compatibility': adapter.compatibility(snapshot),
                        'inspection': adapter.inspect(snapshot.data)})
            else:
                # preview never creates its backup root or writes to the save.
                plan = Editor(adapter, args.review.parent / 'backups').preview(snapshot, _json_file(args.operations))
                document = plan.to_review()
                _new_file(args.review, json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
                _print(document)
            return 0
        document = _json_file(args.review)
        if not isinstance(document, dict):
            raise ValueError('Review must be a JSON object')
        adapter = registry.get(document.get('adapter_id'))
        editor = Editor(adapter, args.backups)
        plan = editor.review(document, args.approve)
        destination = args.output if args.command == 'export' else plan.snapshot.source
        _print(editor.commit(plan, destination, approval=args.approve, mode=args.command))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
