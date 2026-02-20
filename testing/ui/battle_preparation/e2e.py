"""出征准备页面 UI 控制器端到端测试。

运行方式::

    python testing/ui/battle_preparation/e2e.py [serial] [--auto] [--debug]

前置条件：
    游戏位于 **出征准备页面** (地图 → 普通关卡 → 选择关卡后进入)

测试内容：
    1. 验证初始状态（当前舰队、当前面板、自动补给）
    2. 依次切换舰队: 1 → 2 → 3 → 4 → 1
    3. 依次切换底部面板: QUICK_SUPPLY → QUICK_REPAIR → EQUIPMENT → STATS
    4. 拨动「自动补给」两次（开 → 关，或 关 → 开 → 关）
    5. 出征准备页面 → ◁ 地图/上级页面
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from autowsgr.infra import setup_logger
from testing.ui._framework import UIControllerTestRunner, connect_device, ensure_page, info, parse_e2e_args, reset_to_main_page


def run_test(runner: UIControllerTestRunner) -> None:
    from autowsgr.ui.battle.preparation import BattlePreparationPage, Panel

    bp_page = BattlePreparationPage(runner.ctrl)

    runner.verify_current("初始验证: 出征准备页面", "出征准备页面", BattlePreparationPage.is_current_page)
    if runner.aborted:
        return

    runner.read_state(
        "出征准备页面",
        readers={
            "当前舰队": lambda s: BattlePreparationPage.get_selected_fleet(s),
            "当前面板": lambda s: BattlePreparationPage.get_active_panel(s),
            "自动补给": lambda s: BattlePreparationPage.is_auto_supply_enabled(s),
        },
    )

    # 舰队切换
    for fleet_id in [2, 3, 4, 1]:
        runner.execute_step(
            f"切换舰队 → 第{fleet_id}舰队",
            "出征准备页面",
            BattlePreparationPage.is_current_page,
            lambda fid=fleet_id: bp_page.select_fleet(fid),
        )
        if runner.aborted:
            return

    # 面板切换
    for panel in [Panel.QUICK_SUPPLY, Panel.QUICK_REPAIR, Panel.EQUIPMENT, Panel.STATS]:
        runner.execute_step(
            f"切换面板 → {panel.value}",
            "出征准备页面",
            BattlePreparationPage.is_current_page,
            lambda p=panel: bp_page.select_panel(p),
        )
        if runner.aborted:
            return

    # 自动补给拨动两次
    for i in range(1, 3):
        runner.execute_step(
            f"拨动自动补给 (第{i}次)",
            "出征准备页面",
            BattlePreparationPage.is_current_page,
            lambda: bp_page.toggle_auto_supply(),
        )
        if runner.aborted:
            return

    runner.execute_step(
        "出征准备页面 → ◁ 返回",
        None,  # 返回目标页面因地图层级不同而变化，跳过严格验证
        lambda _: True,
        lambda: bp_page.go_back(),
    )


def _parse_extra_args() -> tuple[int, int]:
    """从 sys.argv 读取 --chapter 和 --map-node，缺省均为 1。"""
    chapter, map_node = 1, 1
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--chapter" and i + 1 < len(args):
            chapter = int(args[i + 1])
            i += 2
        elif args[i] == "--map-node" and i + 1 < len(args):
            map_node = int(args[i + 1])
            i += 2
        else:
            i += 1
    return chapter, map_node


def _navigate_to(ctrl, pause: float, *, chapter: int = 1, map_node: int = 1) -> None:
    """从任意已知页面导航到出征准备页面。

    流程: reset → 主页面 → 地图（出征面板） → 章节导航 → 点击地图节点 → 再次点击确认进入
    """
    import time

    from autowsgr.ui.main_page import MainPage, MainPageTarget
    from autowsgr.ui.map.data import TOTAL_CHAPTERS
    from autowsgr.ui.map.page import MapPage
    from autowsgr.ui.map.data import MapPanel, MAP_NODE_POSITIONS

    if not reset_to_main_page(ctrl, pause):
        return

    # 主页面 → 地图
    screen = ctrl.screenshot()
    if not MainPage.is_current_page(screen):
        return
    MainPage(ctrl).navigate_to(MainPageTarget.SORTIE)
    time.sleep(pause)

    # 确认在地图并切换到出征面板
    screen = ctrl.screenshot()
    if not MapPage.is_current_page(screen):
        return
    if MapPage.get_active_panel(screen) != MapPanel.SORTIE:
        MapPage(ctrl).switch_panel(MapPanel.SORTIE)
        time.sleep(pause)

    # 章节导航 (无 OCR)。先向前滑到第 1 章，再向后到目标章
    map_page = MapPage(ctrl)
    for _ in range(TOTAL_CHAPTERS):
        if not map_page.click_prev_chapter():
            break
        time.sleep(pause * 0.4)
    for _ in range(chapter - 1):
        map_page.click_next_chapter()
        time.sleep(pause * 0.4)
    time.sleep(pause * 0.5)

    # 点击地图节点（两次：第一次选中，第二次确认进入）
    if map_node not in MAP_NODE_POSITIONS:
        info(f"[battle_preparation] map_node={map_node} 不在已知坐标表，尝试节点 1")
        map_node = 1
    pos = MAP_NODE_POSITIONS[map_node]
    ctrl.click(*pos)
    time.sleep(pause * 0.5)
    ctrl.click(*pos)
    time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        "出征准备页面 (BattlePreparationPage) e2e 测试",
        precondition="游戏位于出征准备页面 (地图 → 普通关卡 → 选择关卡)",
        default_log_dir="logs/e2e/battle_preparation",
    )
    chapter, map_node = _parse_extra_args()
    setup_logger(log_dir=args.log_dir, level=args.log_level, save_images=True)
    from loguru import logger

    logger.info("=== 出征准备页面 e2e 测试开始 === 章节={} 地图节点={}", chapter, map_node)
    info(f"  章节: {chapter}   地图节点: {map_node}  (可用 --chapter N --map-node M 覆盖)")
    ctrl = connect_device(args.serial)
    from autowsgr.ui.battle.preparation import BattlePreparationPage
    if not ensure_page(
        ctrl, BattlePreparationPage.is_current_page,
        lambda: _navigate_to(ctrl, args.pause, chapter=chapter, map_node=map_node),
        "出征准备页面",
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name="出征准备页面",
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
        logger.opt(exception=True).error("出征准备页面 e2e 测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info("设备已断开")

    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
