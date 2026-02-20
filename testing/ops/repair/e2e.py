"""浴室修理 (repair_in_bath) 端到端测试。

运行方式::

    # 交互模式 (默认)
    python testing/ops/repair/e2e.py

    # 自动执行
    python testing/ops/repair/e2e.py --auto

    # 指定设备
    python testing/ops/repair/e2e.py emulator-5554 --auto --debug

前置条件：
    游戏位于 **任意已知页面** (主页面、地图页面等)，且存在待修理舰船

测试内容：
    1. 验证任意页面识别
    2. 导航到浴室页面
    3. 执行浴室修理 (repair_in_bath)
    4. 验证返回主页面
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from autowsgr.infra import setup_logger
from testing.ui._framework import UIControllerTestRunner, connect_device, info, parse_e2e_args, reset_to_main_page


def run_test(runner: UIControllerTestRunner) -> None:
    """执行浴室修理的完整测试序列。"""
    from autowsgr.ops.repair import repair_in_bath
    from autowsgr.ops.navigate import goto_page
    from autowsgr.ui.bath_page import BathPage
    from autowsgr.ui.main_page import MainPage

    # ───── Step 0: 验证当前页面识别 ───────────────────────────────────
    screen = runner.ctrl.screenshot()
    current_page = "未知页面"
    try:
        from autowsgr.ui.page import get_current_page
        current_page = get_current_page(screen) or "未知页面"
    except Exception:
        pass
    info(f"当前页面: {current_page}")

    # ───── Step 1: 导航到浴室页面 ──────────────────────────────────────
    runner.execute_step(
        "导航 → 浴室页面",
        "浴室页面",
        BathPage.is_current_page,
        lambda: goto_page(runner.ctrl, "浴室页面"),
    )
    if runner.aborted:
        return

    # ───── Step 2: 执行浴室修理 ────────────────────────────────────────
    def _repair() -> None:
        """执行修理操作。"""
        repair_in_bath(runner.ctrl)
        info("repair_in_bath() 已执行")

    runner.execute_step(
        "执行浴室修理",
        "浴室页面",
        BathPage.is_current_page,
        _repair,
    )
    if runner.aborted:
        return

    # ───── Step 3: 返回主页面 ────────────────────────────────────────
    runner.execute_step(
        "浴室页面 → ◁ 主页面",
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
        "浴室修理 (repair_in_bath) e2e 测试",
        precondition="游戏位于任意已知页面，且存在待修理舰船",
        default_log_dir="logs/e2e/repair",
    )
    setup_logger(log_dir=args.log_dir, level=args.log_level, save_images=True)
    from loguru import logger

    logger.info("=== 浴室修理 e2e 测试开始 ===")
    ctrl = connect_device(args.serial)

    runner = UIControllerTestRunner(
        ctrl,
        controller_name="浴室修理",
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
        logger.opt(exception=True).error("浴室修理 e2e 测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info("设备已断开")

    logger.info("=== 浴室修理 e2e 测试结束 ===")
    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
