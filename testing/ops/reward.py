"""任务奖励收取 (collect_rewards) 端到端测试。

运行方式::

    # 交互模式 (默认)
    python testing/ops/reward.py

    # 自动执行
    python testing/ops/reward.py --auto

    # 指定设备
    python testing/ops/reward.py emulator-5554 --auto --debug

前置条件：
    游戏位于 **主页面** (母港/秘书舰界面)，且存在未领取的任务奖励

测试内容：
    1. 验证初始状态 (主页面识别)
    2. 检查任务奖励通知
    3. 执行收取奖励 (collect_rewards)
    4. 验证返回主页面
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from autowsgr.infra import setup_logger
from testing.ui._framework import UIControllerTestRunner, connect_device, ensure_page, info, parse_e2e_args, reset_to_main_page


def run_test(runner: UIControllerTestRunner) -> None:
    """执行任务奖励收取的完整测试序列。"""
    from autowsgr.ops.reward import collect_rewards
    from autowsgr.ui.main_page import MainPage

    main_page = MainPage(runner.ctrl)

    # ───── Step 0: 验证初始状态 ──────────────────────────────────────
    runner.verify_current("初始验证: 主页面", "主页面", MainPage.is_current_page)
    if runner.aborted:
        return

    # ───── Step 1: 读取任务状态 ──────────────────────────────────────
    runner.read_state(
        "主页面状态",
        readers={
            "任务通知": lambda s: MainPage.has_task_ready(s),
        },
    )

    # ───── Step 2: 执行收取奖励 ──────────────────────────────────────
    def _collect() -> None:
        """包装 collect_rewards 并记录返回值。"""
        result = collect_rewards(runner.ctrl)
        info(f"collect_rewards() 返回: {result}")

    runner.execute_step(
        "执行收取奖励",
        "主页面",
        MainPage.is_current_page,
        _collect,
    )
    if runner.aborted:
        return

    # ───── Step 3: 最终验证 ──────────────────────────────────────────
    runner.verify_current("最终验证: 返回主页面", "主页面", MainPage.is_current_page)


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面返回主页面。"""
    reset_to_main_page(ctrl, pause)


def main() -> None:
    args = parse_e2e_args(
        "任务奖励操作 (collect_rewards) e2e 测试",
        precondition="游戏位于主页面 (母港/秘书舰界面)，且存在未领取的任务奖励",
        default_log_dir="logs/e2e/reward",
    )
    setup_logger(log_dir=args.log_dir, level=args.log_level, save_images=True)
    from loguru import logger

    logger.info("=== 任务奖励操作 e2e 测试开始 ===")
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
        controller_name="任务奖励",
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
        logger.opt(exception=True).error("任务奖励操作 e2e 测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info("设备已断开")

    logger.info("=== 任务奖励操作 e2e 测试结束 ===")
    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
