"""战役交互式端到端测试。

直接运行此脚本即可自动连接设备并执行战役，适合快速手动验证。

用法::

    # 自动检测设备，困难驱逐 ×1
    python testing/interactive/campaign.py

    # 指定设备 serial
    python testing/interactive/campaign.py 127.0.0.1:16384

    # 指定战役名和次数（serial 留空用自动检测）
    python testing/interactive/campaign.py "" 困难航母 3

    # 全参数
    python testing/interactive/campaign.py 127.0.0.1:16384 简单驱逐 2

可选参数::

    --formation   阵型名称（默认 double_column）
    --no-night    不进行夜战
    --log-dir     日志目录（默认 logs/interactive/campaign）

注意: 运行前请确保游戏处于任意正常页面（本脚本会自动导航到战役页面）。
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

# ── UTF-8 输出兼容（Windows 终端）──
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

from autowsgr.infra import setup_logger
from autowsgr.emulator import ADBController
from autowsgr.combat.engine import CombatEngine
from autowsgr.ops.campaign import CampaignRunner, CAMPAIGN_NAME_MAP
from autowsgr.types import ConditionFlag, Formation, RepairMode


# ── 默认值 ──────────────────────────────────────────────────────────────────
_DEFAULT_CAMPAIGN = "困难驱逐"
_DEFAULT_TIMES = 1
_DEFAULT_FORMATION = "double_column"


# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="战役交互式测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "可选战役名称:\n  "
            + "\n  ".join(sorted(CAMPAIGN_NAME_MAP))
        ),
    )
    parser.add_argument(
        "serial",
        nargs="?",
        default=None,
        metavar="SERIAL",
        help="ADB serial（留空则自动检测唯一设备）",
    )
    parser.add_argument(
        "campaign",
        nargs="?",
        default=_DEFAULT_CAMPAIGN,
        metavar="CAMPAIGN",
        help=f"战役名称，默认: {_DEFAULT_CAMPAIGN}",
    )
    parser.add_argument(
        "times",
        nargs="?",
        type=int,
        default=_DEFAULT_TIMES,
        metavar="TIMES",
        help=f"战役次数，默认: {_DEFAULT_TIMES}",
    )
    parser.add_argument(
        "--formation",
        default=_DEFAULT_FORMATION,
        choices=[f.name for f in Formation],
        help=f"舰队阵型，默认: {_DEFAULT_FORMATION}",
    )
    parser.add_argument(
        "--no-night",
        action="store_true",
        help="不进行夜战（默认开启夜战）",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        metavar="DIR",
        help="日志输出目录（默认: logs/interactive/campaign）",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # ── 日志：默认 DEBUG ──────────────────────────────────────────────────────
    log_dir = Path(args.log_dir) if args.log_dir else Path("logs/interactive/campaign")
    setup_logger(log_dir=log_dir, level="DEBUG", save_images=True)

    serial: str | None = args.serial or None
    campaign_name: str = args.campaign
    times: int = args.times
    formation = Formation[args.formation]
    night = not args.no_night

    logger.info("=" * 50)
    logger.info("战役交互式测试")
    logger.info("  战役: {}", campaign_name)
    logger.info("  次数: {}", times)
    logger.info("  阵型: {}", formation.name)
    logger.info("  夜战: {}", night)
    logger.info("  日志: {}", log_dir)
    logger.info("=" * 50)

    # ── 连接设备 ─────────────────────────────────────────────────────────────
    logger.info("正在连接设备{}...", f" ({serial})" if serial else "（自动检测）")
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

    # ── 初始化战斗引擎 ────────────────────────────────────────────────────────
    engine = CombatEngine(ctrl)

    # ── 初始化战役执行器 ──────────────────────────────────────────────────────
    runner = CampaignRunner(
        ctrl=ctrl,
        engine=engine,
        campaign_name=campaign_name,
        times=times,
        formation=formation,
        night=night,
        repair_mode=RepairMode.moderate_damage,
    )

    # ── 运行战役 ──────────────────────────────────────────────────────────────
    logger.info("开始运行战役...")
    try:
        results = runner.run()
    except Exception as exc:
        logger.exception("战役运行异常: {}", exc)
        sys.exit(1)

    # ── 结果汇总 ──────────────────────────────────────────────────────────────
    logger.info("=" * 50)
    logger.info("战役结束，共 {} 场", len(results))

    for i, r in enumerate(results, start=1):
        flag_str = str(r.flag.value) if r.flag is not None else "N/A"
        stats = r.ship_stats if r.ship_stats is not None else []
        logger.info(
            "  [{}] 状态={:<20} 节点数={} 舰船血量={}",
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
