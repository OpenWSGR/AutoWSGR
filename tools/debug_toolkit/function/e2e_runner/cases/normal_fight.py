"""常规战快速验证 case — 接入现有 ops 操作的完整示例。

复用生产同款 ``run_normal_fight_from_yaml``, 用于快速实机验证:
计划加载 → 编队 → 多节点战斗 → 结算的常规战全链路。
编队识别依赖 OCR, 请配 ``--with-ocr`` 运行。

用法::

    # 默认跑 1 次 1-1 (内置计划)
    python tools/e2e/run.py normal_fight --with-ocr

    # 指定计划与次数
    python tools/e2e/run.py normal_fight --with-ocr --plan 7-4千伪 --times 3

    # 指定舰队编号 (默认用计划内配置)
    python tools/e2e/run.py normal_fight --with-ocr --plan 1-1 --fleet 2
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    import argparse

DESC = '常规战: 跑 N 次指定作战计划 (需 --with-ocr)'


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """定义 case 专属命令行参数。"""
    parser.add_argument('--plan', default='1-1', help='计划名或 YAML 路径 (默认 1-1)')
    parser.add_argument('--times', type=int, default=1, help='执行次数 (默认 1)')
    parser.add_argument('--fleet', type=int, default=None, help='舰队编号 (默认用计划配置)')


def run(rt: Any) -> bool:
    """执行常规战验证步骤。"""
    from autowsgr.business.combat.bettle import run_normal_fight_from_yaml

    args = rt.args
    rt.note(f'计划: {args.plan}  次数: {args.times}  舰队: {args.fleet or "计划配置"}')

    # 步骤1: 执行常规战 (复用生产 ops, 内部含计划加载/编队/战斗/结算)
    results = rt.action(
        f'执行常规战 {args.plan} x{args.times}',
        run_normal_fight_from_yaml,
        rt.ctx,
        args.plan,
        times=args.times,
        fleet_id=args.fleet,
    )
    if results is rt.FAILED:
        return False

    # 步骤2: 核对战斗次数
    ok = rt.check('战斗次数一致', lambda: len(results) == args.times)

    # 步骤3: 打印每场战果概况 (不计步, 供人工核对)
    for i, r in enumerate(results, 1):
        rt.note(f'第{i}场: flag={r.flag.name} 节点={r.node_count}')

    return ok
