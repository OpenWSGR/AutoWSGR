"""UI 页面识别套件：测试各页面 ``is_current_page`` 是否正常工作。

目录结构约定::

    test_pkg/ui/
    ├── tests.py              ← 本文件
    ├── <PageName>/           ← 以页面类名命名的子目录
    │   ├── *.png             ← 正例：期望 is_current_page == True
    │   └── false/            ← 负例子目录（可选）
    │       └── *.png         ← 负例：期望 is_current_page == False

已注册页面（目录名 → 页面类）::

    MainPage               → MainPage.is_current_page
    MapPage                → MapPage.is_current_page
    BattlePreparationPage  → BattlePreparationPage.is_current_page
    SidebarPage            → SidebarPage.is_current_page
    MissionPage            → MissionPage.is_current_page
    BackyardPage           → BackyardPage.is_current_page
    BathPage               → BathPage.is_current_page
    CanteenPage            → CanteenPage.is_current_page
    ChooseShipPage         → ChooseShipPage.is_current_page
    BuildPage              → BuildPage.is_current_page
    IntensifyPage          → IntensifyPage.is_current_page
    FriendPage             → FriendPage.is_current_page
    DecisiveBattlePage     → DecisiveBattlePage.is_current_page
    StartScreenPage        → StartScreenPage.is_current_page

运行方式::

    # 单独运行（项目根目录）
    python test_pkg/ui/tests.py

    # 通过 run_tests.py 运行
    python test_pkg/run_tests.py ui
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import cv2


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np


# ── 确保项目根目录在 sys.path ──────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_SUITE_DIR = Path(__file__).resolve().parent

# ── 颜色常量 ──────────────────────────────────────────────────────────────────
_GREEN = '\033[32m'
_RED = '\033[31m'
_CYAN = '\033[36m'
_YELLOW = '\033[33m'
_RESET = '\033[0m'
_BOLD = '\033[1m'
_PASS = f'{_GREEN}PASS{_RESET}'
_FAIL = f'{_RED}FAIL{_RESET}'
_SKIP = f'{_YELLOW}SKIP{_RESET}'


# ═══════════════════════════════════════════════════════════════════════════════
# 页面注册表  目录名 → is_current_page 函数
# ═══════════════════════════════════════════════════════════════════════════════


def _build_registry() -> dict[str, Callable[[np.ndarray], bool]]:
    """延迟导入以避免在 import 时触发模拟器/OCR 初始化。"""
    from autowsgr.ui import (
        BackyardPage,
        BathPage,
        BattlePreparationPage,
        BuildPage,
        CanteenPage,
        ChooseShipPage,
        DecisiveBattlePage,
        FriendPage,
        IntensifyPage,
        MainPage,
        MissionPage,
        SidebarPage,
    )
    from autowsgr.ui.map.page import MapPage
    from autowsgr.ui.start_screen_page import StartScreenPage

    return {
        'MainPage': MainPage.is_current_page,
        'MapPage': MapPage.is_current_page,
        'BattlePreparationPage': BattlePreparationPage.is_current_page,
        'SidebarPage': SidebarPage.is_current_page,
        'MissionPage': MissionPage.is_current_page,
        'BackyardPage': BackyardPage.is_current_page,
        'BathPage': BathPage.is_current_page,
        'CanteenPage': CanteenPage.is_current_page,
        'ChooseShipPage': ChooseShipPage.is_current_page,
        'BuildPage': BuildPage.is_current_page,
        'IntensifyPage': IntensifyPage.is_current_page,
        'FriendPage': FriendPage.is_current_page,
        'DecisiveBattlePage': DecisiveBattlePage.is_current_page,
        'StartScreenPage': StartScreenPage.is_current_page,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 数据结构  (用 NamedTuple 而非 dataclass，避免动态加载时 sys.modules 查找问题)
# ═══════════════════════════════════════════════════════════════════════════════


class _Case(NamedTuple):
    """单条测试用例。"""

    page_name: str
    img_path: Path
    expected: bool  # True = 期望 is_current_page 返回 True


class _Result(NamedTuple):
    """单条测试结果。"""

    name: str  # 显示名称（含相对路径）
    passed: bool
    reason: str = ''


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _load_screen(path: Path) -> np.ndarray | None:
    """读取图像并转换为 RGB ndarray，失败返回 None。"""
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _collect_cases() -> list[_Case]:
    """扫描 _SUITE_DIR 下的子目录，收集全部测试用例。

    规则：
    - ``<PageName>/*.png``       → expected=True
    - ``<PageName>/false/*.png`` → expected=False
    """
    cases: list[_Case] = []

    registry_keys = set(_build_registry().keys())

    for page_dir in sorted(_SUITE_DIR.iterdir()):
        if not page_dir.is_dir():
            continue
        if page_dir.name not in registry_keys:
            continue

        page_name = page_dir.name

        # 正例：直接在 <PageName>/ 下的 png
        for img in sorted(page_dir.glob('*.png')):
            cases.append(_Case(page_name=page_name, img_path=img, expected=True))

        # 负例：<PageName>/false/ 子目录下的 png
        false_dir = page_dir / 'false'
        if false_dir.is_dir():
            for img in sorted(false_dir.glob('*.png')):
                cases.append(_Case(page_name=page_name, img_path=img, expected=False))

    return cases


def _run_case(
    case: _Case,
    registry: dict[str, Callable[[np.ndarray], bool]],
) -> _Result:
    """执行单条用例，返回结果。"""
    rel = case.img_path.relative_to(_SUITE_DIR)
    display = str(rel)

    screen = _load_screen(case.img_path)
    if screen is None:
        return _Result(display, False, f'无法加载图像: {case.img_path}')

    checker = registry[case.page_name]

    try:
        result = checker(screen)
    except Exception as exc:
        return _Result(display, False, f'异常: {exc}')

    if result == case.expected:
        expected_str = 'True' if case.expected else 'False'
        return _Result(display, True, f'is_current_page={expected_str} OK')
    else:
        return _Result(
            display,
            False,
            f'期望={case.expected}, 实际={result}',
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> int:
    """运行 UI 页面识别测试套件，返回失败数量。"""
    # ── 开启 pixel_checker 详细日志（通过通道级别控制） ────────────────
    from autowsgr.infra.logger import setup_logger

    setup_logger(level='DEBUG', channels={'vision.pixel': 'TRACE'})

    print(f'\n{_BOLD}{_CYAN}{"─" * 60}{_RESET}')
    print(f'{_BOLD}套件: ui  (页面 is_current_page 识别){_RESET}')
    print(f'{"─" * 60}{_RESET}')

    registry = _build_registry()
    cases = _collect_cases()

    if not cases:
        print(
            f'\n{_YELLOW}未找到任何测试图像。\n'
            f'请在 test_pkg/ui/<PageName>/ 下放置截图 (*.png)。\n'
            f'已注册页面: {", ".join(sorted(registry.keys()))}{_RESET}\n'
        )
        return 0

    # 按页面分组打印
    current_page = None
    pass_count = fail_count = 0
    start = time.perf_counter()

    for case in cases:
        if case.page_name != current_page:
            current_page = case.page_name
            print(f'\n  {_BOLD}{_CYAN}[ {current_page} ]{_RESET}')

        t0 = time.perf_counter()
        r = _run_case(case, registry)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        status = _PASS if r.passed else _FAIL
        print(f'    {status}  {r.name:<50}  {r.reason}  [{elapsed_ms:.1f}ms]')
        if r.passed:
            pass_count += 1
        else:
            fail_count += 1

    elapsed = time.perf_counter() - start
    total = pass_count + fail_count
    summary_color = _GREEN if fail_count == 0 else _RED
    print(
        f'\n{_BOLD}{summary_color}'
        f'  ui: {pass_count}/{total} 通过  失败={fail_count}  耗时={elapsed:.2f}s'
        f'{_RESET}\n'
    )
    return fail_count


if __name__ == '__main__':
    sys.exit(0 if main() == 0 else 1)
