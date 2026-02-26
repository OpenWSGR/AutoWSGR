"""决战 (DecisiveController) 端到端测试。

用法::

    python testing/ops/decisive_battle.py
    python testing/ops/decisive_battle.py 127.0.0.1:16384

    # 指定章节 (4–6) 和出击次数
    python testing/ops/decisive_battle.py 127.0.0.1:16384 --chapter 6 --times 1

    # 完整示例 (章节 6, 出击 2 次, 自定义舰船编组)
    python testing/ops/decisive_battle.py 127.0.0.1:16384 \\
        --chapter 6 --times 2 \\
        --level1 U-1206 U-96 射水鱼 大青花鱼 鹦鹉螺 鲃鱼 \\
        --level2 甘比尔湾 平海 \\
        --flagship U-1206

前置要求: 游戏处于任意正常页面，脚本会自动导航到决战总览页。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ── UTF-8 输出兼容 (Windows 终端) ──────────────────────────────────────────
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[union-attr]
except Exception:
    pass

from loguru import logger

from autowsgr.infra import DecisiveConfig
from autowsgr.ops.decisive import DecisiveController, DecisiveResult
from testing.ops._framework import launch_for_test


# ── 默认舰船配置 (第 6 章示例) ────────────────────────────────────────────
_DEFAULT_CHAPTER = 6
_DEFAULT_TIMES = 1
_DEFAULT_LEVEL1 = ['U-1206', 'U-96', '射水鱼', 'U-47', '鹦鹉螺', '鲃鱼']
_DEFAULT_LEVEL2 = ['M-296', '伊-25', 'U-1405']
_DEFAULT_FLAGSHIP = ['U-1206']


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='决战端到端测试',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'serial',
        nargs='?',
        default=None,
        metavar='SERIAL',
        help='ADB serial (留空则自动检测唯一设备)',
    )
    parser.add_argument(
        '--chapter',
        type=int,
        default=_DEFAULT_CHAPTER,
        metavar='N',
        choices=[4, 5, 6],
        help=f'目标章节 4/5/6 (默认: {_DEFAULT_CHAPTER})',
    )
    parser.add_argument(
        '--times',
        type=int,
        default=_DEFAULT_TIMES,
        metavar='N',
        help=f'出击轮数 (默认: {_DEFAULT_TIMES})',
    )
    parser.add_argument(
        '--level1',
        nargs='+',
        default=_DEFAULT_LEVEL1,
        metavar='SHIP',
        help='一级优先舰船列表',
    )
    parser.add_argument(
        '--level2',
        nargs='+',
        default=_DEFAULT_LEVEL2,
        metavar='SHIP',
        help='二级舰船列表',
    )
    parser.add_argument(
        '--flagship',
        nargs='+',
        default=_DEFAULT_FLAGSHIP,
        metavar='SHIP',
        help='旗舰优先级列表',
    )
    parser.add_argument(
        '--repair-level',
        type=int,
        default=2,
        metavar='N',
        choices=[1, 2],
        help='修理等级 1=中破修 2=大破修 (默认: 2)',
    )
    parser.add_argument(
        '--log-dir',
        default=None,
        metavar='DIR',
        help='日志输出目录 (默认: logs/e2e/decisive_battle)',
    )
    return parser.parse_args()


def _print_header(args: argparse.Namespace) -> None:
    print('=' * 60)
    print('  决战 (DecisiveController) E2E 测试')
    print('=' * 60)
    print()
    print(f'  章节     : {args.chapter}')
    print(f'  出击轮数 : {args.times}')
    print(f'  一级舰船 : {args.level1}')
    print(f'  二级舰船 : {args.level2}')
    print(f'  旗舰优先 : {args.flagship}')
    print(f'  修理等级 : {"中破修理" if args.repair_level == 1 else "大破修理"}')
    print()
    print('  测试步骤:')
    print('    1. 连接设备')
    print('    2. 初始化 OCR 引擎')
    print('    3. 构建 DecisiveConfig / DecisiveController')
    print(f'    4. 执行 {args.times} 轮决战 (run_for_times)')
    print('    5. 打印每轮结果')
    print()


def main() -> None:
    args = _parse_args()

    log_dir = Path(args.log_dir) if args.log_dir else Path('logs/e2e/decisive_battle')
    _print_header(args)
    input('  按 Enter 开始运行...')
    print()

    # ── 1. 连接设备 ────────────────────────────────────────────────────────
    # ── 1. 连接设备 + OCR + 游戏就绪 ──────────────────────────────────────────
    try:
        ctx = launch_for_test(args.serial, log_dir=log_dir, with_ocr=True)
        ctrl = ctx.ctrl
        ocr = ctx.ocr
        logger.info('已连接: {}', ctrl.serial)
        print(f'  [OK] 已连接: {ctrl.serial}')
        print('  [OK] OCR 引擎已就绪')
    except Exception as exc:
        logger.opt(exception=True).error('启动失败: {}', exc)
        print(f'  [FAIL] 启动失败: {exc}')
        sys.exit(1)

    # ── 2. 构建 DecisiveConfig / DecisiveController ────────────────────────
    config = DecisiveConfig(
        chapter=args.chapter,
        level1=args.level1,
        level2=args.level2,
        flagship_priority=args.flagship,
        repair_level=args.repair_level,
    )
    controller = DecisiveController(ctx, config, ocr=ocr)
    logger.info('DecisiveController 构建完成 (章节 {})', args.chapter)
    print(f'  [OK] 控制器就绪 (章节 {args.chapter})')
    print()

    # ── 4. 执行决战 ────────────────────────────────────────────────────────
    results: list[DecisiveResult] = []
    try:
        logger.info('开始执行 {} 轮决战', args.times)
        results = controller.run_for_times(args.times)
    except Exception as exc:
        logger.opt(exception=True).error('决战执行异常: {}', exc)
        print(f'  [FAIL] 决战执行异常: {exc}')
        ctrl.disconnect()
        sys.exit(1)

    # ── 5. 打印结果 ────────────────────────────────────────────────────────
    print()
    print('=' * 60)
    print(f'  决战结果  (共 {len(results)} 轮)')
    print('=' * 60)

    _RESULT_DESC = {
        DecisiveResult.CHAPTER_CLEAR: '大关通关 ✓',
        DecisiveResult.RETREAT: '主动撤退',
        DecisiveResult.LEAVE: '暂离保存',
        DecisiveResult.ERROR: '异常退出 ✗',
    }

    for i, r in enumerate(results, start=1):
        desc = _RESULT_DESC.get(r, r.value)
        logger.info('第 {}/{} 轮: {}', i, len(results), r.value)
        print(f'    第 {i:2d} 轮: {desc}')

    clear_count = sum(1 for r in results if r == DecisiveResult.CHAPTER_CLEAR)
    print()
    print(f'  大关通关: {clear_count}/{len(results)}')

    ctrl.disconnect()

    if clear_count == args.times:
        print()
        print('  [OK] 决战 E2E 测试通过')
    else:
        print()
        print(f'  [WARN] 通关率 {clear_count}/{args.times}，请检查日志')


if __name__ == '__main__':
    main()
