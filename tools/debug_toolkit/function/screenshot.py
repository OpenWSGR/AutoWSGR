"""Save one raw ADB screenshot with a timestamped name."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tools.ocr_crop_tool import (
    _read_saved_serial,
    _resolve_adb_path,
    _write_png,
    capture_adb_screen,
)


if TYPE_CHECKING:
    import argparse


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = PACKAGE_ROOT / 'result' / 'screenshot'
ADB_PATH = PACKAGE_ROOT / 'adb' / 'adb.exe'


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--serial', help='ADB serial, defaults to the saved serial')
    parser.add_argument('--adb-path', type=Path, help='override the bundled adb.exe')
    parser.add_argument('-o', '--output', type=Path, help='explicit PNG path')


def run(args: argparse.Namespace) -> int:
    adb_path = args.adb_path or (ADB_PATH if ADB_PATH.is_file() else _resolve_adb_path())
    serial = args.serial or _read_saved_serial()
    image = capture_adb_screen(adb_path, serial)
    output = args.output or RESULT_ROOT / f'screenshot_{datetime.now(UTC):%Y%m%d_%H%M%S}.png'
    _write_png(output, image)
    print(output)
    return 0
