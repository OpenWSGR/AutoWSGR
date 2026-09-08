"""Agent-facing entrypoint for the debug toolkit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if __package__:
    from .function import e2e, ocr, roi, screenshot
else:
    from tools.debug_toolkit.function import e2e, ocr, roi, screenshot


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == 'e2e':
        return e2e.run(arguments[1:])

    parser = argparse.ArgumentParser(prog='debug_toolkit')
    subparsers = parser.add_subparsers(dest='command', required=True)
    screenshot.add_arguments(subparsers.add_parser('screenshot'))
    roi.add_arguments(subparsers.add_parser('roi'))
    ocr.add_arguments(subparsers.add_parser('ocr'))
    parser.epilog = 'e2e: debug_toolkit e2e <tools/e2e arguments>'
    args = parser.parse_args(arguments)

    if args.command == 'screenshot':
        return screenshot.run(args)
    if args.command == 'roi':
        return roi.run(args)
    return ocr.run(args)


if __name__ == '__main__':
    raise SystemExit(main())
