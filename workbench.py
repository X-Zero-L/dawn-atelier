"""Application CLI with explicitly registered game adapters.

Run `python workbench.py list` or `python workbench.py --help`.
The standalone `python -m atelier` command needs no game files.
"""

from atelier.cli import main as framework_main
from atelier.registry import builtins
from piper_adapter import ThePiperAdapter


def registry():
    result = builtins()
    result.register(ThePiperAdapter())
    return result


def main():
    return framework_main(registry=registry())


if __name__ == '__main__':
    raise SystemExit(main())
