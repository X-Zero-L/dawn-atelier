"""Synthetic format for adapter authors. This is not another supported game."""

import copy
import json

from .models import Adapter, Capability, GameDescriptor, canonical_json


class JsonReferenceAdapter(Adapter):
    descriptor = GameDescriptor(
        'json-reference', 'Synthetic JSON reference (not a game)', '1',
        (Capability('set', 'Set an existing scalar', 'Use a JSON Pointer target, such as /player/gold.'),),
        synthetic=True,
    )

    @staticmethod
    def sample():
        return b'{"format":"atelier-reference-v1","player":{"gold":100},"unknown":{"preserved":true}}\n'

    def _decode(self, data):
        def pairs(entries):
            result = {}
            for key, value in entries:
                if key in result:
                    raise ValueError(f'Duplicate JSON property: {key}')
                result[key] = value
            return result

        def constant(value):
            raise ValueError(f'Non-finite JSON number: {value}')

        document = json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
        if not isinstance(document, dict) or document.get('format') != 'atelier-reference-v1':
            raise ValueError('Expected a synthetic atelier-reference-v1 document')
        return document

    def inspect(self, data):
        return {'synthetic': True, 'document': self._decode(data)}

    @staticmethod
    def _assign(document, operation):
        if set(operation) != {'action', 'target', 'value'} or operation['action'] != 'set':
            raise ValueError('Reference operations require action=set, target and value')
        target = operation['target']
        if not isinstance(target, str) or not target.startswith('/'):
            raise ValueError('Target must be a JSON Pointer to an existing scalar')
        tokens = target[1:].split('/')
        for token in tokens:
            if '~' in token.replace('~0', '').replace('~1', ''):
                raise ValueError('Invalid JSON Pointer escape')
        tokens = [token.replace('~1', '/').replace('~0', '~') for token in tokens]
        if tokens[0] == 'format':
            raise ValueError('The reference format marker cannot be edited')
        node = document
        for token in tokens[:-1]:
            if not isinstance(node, dict) or token not in node:
                raise ValueError('Target must already exist in an object')
            node = node[token]
        key = tokens[-1]
        if not isinstance(node, dict) or key not in node or isinstance(node[key], (dict, list)):
            raise ValueError('Target must already exist as a scalar in an object')
        value = operation['value']
        if isinstance(value, (dict, list)):
            raise ValueError('Reference values must be JSON scalars')
        if type(value) is not type(node[key]):
            raise ValueError('Reference edits must retain the scalar type')
        node[key] = value

    def _expected(self, original, operations):
        document = copy.deepcopy(self._decode(original))
        for operation in operations:
            self._assign(document, operation)
        return document

    def transform(self, data, operations):
        # This reference format preserves unknown JSON values, not whitespace.
        # Binary game adapters must enforce their own byte preservation rules.
        return (canonical_json(self._expected(data, operations)) + '\n').encode('utf-8')

    def validate(self, original, modified, operations):
        expected = self._expected(original, operations)
        actual = self._decode(modified)
        if canonical_json(actual) != canonical_json(expected):
            raise ValueError('Unexpected change outside the requested reference operations')

    def compatibility(self, snapshot):
        self._decode(snapshot.data)
        return {'format': 'atelier-reference-v1', 'adapter_version': self.descriptor.version, 'synthetic': True}
