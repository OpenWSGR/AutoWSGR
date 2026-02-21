"""战役战斗 (CampaignRunner) 端到端测试。

运行方式::

    # 交互模式 (默认，困难驱逐)
    python testing/ops/campaign/e2e.py

    # 自动执行
    python testing/ops/campaign/e2e.py --auto

    # 指定战役名称和次数
    python testing/ops/campaign/e2e.py --campaign 困难航母 --times 1 --auto

    # 指定设备
    python testing/ops/campaign/e2e.py emulator-5554 --auto --debug

命令行参数::

    serial         设备序列号 (可选，默认自动检测)
    --campaign     战役名称，如 "困难驱逐"、"简单航母" (默认: 困难驱逐)
    --times        重复次数 (默认: 1)
    --no-night     禁用夜战 (默认启用)
    --formation    阵型编号 1-5 (默认: 2 复纵阵)
    --auto         全自动执行
    --debug        DEBUG 日志级别
    --pause        每步等待时间 (秒)，默认 1.5

前置条件：
    游戏位于 **主页面** (母港/秘书舰界面)，且战役次数未用完

测试内容：
    1. 验证初始状态 (主页面)
    2. 显示战役配置
    3. 执行战役战斗 (CampaignRunner.run)
    4. 验证战斗结束后页面
    5. 汇总战斗结果
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from autowsgr.infra import setup_logger
from testing.ui._framework import (
    UIControllerTestRunner,
    connect_device,
    ensure_page,
    fail,
    info,
    ok,
    parse_e2e_args,
    reset_to_main_page,
    warn,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 额外命令行参数解析
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_campaign_args() -> dict:
    """在 parse_e2e_args 之后解析战役专用参数。"""
    campaign = "困难驱逐"
    times = 1
    night = True
    formation = 2

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--campaign":
            i += 1
            campaign = args[i]
        elif arg == "--times":
            i += 1
            times = int(args[i])
        elif arg == "--no-night":
            night = False
        elif arg == "--formation":
            i += 1
            formation = int(args[i])
        i += 1

    return {"campaign": campaign, "times": times, "night": night, "formation": formation}


# ═══════════════════════════════════════════════════════════════════════════════
# 测试序列
# ═══════════════════════════════════════════════════════════════════════════════


def run_test(
    runner: UIControllerTestRunner,
    campaign_name: str,
    times: int,
    night: bool,
    formation_id: int,
) -> None:
    """执行战役战斗的完整测试序列。"""
    from autowsgr.combat.callbacks import CombatResult
    from autowsgr.combat.engine import CombatEngine
    from autowsgr.ops.campaign import CampaignRunner
    from autowsgr.types import ConditionFlag, Formation
    from autowsgr.ui.main_page import MainPage
    from autowsgr.ui.map.page import MapPage

    formation = Formation(formation_id)

    # ───── Step 0: 验证初始状态 ──────────────────────────────────────
    runner.verify_current("初始验证: 主页面", "主页面", MainPage.is_current_page)
    if runner.aborted:
        return

    # ───── Step 1: 显示战役配置 ──────────────────────────────────────
    runner.read_state(
        "战役配置",
        readers={
            "战役名称": lambda _: campaign_name,
            "次数": lambda _: times,
            "阵型": lambda _: f"{formation_id} ({formation.name})",
            "夜战": lambda _: night,
        },
    )

    # ───── Step 2: 执行战役战斗 ──────────────────────────────────────
    results: list[CombatResult] = []

    def _run_campaign() -> None:
        engine = CombatEngine(runner.ctrl)
        campaign_runner = CampaignRunner(
            runner.ctrl,
            engine,
            campaign_name,
            times=times,
            formation=formation,
            night=night,
        )
        nonlocal results
        results = campaign_runner.run()

    runner.execute_step(
        f"执行战役战斗 {campaign_name} x{times}",
        "地图页面",
        MapPage.is_current_page,
        _run_campaign,
    )
    if runner.aborted:
        return

    # ───── Step 3: 汇总战斗结果 ──────────────────────────────────────
    if results:
        info(f"共完成 {len(results)} 次战斗")
        for i, r in enumerate(results):
            flag_str = r.flag.value
            node_count = r.node_count
            info(f"  [{i + 1}] flag={flag_str}  节点数={node_count}  "
                 f"血量={r.ship_stats}")
        success_count = sum(
            1 for r in results if r.flag == ConditionFlag.OPERATION_SUCCESS
        )
        if success_count == len(results):
            ok(f"全部 {success_count} 次战斗成功")
        else:
            warn(f"成功 {success_count}/{len(results)} 次")
    else:
        warn("未获得任何战斗结果")


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════


def _navigate_to(ctrl, pause: float) -> None:
    """从任意已知页面返回主页面。"""
    reset_to_main_page(ctrl, pause)


def main() -> None:
    campaign_args = _parse_campaign_args()

    campaign_name: str = campaign_args["campaign"]
    times: int = campaign_args["times"]
    night: bool = campaign_args["night"]
    formation_id: int = campaign_args["formation"]

    args = parse_e2e_args(
        f"战役战斗 ({campaign_name}) e2e 测试",
        precondition=(
            f"游戏位于主页面 (母港/秘书舰界面)，"
            f"且 [{campaign_name}] 战役次数未用完"
        ),
        default_log_dir="logs/e2e/campaign",
    )
    setup_logger(log_dir=args.log_dir, level=args.log_level, save_images=True)
    from loguru import logger

    logger.info("=== 战役战斗 e2e 测试开始: {} ===", campaign_name)

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
        controller_name="战役战斗",
        log_dir=args.log_dir,
        auto_mode=args.auto,
        pause=args.pause,
    )

    try:
        run_test(runner, campaign_name, times, night, formation_id)
    except KeyboardInterrupt:
        warn("用户中断 (Ctrl+C)")
    except Exception as exc:
        fail(f"未预期异常: {exc}")
        logger.opt(exception=True).error("战役战斗 e2e 测试异常")
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info("设备已断开")

    logger.info("=== 战役战斗 e2e 测试结束 ===")
    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == "__main__":
    main()
