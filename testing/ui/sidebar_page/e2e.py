"""侧边栏页面 UI 控制器端到端测试。

运行方式::

    python testing/ui/sidebar_page/e2e.py [serial] [--auto] [--debug]

前置条件：
    游戏位于 **侧边栏** (主页面 → ≡ 菜单)

测试内容：
    1. 验证初始状态 (侧边栏识别)
    2. 侧边栏 → 建造页面 (4 标签切换) → ◁ 侧边栏
    3. 侧边栏 → 强化页面 (3 标签切换) → ◁ 侧边栏
    4. 侧边栏 → 好友页面 → ◁ 侧边栏
    5. 侧边栏 → close → 主页面
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from autowsgr.infra import setup_logger
from testing.ui._framework import UIControllerTestRunner, connect_device, ensure_page, info, parse_e2e_args, reset_to_main_page


def run_test(runner: UIControllerTestRunner) -> None:
    from autowsgr.ui.build_page import BuildPage, BuildTab
    from autowsgr.ui.friend_page import FriendPage
    from autowsgr.ui.intensify_page import IntensifyPage, IntensifyTab
    from autowsgr.ui.main_page import MainPage
    from autowsgr.ui.sidebar_page import SidebarPage, SidebarTarget

    sidebar_page = SidebarPage(runner.ctrl)
    build_page = BuildPage(runner.ctrl)
    intensify_page = IntensifyPage(runner.ctrl)
    friend_page = FriendPage(runner.ctrl)

    # Step 0: 验证初始
    runner.verify_current("初始验证: 侧边栏", "侧边栏", SidebarPage.is_current_page)
    if runner.aborted:
        return

    # Step 1: 侧边栏 → 建造
    runner.execute_step(
        "侧边栏 → 建造页面",
        "建造页面",
        BuildPage.is_current_page,
        lambda: sidebar_page.navigate_to(SidebarTarget.BUILD),
    )
    if runner.aborted:
        return

    # Step 2-4: 建造页面内标签切换
    for tab in [BuildTab.DESTROY, BuildTab.DEVELOP, BuildTab.DISCARD, BuildTab.BUILD]:
        runner.execute_step(
            f"建造: 切换标签 → {tab.value}",
            "建造页面",
            BuildPage.is_current_page,
            lambda t=tab: build_page.switch_tab(t),
        )
        if runner.aborted:
            return

    # Step 5: 建造 → ◁ 侧边栏
    runner.execute_step(
        "建造页面 → ◁ 侧边栏",
        "侧边栏",
        SidebarPage.is_current_page,
        lambda: build_page.go_back(),
    )
    if runner.aborted:
        return

    # Step 6: 侧边栏 → 强化
    runner.execute_step(
        "侧边栏 → 强化页面",
        "强化页面",
        IntensifyPage.is_current_page,
        lambda: sidebar_page.navigate_to(SidebarTarget.INTENSIFY),
    )
    if runner.aborted:
        return

    # Step 7-8: 强化页面内标签切换
    for tab in [IntensifyTab.REMAKE, IntensifyTab.SKILL, IntensifyTab.INTENSIFY]:
        runner.execute_step(
            f"强化: 切换标签 → {tab.value}",
            "强化页面",
            IntensifyPage.is_current_page,
            lambda t=tab: intensify_page.switch_tab(t),
        )
        if runner.aborted:
            return

    # Step 9: 强化 → ◁ 侧边栏
    runner.execute_step(
        "强化页面 → ◁ 侧边栏",
        "侧边栏",
        SidebarPage.is_current_page,
        lambda: intensify_page.go_back(),
    )
    if runner.aborted:
        return

    # Step 10: 侧边栏 → 好友
    runner.execute_step(
        "侧边栏 → 好友页面",
        "好友页面",
        FriendPage.is_current_page,
        lambda: sidebar_page.navigate_to(SidebarTarget.FRIEND),
    )
    if runner.aborted:
        return

    # Step 11: 好友 → ◁ 侧边栏
    runner.execute_step(
        "好友页面 → ◁ 侧边栏",
        "侧边栏",
        SidebarPage.is_current_page,
        lambda: friend_page.go_back(),
    )
    if runner.aborted:
        return

    # Step 12: 侧边栏 → close → 主页面
    runner.execute_step(
        "侧边栏 → close → 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: sidebar_page.close(),
    )


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面导航到侧边栏。"""
    import time

    from autowsgr.ui.main_page import MainPage, MainPageTarget

    if not reset_to_main_page(ctrl, pause):
        return
    screen = ctrl.screenshot()
    if MainPage.is_current_page(screen):
        MainPage(ctrl).navigate_to(MainPageTarget.SIDEBAR)
        time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        "侧边栏 (SidebarPage) e2e 测试",
        precondition="游戏位于侧边栏 (主页面 → ≡)",
        default_log_dir="logs/e2e/sidebar_page",
    )
    setup_logger(log_dir=args.log_dir, level=args.log_level, save_images=True)
    from loguru import logger

    logger.info("=== 侧边栏 e2e 测试开始 ===")
    ctrl = connect_device(args.serial)
    from autowsgr.ui.sidebar_page import SidebarPage
    if not ensure_page(
        ctrl, SidebarPage.is_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        "侧边栏",
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name="侧边栏",
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

        fail(f"未预期异常: {exc}")
        logger.opt(exception=True).error("侧边栏 e2e 测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info("设备已断开")

    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
