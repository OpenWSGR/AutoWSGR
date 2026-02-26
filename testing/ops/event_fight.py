"""活动战交互式端到端测试。

直接运行此脚本即可自动连接设备并执行活动战斗，适合快速手动验证。

用法::

    # 自动检测设备，默认打 H3 × 1 次
    python testing/ops/event_fight.py

    # 指定设备 serial
    python testing/ops/event_fight.py 127.0.0.1:16384

    # 指定 map_code 和次数
    python testing/ops/event_fight.py "" H5 3

    # 全参数
    python testing/ops/event_fight.py 127.0.0.1:16384 E2 2

可选参数::

    --entrance    入口选择: alpha / beta（默认 None，不切换）
    --fleet       舰队编号 1-4（默认 1）
    --formation   阵型名称（默认 double_column）
    --no-night    不进行夜战
    --plan        自定义 YAML 计划文件（默认使用内置简易计划）
    --log-dir     日志目录（默认 logs/interactive/event_fight）

注意: 运行前请确保游戏处于任意正常页面（本脚本会自动导航到活动地图页面）。
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path


# ── UTF-8 输出兼容（Windows 终端）──
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[union-attr]
except Exception:
    try:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True
            )
        if isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True
            )
    except Exception:
        pass

from loguru import logger

from autowsgr.combat import CombatMode, CombatPlan, NodeDecision, RuleEngine
from autowsgr.ops.event_fight import EventFightRunner
from autowsgr.types import ConditionFlag, FightCondition, Formation, RepairMode
from testing.ops._framework import launch_for_test


# ── 默认值 ──────────────────────────────────────────────────────────────────
_DEFAULT_MAP_CODE = 'H5'
_DEFAULT_TIMES = 3
_DEFAULT_FLEET_ID = 1
_DEFAULT_FORMATION = 'single_column'
_DEFAULT_PLAN_YAML = str(
    Path(__file__).parent.parent.parent
    / 'examples'
    / 'plans'
    / 'event'
    / '20260212'
    / 'Ex5A夜战.yaml'
)


def _build_default_plan(
    map_code: str,
    fleet_id: int = 1,
    formation: Formation = Formation.double_column,
    night: bool = True,
) -> CombatPlan:
    """构建内置的活动战简易计划。

    Parameters
    ----------
    map_code:
        活动地图代号，如 ``"H3"``。
    fleet_id:
        舰队编号。
    formation:
        默认阵型。
    night:
        是否进行夜战。
    """
    # 推导 chapter / map_id
    chapter = map_code[0].upper() if map_code else 'H'
    map_id_str = map_code[1:] if len(map_code) > 1 else '1'
    try:
        map_id = int(map_id_str)
    except ValueError:
        map_id = 1

    default_node = NodeDecision(
        formation=formation,
        night=night,
        proceed=True,
        proceed_stop=RepairMode.moderate_damage,
        enemy_rules=RuleEngine.from_legacy_rules([]),
    )

    return CombatPlan(
        name=f'活动战-{map_code}-交互测试',
        mode=CombatMode.EVENT,
        chapter=chapter,
        map_id=map_id,
        fleet_id=fleet_id,
        repair_mode=RepairMode.moderate_damage,
        fight_condition=FightCondition(4),
        default_node=default_node,
    )


# ─────────────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='活动战交互式测试',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='map_code 格式: H1-H6 或 E1-E6 (H=困难, E=简单)',
    )
    parser.add_argument(
        'serial',
        nargs='?',
        default=None,
        metavar='SERIAL',
        help='ADB serial（留空则自动检测唯一设备）',
    )
    parser.add_argument(
        'map_code',
        nargs='?',
        default=_DEFAULT_MAP_CODE,
        metavar='MAP_CODE',
        help=f'活动地图代号，默认: {_DEFAULT_MAP_CODE}',
    )
    parser.add_argument(
        'times',
        nargs='?',
        type=int,
        default=_DEFAULT_TIMES,
        metavar='TIMES',
        help=f'战斗次数，默认: {_DEFAULT_TIMES}',
    )
    parser.add_argument(
        '--entrance',
        choices=['alpha', 'beta'],
        default=None,
        help='入口选择（默认不切换）',
    )
    parser.add_argument(
        '--fleet',
        type=int,
        default=_DEFAULT_FLEET_ID,
        choices=[1, 2, 3, 4],
        help=f'舰队编号，默认: {_DEFAULT_FLEET_ID}',
    )
    parser.add_argument(
        '--formation',
        default=_DEFAULT_FORMATION,
        choices=[f.name for f in Formation],
        help=f'舰队阵型，默认: {_DEFAULT_FORMATION}',
    )
    parser.add_argument(
        '--no-night',
        action='store_true',
        help='不进行夜战（默认开启夜战）',
    )
    parser.add_argument(
        '--plan',
        default=None,
        metavar='YAML',
        help='自定义 YAML 计划文件（默认使用内置简易计划）',
    )
    parser.add_argument(
        '--log-dir',
        default=None,
        metavar='DIR',
        help='日志输出目录（默认: logs/interactive/event_fight）',
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    log_dir = Path(args.log_dir) if args.log_dir else Path('logs/interactive/event_fight')
    serial: str | None = args.serial or None
    map_code: str = args.map_code
    times: int = args.times
    entrance = args.entrance
    formation = Formation[args.formation]
    night = not args.no_night

    # ── 连接并启动游戏 ──
    try:
        ctx = launch_for_test(serial, log_dir=log_dir)
    except Exception as exc:
        print(f'[ERROR] 启动失败: {exc}')
        sys.exit(1)
    ctrl = ctx.ctrl

    logger.info('=' * 50)
    logger.info('活动战交互式测试')
    logger.info('  地图: {}', map_code)
    logger.info('  入口: {}', entrance or '默认')
    logger.info('  次数: {}', times)
    logger.info('  舰队: {}', args.fleet)
    logger.info('  阵型: {}', formation.name)
    logger.info('  夜战: {}', night)
    logger.info('  日志: {}', log_dir)
    logger.info('已连接: {}', ctrl.serial)
    logger.info('=' * 50)

    # ── 加载/构建计划 ──
    plan_path = args.plan or _DEFAULT_PLAN_YAML
    if Path(plan_path).exists():
        plan = CombatPlan.from_yaml(plan_path)
        logger.info('使用 YAML 计划: {}', plan_path)
    else:
        plan = _build_default_plan(
            map_code=map_code,
            fleet_id=args.fleet,
            formation=formation,
            night=night,
        )
        logger.info('使用内置活动战计划: {}', plan.name)

    # ── 初始化执行器 ──
    runner = EventFightRunner(
        ctx,
        plan,
        map_code=map_code,
        entrance=entrance,
    )

    # ── 运行战斗 ──
    logger.info('开始运行活动战...')
    try:
        results = runner.run_for_times(times)
    except Exception as exc:
        logger.exception('活动战运行异常: {}', exc)
        sys.exit(1)

    # ── 结果汇总 ──
    logger.info('=' * 50)
    logger.info('活动战结束，共 {} 场', len(results))

    for i, r in enumerate(results, start=1):
        flag_str = str(r.flag.value) if r.flag is not None else 'N/A'
        stats = r.ship_stats if r.ship_stats is not None else []
        logger.info(
            '  [{}] 状态={:<20} 节点数={} 舰船血量={}',
            i,
            flag_str,
            r.node_count,
            stats,
        )

    success_count = sum(1 for r in results if r.flag == ConditionFlag.OPERATION_SUCCESS)
    logger.info('成功完成: {}/{}', success_count, len(results))
    logger.info('=' * 50)


if __name__ == '__main__':
    main()
