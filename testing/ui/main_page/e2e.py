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

    A. 页面识别与状态
        1. 验证初始状态 (is_current_page + is_base_page)
        2. 浮层检测 — 检测并消除可能的浮层 (NEWS / SIGN / BOOKING)
        3. 状态查询 — 远征完成通知、任务可领取通知红点

    B. 标准导航 (四个方向 + 返回)
        4. 主页面 → 地图页面 (出征) → ◁ 返回主页面
        5. 主页面 → 任务页面 → ◁ 返回主页面
        6. 主页面 → 侧边栏 → close → 返回主页面
        7. 主页面 → 后院页面 → ◁ 返回主页面

    C. 活动导航 (模板匹配 + 重试)
        8. 主页面 → 活动地图 → ◁ 返回主页面

    D. 便捷方法
        9. go_to_sortie() → ◁ 返回主页面
       10. 最终主页面验证
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
    ok,
    parse_e2e_args,
    reset_to_main_page,
    warn,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 测试序列
# ═══════════════════════════════════════════════════════════════════════════════


def run_test(runner: UIControllerTestRunner) -> None:
    """执行主页面控制器完整测试序列。"""
    from autowsgr.ui.backyard_page import BackyardPage
    from autowsgr.ui.main_page import MainPage
    from autowsgr.ui.map.page import MapPage
    from autowsgr.ui.mission_page import MissionPage
    from autowsgr.ui.sidebar_page import SidebarPage

    main_page = MainPage(runner.ctrl)
    map_page = MapPage(runner.ctrl)
    mission_page = MissionPage(runner.ctrl)
    sidebar_page = SidebarPage(runner.ctrl)
    backyard_page = BackyardPage(runner.ctrl)

    # ═══════════════════════════════════════════════════════════════════════
    # A. 页面识别与状态
    # ═══════════════════════════════════════════════════════════════════════

    # ───── Step 1: is_current_page 验证 ──────────────────────────────
    runner.verify_current(
        '初始验证: 主页面 (is_current_page)',
        '主页面',
        MainPage.is_current_page,
    )
    if runner.aborted:
        return

    # ───── Step 2: is_base_page + 浮层检测与消除 ─────────────────────
    screen = runner.ctrl.screenshot()
    is_base = MainPage.is_base_page(screen)
    overlay = MainPage.detect_overlay(screen)

    if overlay is not None:
        info(f'检测到浮层: {overlay.value} — 尝试消除')
        runner.execute_step(
            f'浮层消除: {overlay.value}',
            '主页面',
            MainPage.is_base_page,
            lambda: main_page.dismiss_current_overlay(),
        )
        if runner.aborted:
            return
    else:
        if is_base:
            ok('主页面基础状态确认 (无浮层)')
        else:
            warn('is_current_page 通过但 is_base_page 为 False — 可能存在未识别浮层')

    # ───── Step 3: 状态查询 (远征/任务通知红点) ──────────────────────
    runner.read_state(
        '主页面状态',
        readers={
            '远征完成通知': lambda s: MainPage.has_expedition_ready(s),
            '任务可领取通知': lambda s: MainPage.has_task_ready(s),
        },
    )

    # ═══════════════════════════════════════════════════════════════════════
    # B. 标准导航 (四个方向 + 返回)
    # ═══════════════════════════════════════════════════════════════════════

    # ───── Step 4: 主页面 → 地图页面 (出征) ─────────────────────────
    runner.execute_step(
        '主页面 → 地图页面 (navigate_to SORTIE)',
        '地图页面',
        MapPage.is_current_page,
        lambda: main_page.navigate_to(MainPage.Target.SORTIE),
    )
    if runner.aborted:
        return

    runner.execute_step(
        '地图页面 → ◁ 主页面',
        '主页面',
        MainPage.is_current_page,
        lambda: map_page.go_back(),
    )
    if runner.aborted:
        return

    # ───── Step 5: 主页面 → 任务页面 ────────────────────────────────
    runner.execute_step(
        '主页面 → 任务页面 (navigate_to TASK)',
        '任务页面',
        MissionPage.is_current_page,
        lambda: main_page.navigate_to(MainPage.Target.TASK),
    )
    if runner.aborted:
        return

    runner.execute_step(
        '任务页面 → ◁ 主页面',
        '主页面',
        MainPage.is_current_page,
        lambda: mission_page.go_back(),
    )
    if runner.aborted:
        return

    # ───── Step 6: 主页面 → 侧边栏 ──────────────────────────────────
    runner.execute_step(
        '主页面 → 侧边栏 (navigate_to SIDEBAR)',
        '侧边栏',
        SidebarPage.is_current_page,
        lambda: main_page.navigate_to(MainPage.Target.SIDEBAR),
    )
    if runner.aborted:
        return

    runner.execute_step(
        '侧边栏 → close → 主页面',
        '主页面',
        MainPage.is_current_page,
        lambda: sidebar_page.close(),
    )
    if runner.aborted:
        return

    # ───── Step 7: 主页面 → 后院页面 ────────────────────────────────
    runner.execute_step(
        '主页面 → 后院页面 (navigate_to HOME)',
        '后院页面',
        BackyardPage.is_current_page,
        lambda: main_page.navigate_to(MainPage.Target.HOME),
    )
    if runner.aborted:
        return

    runner.execute_step(
        '后院页面 → ◁ 主页面',
        '主页面',
        MainPage.is_current_page,
        lambda: backyard_page.go_back(),
    )
    if runner.aborted:
        return

    # ═══════════════════════════════════════════════════════════════════════
    # C. 活动导航 (模板匹配 + 重试流程)
    # ═══════════════════════════════════════════════════════════════════════

    # ───── Step 8: 主页面 → 活动地图 ────────────────────────────────
    try:
        from autowsgr.ui.event.event_page import BaseEventPage

        runner.execute_step(
            '主页面 → 活动地图 (navigate_to EVENT, 模板匹配)',
            '活动地图页面',
            BaseEventPage.is_current_page,
            lambda: main_page.navigate_to(MainPage.Target.EVENT),
        )
    except Exception as exc:
        warn(f'活动导航测试跳过 (可能当前无活动入口): {exc}')

    if runner.aborted:
        return

    # ───── Step 8b: 活动地图 → ◁ 主页面 ─────────────────────────────
    screen = runner.ctrl.screenshot()
    try:
        from autowsgr.ui.event.event_page import BaseEventPage

        if BaseEventPage.is_current_page(screen):
            event_page = BaseEventPage(runner.ctrl)
            runner.execute_step(
                '活动地图 → ◁ 主页面',
                '主页面',
                MainPage.is_current_page,
                lambda: event_page.go_back(),
            )
        else:
            info('未在活动地图页面，跳过返回步骤')
    except Exception:
        pass

    if runner.aborted:
        return

    # ═══════════════════════════════════════════════════════════════════════
    # D. 便捷方法验证
    # ═══════════════════════════════════════════════════════════════════════

    # ───── Step 9: go_to_sortie() ────────────────────────────────────
    runner.execute_step(
        '便捷方法 go_to_sortie()',
        '地图页面',
        MapPage.is_current_page,
        lambda: main_page.go_to_sortie(),
    )
    if runner.aborted:
        return

    runner.execute_step(
        '地图页面 → ◁ 主页面 (收尾)',
        '主页面',
        MainPage.is_current_page,
        lambda: map_page.go_back(),
    )
    if runner.aborted:
        return

    # ───── Step 10: 最终验证 ─────────────────────────────────────────
    runner.verify_current('最终验证: 主页面', '主页面', MainPage.is_current_page)


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面返回主页面。"""
    reset_to_main_page(ctrl, pause)


def main() -> None:
    args = parse_e2e_args(
        '主页面 (MainPage) e2e 测试',
        precondition='游戏位于主页面 (母港/秘书舰界面)',
        default_log_dir='logs/e2e/main_page',
    )
    ctrl = connect_via_launcher(args.serial, args.log_dir, args.log_level)
    from loguru import logger

    logger.info('=== 主页面 e2e 测试开始 ===')

    from autowsgr.ui.main_page import MainPage

    if not ensure_page(
        ctrl,
        MainPage.is_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        '主页面',
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)

    runner = UIControllerTestRunner(
        ctrl,
        controller_name='主页面',
        log_dir=args.log_dir,
        auto_mode=args.auto,
        pause=args.pause,
    )
    try:
        run_test(runner)
    except KeyboardInterrupt:
        warn('用户中断 (Ctrl+C)')
    except Exception as exc:
        from testing.ui._framework import fail

        fail(f'未预期异常: {exc}')
        logger.opt(exception=True).error('主页面 e2e 测试异常')
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info('设备已断开')

    logger.info('=== 主页面 e2e 测试结束 ===')
    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == '__main__':
    main()
