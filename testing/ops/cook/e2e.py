"""食堂做菜 (cook) 端到端测试。

运行方式::

    # 交互模式 (默认)
    python testing/ops/cook/e2e.py

    # 自动执行
    python testing/ops/cook/e2e.py --auto

    # 指定设备
    python testing/ops/cook/e2e.py emulator-5554 --auto --debug

前置条件：
    游戏位于 **主页面** (母港/秘书舰界面)

测试内容：
    1. 验证初始状态 (主页面识别)
    2. 导航到食堂页面
    3. 执行做菜 (cook)
    4. 验证返回主页面
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from autowsgr.infra import setup_logger
from testing.ui._framework import UIControllerTestRunner, connect_device, ensure_page, info, parse_e2e_args, reset_to_main_page


def run_test(runner: UIControllerTestRunner) -> None:
    """执行食堂做菜的完整测试序列。"""
    from autowsgr.ops.cook import cook
    from autowsgr.ops.navigate import goto_page
    from autowsgr.ui.canteen_page import CanteenPage
    from autowsgr.ui.main_page import MainPage

    # ───── Step 0: 验证初始状态 ──────────────────────────────────────
    runner.verify_current("初始验证: 主页面", "主页面", MainPage.is_current_page)
    if runner.aborted:
        return

    # ───── Step 1: 导航到食堂 ────────────────────────────────────────
    runner.execute_step(
        "主页面 → 食堂页面",
        "食堂页面",
        CanteenPage.is_current_page,
        lambda: goto_page(runner.ctrl, "食堂页面"),
    )
    if runner.aborted:
        return

    # ───── Step 2: 执行做菜 (默认位置 1) ──────────────────────────────
    def _cook() -> None:
        """执行做菜操作。"""
        result = cook(runner.ctrl, position=1, force_cook=False)
        info(f"cook(position=1, force_cook=False) 返回: {result}")

    runner.execute_step(
        "执行做菜 (位置 1)",
        "食堂页面",
        CanteenPage.is_current_page,
        _cook,
    )
    if runner.aborted:
        return

    # ───── Step 3: 返回主页面 ────────────────────────────────────────
    runner.execute_step(
        "食堂页面 → ◁ 主页面",
        "主页面",
        MainPage.is_current_page,
        lambda: goto_page(runner.ctrl, "主页面"),
    )
    if runner.aborted:
        return

    # ───── Step 4: 最终验证 ──────────────────────────────────────────
    runner.verify_current("最终验证: 返回主页面", "主页面", MainPage.is_current_page)


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面返回主页面。"""
    reset_to_main_page(ctrl, pause)


def main() -> None:
    args = parse_e2e_args(
        "食堂做菜 (cook) e2e 测试",
        precondition="游戏位于主页面 (母港/秘书舰界面)",
        default_log_dir="logs/e2e/cook",
    )
    setup_logger(log_dir=args.log_dir, level=args.log_level, save_images=True)
    from loguru import logger

    logger.info("=== 食堂做菜 e2e 测试开始 ===")
    ctrl = connect_device(args.serial)
    from autowsgr.ui.main_page import MainPage

    if not ensure_page(
        ctrl,
        MainPage.is_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        "主页面",
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)

    runner = UIControllerTestRunner(
        ctrl,
        controller_name="食堂做菜",
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
        logger.opt(exception=True).error("食堂做菜 e2e 测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info("设备已断开")

    logger.info("=== 食堂做菜 e2e 测试结束 ===")
    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
