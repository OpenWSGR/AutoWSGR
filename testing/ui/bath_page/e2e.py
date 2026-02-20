"""浴室页面 UI 控制器端到端测试。

运行方式::

    python testing/ui/bath_page/e2e.py [serial] [--auto] [--debug]

前置条件：
    游戏位于 **浴室页面** (后院 → 浴室)

测试内容：
    1. 验证初始状态
    2. 读取页面状态（当前修理槽信息）
    3. 浴室页面 → ◁ 后院
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from autowsgr.infra import setup_logger
from testing.ui._framework import UIControllerTestRunner, connect_device, ensure_page, info, parse_e2e_args, reset_to_main_page


def run_test(runner: UIControllerTestRunner) -> None:
    from autowsgr.ui.backyard_page import BackyardPage
    from autowsgr.ui.bath_page import BathPage

    bath_page = BathPage(runner.ctrl)

    runner.verify_current("初始验证: 浴室页面", "浴室页面", BathPage.is_current_page)
    if runner.aborted:
        return

    runner.read_state(
        "浴室页面",
        readers={"修理中船舰数": lambda s: "（需手动读取）"},
    )

    runner.execute_step(
        "浴室页面 → ◁ 后院",
        "后院",
        BackyardPage.is_current_page,
        lambda: bath_page.go_back(),
    )


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面导航到浴室页面。"""
    import time

    from autowsgr.ui.backyard_page import BackyardPage
    from autowsgr.ui.main_page import MainPage, MainPageTarget

    if not reset_to_main_page(ctrl, pause):
        return
    screen = ctrl.screenshot()
    if MainPage.is_current_page(screen):
        MainPage(ctrl).navigate_to(MainPageTarget.HOME)
        time.sleep(pause)
        screen = ctrl.screenshot()
    if BackyardPage.is_current_page(screen):
        BackyardPage(ctrl).go_to_bath()
        time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        "浴室页面 (BathPage) e2e 测试",
        precondition="游戏位于浴室页面 (后院 → 浴室)",
        default_log_dir="logs/e2e/bath_page",
    )
    setup_logger(log_dir=args.log_dir, level=args.log_level, save_images=True)
    from loguru import logger

    logger.info("=== 浴室页面 e2e 测试开始 ===")
    ctrl = connect_device(args.serial)
    from autowsgr.ui.bath_page import BathPage
    if not ensure_page(
        ctrl, BathPage.is_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        "浴室页面",
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name="浴室页面",
        log_dir=args.log_dir,
        auto_mode=args.auto,
        pause=args.pause,
    )
    try:
        run_test(runner)
    except KeyboardInterrupt:
        from testing.ui._framework import warn

        warn("用户中断")
    except Exception as exc:
        from testing.ui._framework import fail

        fail(f"未预期: {exc}")
        logger.opt(exception=True).error("浴室页面 e2e 测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info("设备已断开")

    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
