"""地图页面 UI 控制器端到端测试。

运行方式::

    python testing/ui/map_page/e2e.py [serial] [--auto] [--debug] [--pause 1.5]

前置条件：
    游戏位于 **地图选择页面** (出征面板)
    （主页面 → 出征）

测试内容：
    1. 验证初始状态 (地图页面, 出征面板)
    2. 读取状态 (远征通知、当前面板)
    3. 面板切换: 出征 → 演习 → 远征 → 战役 → 决战 → 出征
    4. 章节导航: 下一章 → 上一章 (视觉确认)
    5. 地图页面 → ◁ 返回主页面
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from autowsgr.infra import setup_logger
from testing.ui._framework import UIControllerTestRunner, connect_device, ensure_page, info, parse_e2e_args, reset_to_main_page


def run_test(runner: UIControllerTestRunner) -> None:
    """执行地图页面控制器完整测试序列。"""
    from autowsgr.ui.main_page import MainPage
    from autowsgr.ui.map.page import MapPage
    from autowsgr.ui.map.data import MapPanel

    map_page = MapPage(runner.ctrl)

    # ───── Step 0: 验证初始状态 ──────────────────────────────────────
    runner.verify_current("初始验证: 地图页面", "地图页面", MapPage.is_current_page)
    if runner.aborted:
        return

    # ───── Step 1: 读取状态 ──────────────────────────────────────────
    runner.read_state(
        "地图页面状态",
        readers={
            "远征通知": lambda s: MapPage.has_expedition_notification(s),
            "当前面板": lambda s: MapPage.get_active_panel(s),
            "选中章节Y": lambda s: MapPage.find_selected_chapter_y(s),
        },
    )

    # ───── Step 2-6: 面板切换 ─────────────────────────────────────────
    panel_sequence = [
        MapPanel.EXERCISE,
        MapPanel.EXPEDITION,
        MapPanel.BATTLE,
        MapPanel.DECISIVE,
        MapPanel.SORTIE,
    ]
    for panel in panel_sequence:
        runner.execute_step(
            f"面板切换 → {panel.value}",
            "地图页面",
            MapPage.is_current_page,
            lambda p=panel: map_page.switch_panel(p),
        )
        if runner.aborted:
            return

    # ───── Step 7: 章节 → 下一章 ─────────────────────────────────────
    runner.execute_step(
        "章节 → 下一章",
        "地图页面",
        MapPage.is_current_page,
        lambda: map_page.click_next_chapter(),
    )
    if runner.aborted:
        return

    # ───── Step 8: 章节 → 上一章 ─────────────────────────────────────
    runner.execute_step(
        "章节 → 上一章 (恢复)",
        "地图页面",
        MapPage.is_current_page,
        lambda: map_page.click_prev_chapter(),
    )
    if runner.aborted:
        return

    # ───── Step 9: 地图页面 → ◁ 主页面 ──────────────────────────────
    runner.execute_step(
        "地图页面 → ◁ 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: map_page.go_back(),
    )


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面导航到地图页面（出征面板）。"""
    import time

    from autowsgr.ui.main_page import MainPage, MainPageTarget

    if not reset_to_main_page(ctrl, pause):
        return
    screen = ctrl.screenshot()
    if MainPage.is_current_page(screen):
        MainPage(ctrl).navigate_to(MainPageTarget.SORTIE)
        time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        "地图页面 (MapPage) e2e 测试",
        precondition="游戏位于地图选择页面 (出征面板)，从主页面→出征进入",
        default_log_dir="logs/e2e/map_page",
    )
    setup_logger(log_dir=args.log_dir, level=args.log_level, save_images=True)
    from loguru import logger

    logger.info("=== 地图页面 e2e 测试开始 ===")
    ctrl = connect_device(args.serial)
    from autowsgr.ui.map.page import MapPage
    if not ensure_page(
        ctrl, MapPage.is_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        "地图页面",
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name="地图页面",
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
        logger.opt(exception=True).error("地图页面 e2e 测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info("设备已断开")

    logger.info("=== 地图页面 e2e 测试结束 ===")
    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
