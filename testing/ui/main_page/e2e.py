"""主页面 UI 控制器端到端测试。

运行方式::

    # 交互模式 (默认)
    python testing/ui/main_page/e2e.py

    # 自动执行
    python testing/ui/main_page/e2e.py --auto

    # 指定设备
    python testing/ui/main_page/e2e.py emulator-5554 --auto --debug

前置条件：
    游戏位于 **主页面** (母港/秘书舰界面)

测试内容：
    1. 验证初始状态 (主页面识别)
    2. 读取状态 (远征通知、任务通知)
    3. 主页面 → 地图页面 (出征) → ◁ 返回主页面
    4. 主页面 → 任务页面 → ◁ 返回主页面
    5. 主页面 → 侧边栏 → close → 返回主页面
    6. 主页面 → 后院页面 → ◁ 返回主页面
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from autowsgr.infra import setup_logger
from testing.ui._framework import UIControllerTestRunner, connect_device, ensure_page, info, parse_e2e_args, reset_to_main_page


def run_test(runner: UIControllerTestRunner) -> None:
    """执行主页面控制器完整测试序列。"""
    from autowsgr.ui.backyard_page import BackyardPage
    from autowsgr.ui.main_page import MainPage, MainPageTarget
    from autowsgr.ui.map.page import MapPage
    from autowsgr.ui.mission_page import MissionPage
    from autowsgr.ui.sidebar_page import SidebarPage

    main_page = MainPage(runner.ctrl)
    map_page = MapPage(runner.ctrl)
    mission_page = MissionPage(runner.ctrl)
    sidebar_page = SidebarPage(runner.ctrl)
    backyard_page = BackyardPage(runner.ctrl)

    # ───── Step 0: 验证初始状态 ──────────────────────────────────────
    runner.verify_current("初始验证: 主页面", "主页面", MainPage.is_current_page)
    if runner.aborted:
        return

    # ───── Step 1: 读取状态 ──────────────────────────────────────────
    runner.read_state(
        "主页面状态",
        readers={
            "远征通知": lambda s: MainPage.has_expedition_ready(s),
            "任务通知": lambda s: MainPage.has_task_ready(s),
        },
    )

    # ───── Step 2: 主页面 → 地图页面 (出征) ─────────────────────────
    runner.execute_step(
        "主页面 → 地图页面 (出征)",
        "地图页面",
        MapPage.is_current_page,
        lambda: main_page.go_to_sortie(),
    )
    if runner.aborted:
        return

    # ───── Step 3: 地图页面 → ◁ 主页面 ──────────────────────────────
    runner.execute_step(
        "地图页面 → ◁ 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: map_page.go_back(),
    )
    if runner.aborted:
        return

    # ───── Step 4: 主页面 → 任务页面 ─────────────────────────────────
    runner.execute_step(
        "主页面 → 任务页面",
        "任务页面",
        MissionPage.is_current_page,
        lambda: main_page.go_to_task(),
    )
    if runner.aborted:
        return

    # ───── Step 5: 任务页面 → ◁ 主页面 ──────────────────────────────
    runner.execute_step(
        "任务页面 → ◁ 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: mission_page.go_back(),
    )
    if runner.aborted:
        return

    # ───── Step 6: 主页面 → 侧边栏 ───────────────────────────────────
    runner.execute_step(
        "主页面 → 侧边栏",
        "侧边栏",
        SidebarPage.is_current_page,
        lambda: main_page.open_sidebar(),
    )
    if runner.aborted:
        return

    # ───── Step 7: 侧边栏 → close → 主页面 ──────────────────────────
    runner.execute_step(
        "侧边栏 → close → 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: sidebar_page.close(),
    )
    if runner.aborted:
        return

    # ───── Step 8: 主页面 → 后院页面 ─────────────────────────────────
    runner.execute_step(
        "主页面 → 后院页面",
        "后院页面",
        BackyardPage.is_current_page,
        lambda: main_page.go_home(),
    )
    if runner.aborted:
        return

    # ───── Step 9: 后院页面 → ◁ 主页面 ──────────────────────────────
    runner.execute_step(
        "后院页面 → ◁ 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: backyard_page.go_back(),
    )
    if runner.aborted:
        return

    # ───── Step 10: 最终验证 ──────────────────────────────────────────
    runner.verify_current("最终验证: 主页面", "主页面", MainPage.is_current_page)


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面返回主页面。"""
    reset_to_main_page(ctrl, pause)


def main() -> None:
    args = parse_e2e_args(
        "主页面 (MainPage) e2e 测试",
        precondition="游戏位于主页面 (母港/秘书舰界面)",
        default_log_dir="logs/e2e/main_page",
    )
    setup_logger(log_dir=args.log_dir, level=args.log_level, save_images=True)
    from loguru import logger

    logger.info("=== 主页面 e2e 测试开始 ===")
    ctrl = connect_device(args.serial)
    from autowsgr.ui.main_page import MainPage
    if not ensure_page(
        ctrl, MainPage.is_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        "主页面",
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name="主页面",
        log_dir=args.log_dir,
        auto_mode=args.auto,
        pause=args.pause,
    )
    try:
        run_test(runner)
    except KeyboardInterrupt:
        from testing.ui._framework import warn

        warn("用户中断 (Ctrl+C)")
    except Exception as exc:
        from testing.ui._framework import fail

        fail(f"未预期异常: {exc}")
        logger.opt(exception=True).error("主页面 e2e 测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info("设备已断开")

    logger.info("=== 主页面 e2e 测试结束 ===")
    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
