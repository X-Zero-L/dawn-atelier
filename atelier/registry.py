"""Explicit adapter registration; no downloaded code or entry-point discovery."""

from .models import Adapter


class Registry:
    def __init__(self):
        self._adapters = {}

    def register(self, adapter: Adapter):
        key = adapter.descriptor.id
        if key in self._adapters:
            raise ValueError(f'Adapter already registered: {key}')
        self._adapters[key] = adapter
        return adapter

    def get(self, adapter_id):
        try:
            return self._adapters[adapter_id]
        except KeyError:
            raise ValueError(f'Unknown game adapter: {adapter_id}') from None

    def descriptors(self):
        return [self._adapters[key].descriptor.to_dict() for key in sorted(self._adapters)]


def builtins():
    from .reference import JsonReferenceAdapter
    registry = Registry()
    registry.register(JsonReferenceAdapter())
    return registry
