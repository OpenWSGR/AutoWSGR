"""常规战 7-4 6SS 交互式端到端测试。

直接运行此脚本即可自动连接设备并执行 7-4 地图 6 潜艇战斗，适合快速手动验证。

用法::

    # 自动检测设备，默认 1 次
    python testing/ops/normal_fight.py

    # 指定设备 serial 和次数
    python testing/ops/normal_fight.py 127.0.0.1:16384 3

    # 使用自定义 YAML 计划
    python testing/ops/normal_fight.py --plan examples/plans/normal_fight/7-46SS-all.yaml

可选参数::

    --plan        自定义 YAML 计划文件 (默认使用内置 7-4 6SS 计划)
    --log-dir     日志目录 (默认 logs/interactive/normal_fight)

注意: 运行前请确保游戏处于任意正常页面 (本脚本会自动导航到出征地图页面)。
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

# ── UTF-8 输出兼容 (Windows 终端) ──
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:
    try:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
        if isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
    except Exception:
        pass

from loguru import logger

from autowsgr.combat import CombatMode, CombatPlan, NodeDecision, RuleEngine, CombatEngine
from autowsgr.emulator import ADBController
from autowsgr.infra import setup_logger
from autowsgr.ops import ensure_game_ready, NormalFightRunner
from autowsgr.types import ConditionFlag, FightCondition, Formation, GameAPP, RepairMode


# ── 默认值 ──
_DEFAULT_TIMES = 5


def _build_7_4_6ss_plan() -> CombatPlan:
    """构建内置的 7-4 6SS 战斗计划。

    6 潜艇编队打 7-4 周常，选择节点 B/E/D/L/M/K。
    """
    # 默认节点: 梯形阵، 不夜战, 前进, 中破停
    default_rules = RuleEngine.from_legacy_rules([
        ["DD + CL <= 1", "4"],
        ["CVL == 1 and CV == 0", "4"],
    ])
    default_node = NodeDecision(
        formation=Formation.double_column,
        night=False,
        proceed=True,
        proceed_stop=[2, 2, 2, 2, 2, 2],
        enemy_rules=default_rules,
    )

    b_rules = RuleEngine.from_legacy_rules([
        ["CL >= 3", "retreat"],
    ])
    node_b = NodeDecision(
        formation=Formation.single_column,
        night=False,
        proceed=True,
        proceed_stop=[2, 2, 2, 2, 2, 2],
        enemy_rules=b_rules,
    )

    # M 节点: 单纵阵, 夜战
    m_rules = RuleEngine.from_legacy_rules([
        ["DD + CL <= 1", "4"],
        ["CVL == 1 and CV == 0", "4"],
    ])
    node_m = NodeDecision(
        formation=Formation.single_column,
        night=True,
        proceed=True,
        proceed_stop=[2, 2, 2, 2, 2, 2],
        enemy_rules=m_rules,
    )

    return CombatPlan(
        name="7-4-6SS-交互测试",
        mode=CombatMode.NORMAL,
        chapter=7,
        map_id=4,
        fleet_id=2,
        repair_mode=RepairMode.moderate_damage,
        fight_condition=FightCondition(4),
        selected_nodes=["B", "E", "D", "L", "M", "K"],
        default_node=default_node,
        nodes={
            "B": node_b,
            "M": node_m,
        },
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="7-4 6SS 常规战交互式测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "serial",
        nargs="?",
        default=None,
        metavar="SERIAL",
        help="ADB serial (留空则自动检测唯一设备)",
    )
    parser.add_argument(
        "times",
        nargs="?",
        type=int,
        default=_DEFAULT_TIMES,
        metavar="TIMES",
        help=f"战斗次数, 默认: {_DEFAULT_TIMES}",
    )
    parser.add_argument(
        "--plan",
        default=None,
        metavar="YAML",
        help="自定义 YAML 计划文件 (默认使用内置 7-4 6SS)",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        metavar="DIR",
        help="日志输出目录 (默认: logs/interactive/normal_fight)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # ── 日志 ──
    log_dir = Path(args.log_dir) if args.log_dir else Path("logs/interactive/normal_fight")
    setup_logger(log_dir=log_dir, level="DEBUG", save_images=True)

    serial: str | None = args.serial or None
    times: int = args.times

    # ── 加载计划 ──
    if args.plan:
        plan = CombatPlan.from_yaml(args.plan)
        logger.info("使用自定义计划: {}", args.plan)
    else:
        plan = _build_7_4_6ss_plan()
        logger.info("使用内置 7-4 6SS 计划")

    logger.info("=" * 50)
    logger.info("常规战交互式测试")
    logger.info("  地图: {}-{}", plan.chapter, plan.map_id)
    logger.info("  节点: {}", plan.selected_nodes)
    logger.info("  次数: {}", times)
    logger.info("  日志: {}", log_dir)
    logger.info("=" * 50)

    # ── 连接设备 ──
    logger.info("正在连接设备{}...", f" ({serial})" if serial else " (自动检测)")
    ctrl = ADBController(serial=serial)
    try:
        dev_info = ctrl.connect()
        logger.info(
            "已连接: {}  分辨率: {}x{}",
            dev_info.serial,
            dev_info.resolution[0],
            dev_info.resolution[1],
        )
    except Exception as exc:
        logger.error("连接设备失败: {}", exc)
        sys.exit(1)

    # ── 初始化：确保游戏已就绪 ──
    # ensure_game_ready(ctrl, GameAPP.official)

    # ── 初始化引擎 ──
    runner = NormalFightRunner(ctrl, plan)

    # ── 运行战斗 ──
    results: list = []
    for i in range(times):
        logger.info("第 {}/{} 次战斗", i + 1, times)

        # 导航到出征地图页 → 选择地图 → 进入准备页
        result = runner.run()

        logger.info(
            "  战斗结果: {} 血量={}",
            result.flag.value if result.flag else "N/A",
            result.ship_stats,
        )

    # ── 结果汇总 ──
    logger.info("=" * 50)
    logger.info("测试结束, 共 {} 场", len(results))

    for i, r in enumerate(results, start=1):
        flag_str = str(r.flag.value) if r.flag is not None else "N/A"
        stats = r.ship_stats if r.ship_stats is not None else []
        logger.info(
            "  [{}] 状态={:<20} 节点数={} 血量={}",
            i,
            flag_str,
            r.node_count,
            stats,
        )

    success_count = sum(
        1 for r in results if r.flag == ConditionFlag.OPERATION_SUCCESS
    )
    logger.info("成功完成: {}/{}", success_count, len(results))
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
