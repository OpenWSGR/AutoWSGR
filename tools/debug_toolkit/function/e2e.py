"""Pass-through wrapper for the existing E2E runner."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[1]
RESULT_LOG_ROOT = PACKAGE_ROOT / 'result' / 'logs'


def _copy_latest_log() -> None:
    source_root = REPO_ROOT / 'logs' / 'e2e_tools'
    candidates = [path for path in source_root.glob('*/*') if path.is_dir()]
    if not candidates:
        return
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    target = RESULT_LOG_ROOT / latest.parent.name / latest.name
    shutil.copytree(latest, target, dirs_exist_ok=True)
    print(f'log: {target}')


def run(arguments: list[str]) -> int:
    command = [
        sys.executable,
        str(PACKAGE_ROOT / 'function' / 'e2e_runner' / 'run.py'),
        *arguments,
    ]
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)  # noqa: S603
    if '--list' not in arguments:
        _copy_latest_log()
    return completed.returncode
