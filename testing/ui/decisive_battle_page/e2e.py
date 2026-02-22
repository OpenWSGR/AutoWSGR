"""决战页面 UI 控制器端到端测试。

运行方式::

    python testing/ui/decisive_battle_page/e2e.py [serial] [--auto] [--debug]

前置条件：
    游戏位于 **决战总览页面** (地图 → 决战面板 → 点击进入)

测试内容：
    1. 验证初始状态
    2. 向前翻一章 (go_prev_chapter)，再向后翻一章还原 (go_next_chapter)
    3. 决战页面 → ◁ 主页面
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from autowsgr.infra import setup_logger
from testing.ui._framework import UIControllerTestRunner, connect_device, ensure_page, info, parse_e2e_args, reset_to_main_page


def run_test(runner: UIControllerTestRunner) -> None:
    from autowsgr.ui.decisive.battle_page import DecisiveBattlePage
    from autowsgr.ui.main_page import MainPage

    db_page = DecisiveBattlePage(runner.ctrl)

    runner.verify_current("初始验证: 决战页面", "决战页面", DecisiveBattlePage.is_current_page)
    if runner.aborted:
        return

    runner.execute_step(
        "决战页面 → ◁ 前一章节",
        "决战页面",
        DecisiveBattlePage.is_current_page,
        lambda: db_page.go_prev_chapter(),
    )
    if runner.aborted:
        return

    runner.execute_step(
        "决战页面 → ▷ 后一章节 (还原)",
        "决战页面",
        DecisiveBattlePage.is_current_page,
        lambda: db_page.go_next_chapter(),
    )
    if runner.aborted:
        return

    runner.execute_step(
        "决战页面 → ◁ 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: db_page.go_back(),
    )


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面导航到决战总览。"""
    import time

    from autowsgr.ui.decisive.battle_page import DecisiveBattlePage
    from autowsgr.ui.main_page import MainPage, MainPageTarget
    from autowsgr.ui.map.page import MapPage
    from autowsgr.ui.map.data import MapPanel

    if not reset_to_main_page(ctrl, pause):
        return
    screen = ctrl.screenshot()
    if MainPage.is_current_page(screen):
        MainPage(ctrl).navigate_to(MainPageTarget.SORTIE)
        time.sleep(pause)
        screen = ctrl.screenshot()
    if MapPage.is_current_page(screen):
        if MapPage.get_active_panel(screen) != MapPanel.DECISIVE:
            MapPage(ctrl).switch_panel(MapPanel.DECISIVE)
            time.sleep(pause)
            screen = ctrl.screenshot()
        MapPage(ctrl).enter_decisive()
        time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        "决战页面 (DecisiveBattlePage) e2e 测试",
        precondition="游戏位于决战总览页面 (地图 → 决战面板 → 点击进入)",
        default_log_dir="logs/e2e/decisive_battle_page",
    )
    setup_logger(log_dir=args.log_dir, level=args.log_level, save_images=True)
    from loguru import logger

    logger.info("=== 决战页面 e2e 测试开始 ===")
    ctrl = connect_device(args.serial)
    from autowsgr.ui.decisive.battle_page import DecisiveBattlePage
    if not ensure_page(
        ctrl, DecisiveBattlePage.is_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        "决战页面",
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name="决战页面",
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
        logger.opt(exception=True).error("决战页面 e2e 测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info("设备已断开")

    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
