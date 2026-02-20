"""好友页面 UI 控制器端到端测试。

运行方式::

    python testing/ui/friend_page/e2e.py [serial] [--auto] [--debug]

前置条件：
    游戏位于 **好友页面** (侧边栏 → 好友)

测试内容：
    1. 验证初始状态
    2. 好友页面 → ◁ 侧边栏
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from autowsgr.infra import setup_logger
from testing.ui._framework import UIControllerTestRunner, connect_device, ensure_page, info, parse_e2e_args, reset_to_main_page


def run_test(runner: UIControllerTestRunner) -> None:
    from autowsgr.ui.friend_page import FriendPage
    from autowsgr.ui.sidebar_page import SidebarPage

    friend_page = FriendPage(runner.ctrl)

    runner.verify_current("初始验证: 好友页面", "好友页面", FriendPage.is_current_page)
    if runner.aborted:
        return

    runner.execute_step(
        "好友页面 → ◁ 侧边栏",
        "侧边栏",
        SidebarPage.is_current_page,
        lambda: friend_page.go_back(),
    )


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面导航到好友页面。"""
    import time

    from autowsgr.ui.main_page import MainPage, MainPageTarget
    from autowsgr.ui.sidebar_page import SidebarPage

    if not reset_to_main_page(ctrl, pause):
        return
    screen = ctrl.screenshot()
    if MainPage.is_current_page(screen):
        MainPage(ctrl).navigate_to(MainPageTarget.SIDEBAR)
        time.sleep(pause)
        screen = ctrl.screenshot()
    if SidebarPage.is_current_page(screen):
        SidebarPage(ctrl).go_to_friend()
        time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        "好友页面 (FriendPage) e2e 测试",
        precondition="游戏位于好友页面 (侧边栏 → 好友)",
        default_log_dir="logs/e2e/friend_page",
    )
    setup_logger(log_dir=args.log_dir, level=args.log_level, save_images=True)
    from loguru import logger

    logger.info("=== 好友页面 e2e 测试开始 ===")
    ctrl = connect_device(args.serial)
    from autowsgr.ui.friend_page import FriendPage
    if not ensure_page(
        ctrl, FriendPage.is_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        "好友页面",
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name="好友页面",
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
        logger.opt(exception=True).error("好友页面 e2e 测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info("设备已断开")

    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
