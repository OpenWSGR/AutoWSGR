"""后院页面 UI 控制器端到端测试。

运行方式::

    python testing/ui/backyard_page/e2e.py [serial] [--auto] [--debug]

前置条件：
    游戏位于 **后院页面** (主页面 → 🏛 主页图标)

测试内容：
    1. 验证初始状态 (后院页面识别)
    2. 后院 → 浴室 → ◁ 后院
    3. 后院 → 食堂 → ◁ 后院
    4. 后院 → ◁ 主页面
"""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from testing.ui._framework import (
    UIControllerTestRunner,
    connect_via_launcher,
    ensure_page,
    info,
    parse_e2e_args,
    reset_to_main_page,
)


def run_test(runner: UIControllerTestRunner) -> None:
    from autowsgr.ui.backyard_page import BackyardPage
    from autowsgr.ui.bath_page import BathPage
    from autowsgr.ui.canteen_page import CanteenPage
    from autowsgr.ui.main_page import MainPage

    backyard_page = BackyardPage(runner.ctrl)
    bath_page = BathPage(runner.ctrl)
    canteen_page = CanteenPage(runner.ctrl)

    # Step 0: 验证初始
    runner.verify_current('初始验证: 后院页面', '后院页面', BackyardPage.is_current_page)
    if runner.aborted:
        return

    # Step 1: 后院 → 浴室
    runner.execute_step(
        '后院 → 浴室页面',
        '浴室页面',
        BathPage.is_current_page,
        lambda: backyard_page.go_to_bath(),
    )
    if runner.aborted:
        return

    # Step 2: 浴室 → ◁ 后院
    runner.execute_step(
        '浴室 → ◁ 后院页面',
        '后院页面',
        BackyardPage.is_current_page,
        lambda: bath_page.go_back(),
    )
    if runner.aborted:
        return

    # Step 3: 后院 → 食堂
    runner.execute_step(
        '后院 → 食堂页面',
        '食堂页面',
        CanteenPage.is_current_page,
        lambda: backyard_page.go_to_canteen(),
    )
    if runner.aborted:
        return

    # Step 4: 食堂 → ◁ 后院
    runner.execute_step(
        '食堂 → ◁ 后院页面',
        '后院页面',
        BackyardPage.is_current_page,
        lambda: canteen_page.go_back(),
    )
    if runner.aborted:
        return

    # Step 5: 后院 → ◁ 主页面
    runner.execute_step(
        '后院 → ◁ 主页面',
        '主页面',
        MainPage.is_current_page,
        lambda: backyard_page.go_back(),
    )


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面导航到后院页面。"""
    import time

    from autowsgr.ui.main_page import MainPage

    if not reset_to_main_page(ctrl, pause):
        return
    screen = ctrl.screenshot()
    if MainPage.is_current_page(screen):
        MainPage(ctrl).navigate_to(MainPage.Target.HOME)
        time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        '后院页面 (BackyardPage) e2e 测试',
        precondition='游戏位于后院页面 (主页面 → 🏛)',
        default_log_dir='logs/e2e/backyard_page',
    )
    ctrl = connect_via_launcher(args.serial, args.log_dir, args.log_level)
    from loguru import logger

    logger.info('=== 后院页面 e2e 测试开始 ===')
    from autowsgr.ui.backyard_page import BackyardPage

    if not ensure_page(
        ctrl,
        BackyardPage.is_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        '后院页面',
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name='后院页面',
        log_dir=args.log_dir,
        auto_mode=args.auto,
        pause=args.pause,
    )
    try:
        run_test(runner)
    except KeyboardInterrupt:
        from testing.ui._framework import warn

        warn('用户中断')
    except Exception as exc:
        from testing.ui._framework import fail

        fail(f'未预期异常: {exc}')
        logger.opt(exception=True).error('后院页面 e2e 测试异常')
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info('设备已断开')

    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == '__main__':
    main()
