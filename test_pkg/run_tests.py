"""测试套件分发器。

扫描 test_pkg/ 各子目录中的 ``tests.py``，导入其 ``main()``，
统一收集运行结果（main 返回失败数量，0 表示全部通过）。

运行方式（项目根目录下执行）::

    python test_pkg/run_tests.py                  # 运行全部套件
    python test_pkg/run_tests.py blood             # 只运行指定套件
    python test_pkg/run_tests.py blood node_tracker  # 运行多个套件
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path


# ── 确保项目根目录在 sys.path ──
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TEST_PKG_DIR = Path(__file__).resolve().parent

_GREEN = '\033[32m'
_RED = '\033[31m'
_YELLOW = '\033[33m'
_CYAN = '\033[36m'
_RESET = '\033[0m'
_BOLD = '\033[1m'


def _collect(filter_names: list[str]) -> list[Path]:
    """收集含 tests.py 的子目录，按名称过滤。"""
    suites = sorted(p for p in _TEST_PKG_DIR.iterdir() if p.is_dir() and (p / 'tests.py').exists())
    if filter_names:
        suites = [s for s in suites if s.name in filter_names]
    return suites


def _load_main(suite_dir: Path):
    """动态加载子目录 tests.py 中的 main 函数。"""
    tests_path = suite_dir / 'tests.py'
    mod_name = f'_suite_{suite_dir.name}'
    spec = importlib.util.spec_from_file_location(mod_name, tests_path)
    mod = importlib.util.module_from_spec(spec)
    # 必须在 exec_module 之前注册，否则 Python 3.13 的 @dataclass 会失败
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod.main


def main() -> None:
    filter_names = sys.argv[1:]
    suites = _collect(filter_names)

    if not suites:
        print(f'{_YELLOW}未找到可运行的套件（含 tests.py 的子目录）{_RESET}')
        return

    total_fail = 0
    start = time.perf_counter()

    for suite_dir in suites:
        try:
            suite_main = _load_main(suite_dir)
            fail_count = suite_main()
        except Exception as exc:
            print(f'\n{_BOLD}{_RED}套件 {suite_dir.name} 加载失败: {exc}{_RESET}')
            fail_count = 1

        total_fail += fail_count or 0

    elapsed = time.perf_counter() - start
    print(f'\n{_BOLD}{"═" * 60}{_RESET}')
    summary_color = _GREEN if total_fail == 0 else _RED
    print(f'{_BOLD}{summary_color}全部套件完成  总失败={total_fail}  耗时={elapsed:.2f}s{_RESET}')

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == '__main__':
    main()
