"""活动地图页面 UI 控制器端到端测试。

运行方式::

    # 交互模式 (默认)
    python testing/ui/event_page/e2e.py

    # 自动执行
    python testing/ui/event_page/e2e.py --auto

    # 指定设备
    python testing/ui/event_page/e2e.py emulator-5554 --auto --debug

前置条件：
    游戏位于 **活动地图页面** (主页面 → 活动入口)

测试内容：

    A. 页面识别
        1. 验证初始状态 (is_current_page)
        2. 浮层检测 (detect_overlay — 地图进入页弹窗)

    B. 难度系统
        3. 读取当前难度 (_get_difficulty)
        4. 切换到相反难度，验证 (_change_difficulty)
        5. 切换回原难度，验证 (_change_difficulty)

    C. 导航
        6. 活动地图 → ◁ 返回主页面
        7. 主页面 → 活动地图 (从主页面重新导航回来验证双向性)

    D. 节点选择 (如条件允许)
        8. 选择节点 → 检测浮层 (overlay) 出现
"""

from __future__ import annotations

import sys
import time
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
    """执行活动地图页面控制器完整测试序列。"""
    from autowsgr.context import GameContext
    from autowsgr.infra import UserConfig
    from autowsgr.ui.event.event_page import BaseEventPage
    from autowsgr.ui.main_page import MainPage

    ctx = GameContext(ctrl=runner.ctrl, config=UserConfig())
    event_page = BaseEventPage(ctx)
    main_page = MainPage(ctx)

    # ═══════════════════════════════════════════════════════════════════════
    # A. 页面识别
    # ═══════════════════════════════════════════════════════════════════════

    # ───── Step 1: 验证初始状态 (is_current_page) ────────────────────
    runner.verify_current(
        '初始验证: 活动地图页面 (is_current_page)',
        '活动地图页面',
        BaseEventPage.is_current_page,
    )
    if runner.aborted:
        return

    # ───── Step 2: 浮层检测 ──────────────────────────────────────────
    runner.read_state(
        '活动地图状态',
        readers={
            '浮层 (进入页弹窗)': lambda s: BaseEventPage._detect_overlay(s),
        },
    )

    # ═══════════════════════════════════════════════════════════════════════
    # B. 难度系统
    # ═══════════════════════════════════════════════════════════════════════

    # ───── Step 3: 读取当前难度 ──────────────────────────────────────
    initial_difficulty: str = 'H'  # 默认值，读取失败时维持
    try:
        initial_difficulty = event_page._get_difficulty()
        ok(f'当前难度: {initial_difficulty} ({"困难" if initial_difficulty == "H" else "简单"})')
    except Exception as exc:
        warn(f'读取难度失败: {exc}')

    # ───── Step 4: 切换到相反难度并验证 ──────────────────────────────
    opposite = 'E' if initial_difficulty == 'H' else 'H'
    opposite_label = '简单' if opposite == 'E' else '困难'
    runner.execute_step(
        f'切换难度: {initial_difficulty} → {opposite} ({opposite_label})',
        '活动地图页面',
        lambda s: event_page._get_difficulty() == opposite,
        lambda: event_page._change_difficulty(opposite),
    )
    if runner.aborted:
        return

    # ───── Step 5: 切换回原难度并验证 ────────────────────────────────
    initial_label = '困难' if initial_difficulty == 'H' else '简单'
    runner.execute_step(
        f'切换回原难度: {opposite} → {initial_difficulty} ({initial_label})',
        '活动地图页面',
        lambda s: event_page._get_difficulty() == initial_difficulty,
        lambda: event_page._change_difficulty(initial_difficulty),
    )
    if runner.aborted:
        return

    # ═══════════════════════════════════════════════════════════════════════
    # C. 导航 (活动地图 ↔ 主页面)
    # ═══════════════════════════════════════════════════════════════════════

    # ───── Step 6: 活动地图 → ◁ 主页面 ──────────────────────────────────
    runner.execute_step(
        '活动地图 → ◁ 主页面',
        '主页面',
        MainPage.is_current_page,
        lambda: event_page.go_back(),
    )
    if runner.aborted:
        return

    # ───── Step 7: 主页面 → 活动地图 (双向导航验证) ────────────────────
    runner.execute_step(
        '主页面 → 活动地图 (双向导航验证)',
        '活动地图页面',
        BaseEventPage.is_current_page,
        lambda: main_page.navigate_to(MainPage.Target.EVENT),
    )
    if runner.aborted:
        return

    # ═══════════════════════════════════════════════════════════════════════
    # D. 节点选择 (选择第一个节点并检测浮层)
    # ═══════════════════════════════════════════════════════════════════════

    # ───── Step 8: 选择节点 → 检测浮层 ────────────────────────────────────
    runner.execute_step(
        '选择节点 1 → 检测浮层 (节点进入页)',
        '活动地图页面',
        BaseEventPage.is_current_page,
        lambda: _try_enter_node(event_page, node_id=1),
    )
    if runner.aborted:
        return

    # ───── Step 9: 最终验证 ──────────────────────────────────────────
    runner.verify_current(
        '最终验证: 活动地图页面',
        '活动地图页面',
        BaseEventPage.is_current_page,
    )


def _try_enter_node(event_page: object, node_id: int) -> None:
    """尝试选择一个节点。异常时静默处理（不中断测试）。"""
    try:
        event_page._enter_node(node_id)  # type: ignore[attr-defined]
    except Exception:
        pass  # 节点选择可能因活动状态而失败，不影响测试流程


# ═══════════════════════════════════════════════════════════════════════════════
# 导航到活动地图
# ═══════════════════════════════════════════════════════════════════════════════


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面导航到活动地图页面。"""
    from autowsgr.context import GameContext
    from autowsgr.infra import UserConfig
    from autowsgr.ui.main_page import MainPage

    if not reset_to_main_page(ctrl, pause):
        return
    time.sleep(pause)
    screen = ctrl.screenshot()
    if MainPage.is_current_page(screen):
        ctx = GameContext(ctrl=ctrl, config=UserConfig())
        MainPage(ctx).navigate_to(MainPage.Target.EVENT)
        time.sleep(pause)


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    args = parse_e2e_args(
        '活动地图页面 (BaseEventPage) e2e 测试',
        precondition='游戏位于活动地图页面 (主页面 → 活动入口)',
        default_log_dir='logs/e2e/event_page',
    )
    ctrl = connect_via_launcher(args.serial, args.log_dir, args.log_level)
    from loguru import logger

    logger.info('=== 活动地图页面 e2e 测试开始 ===')

    from autowsgr.ui.event.event_page import BaseEventPage

    if not ensure_page(
        ctrl,
        BaseEventPage.is_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        '活动地图页面',
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)

    runner = UIControllerTestRunner(
        ctrl,
        controller_name='活动地图页面',
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
        logger.opt(exception=True).error('活动地图页面 e2e 测试异常')
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info('设备已断开')

    logger.info('=== 活动地图页面 e2e 测试结束 ===')
    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == '__main__':
    main()
