"""调度器端到端测试 — Ex5 三连夜战 + 定时远征。

用法::

    # 默认: Ex5 H5 三连夜战 ×30, 远征间隔 15min
    python testing/ops/scheduler.py

    # 指定设备和次数
    python testing/ops/scheduler.py 127.0.0.1:16384 --times 10

    # 使用自定义 YAML
    python testing/ops/scheduler.py --plan examples/plans/event/20260212/Ex5A夜战.yaml --times 50

前置要求: 游戏处于任意正常页面。
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

from autowsgr.combat import CombatPlan
from autowsgr.ops.event_fight import EventFightRunner
from autowsgr.scheduler import FightTask, TaskScheduler
from autowsgr.types import ConditionFlag
from testing.ops._framework import launch_for_test


# ── 默认值 ──
_DEFAULT_PLAN_YAML = str(
    Path(__file__).parent.parent.parent
    / 'examples'
    / 'plans'
    / 'event'
    / '20260212'
    / 'Ex5A夜战.yaml'
)
_DEFAULT_TIMES = 30
_DEFAULT_MAP_CODE = 'H5'
_DEFAULT_EXPEDITION_INTERVAL = 900  # 15 分钟


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='调度器端到端测试 — Ex5 三连夜战 + 定时远征',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'serial',
        nargs='?',
        default=None,
        metavar='SERIAL',
        help='ADB serial（留空则自动检测唯一设备）',
    )
    parser.add_argument(
        '--plan',
        default=_DEFAULT_PLAN_YAML,
        metavar='YAML',
        help='战斗计划 YAML（默认: Ex5A夜战.yaml）',
    )
    parser.add_argument(
        '--map-code',
        default=_DEFAULT_MAP_CODE,
        metavar='CODE',
        help=f'活动地图代号（默认: {_DEFAULT_MAP_CODE}）',
    )
    parser.add_argument(
        '--times',
        type=int,
        default=_DEFAULT_TIMES,
        metavar='N',
        help=f'战斗次数（默认: {_DEFAULT_TIMES}）',
    )
    parser.add_argument(
        '--expedition-interval',
        type=int,
        default=_DEFAULT_EXPEDITION_INTERVAL,
        metavar='SEC',
        help=f'远征检查间隔秒数（默认: {_DEFAULT_EXPEDITION_INTERVAL}）',
    )
    parser.add_argument(
        '--log-dir',
        default=None,
        metavar='DIR',
        help='日志输出目录（默认: logs/interactive/scheduler）',
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    log_dir = Path(args.log_dir) if args.log_dir else Path('logs/interactive/scheduler')

    serial = args.serial or None

    # ── 连接并启动游戏 ──
    try:
        ctx = launch_for_test(serial, log_dir=log_dir)
    except Exception as exc:
        print(f'[ERROR] 启动失败: {exc}')
        sys.exit(1)
    ctrl = ctx.ctrl

    logger.info('=' * 60)
    logger.info('调度器 E2E 测试 — Ex5 三连夜战 + 远征')
    logger.info('  计划: {}', args.plan)
    logger.info('  地图: {}', args.map_code)
    logger.info('  次数: {}', args.times)
    logger.info('  远征: 每 {}s', args.expedition_interval)
    logger.info('已连接: {}', ctrl.serial)
    logger.info('=' * 60)

    # ── 加载计划 ──
    plan = CombatPlan.from_yaml(args.plan)
    logger.info('已加载计划: {} ({})', plan.name, args.plan)

    # ── 构建 Runner ──
    runner = EventFightRunner(ctx, plan, map_code=args.map_code, fleet_id=2)

    # ── 构建调度器 ──
    scheduler = TaskScheduler(
        ctx,
        expedition_interval=float(args.expedition_interval),
    )
    scheduler.add(
        FightTask(
            runner=runner,
            times=args.times,
            name=f'Ex5夜战-{args.map_code}',
        )
    )

    # ── 运行 ──
    logger.info('开始调度...')
    try:
        tasks = scheduler.run()
    except Exception as exc:
        logger.exception('调度异常: {}', exc)
        sys.exit(1)

    # ── 结果 ──
    task = tasks[0]
    success = sum(1 for r in task.results if r.flag == ConditionFlag.OPERATION_SUCCESS)
    logger.info('=' * 60)
    logger.info('完成: {}/{} 成功', success, task.completed)
    logger.info('=' * 60)


if __name__ == '__main__':
    main()
