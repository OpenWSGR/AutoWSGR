"""战役断点与编队 E2E。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    import argparse

DESC = '战役: 编队、断点和任务插入验证 (需 --with-ocr)'

_DEFAULT_YAML = str(
    Path(__file__).resolve().parents[3] / 'testing' / 'fixtures' / 'campaign_simple_destroyer.yaml'
)
_BREAKPOINTS = (
    'panel_ready',
    'formation_entered',
    'fleet_checkpoint',
    'before_start',
    'battle_done',
)
_CHECK_TYPES = ('expedition_check', 'reward_check')


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """定义战役 case 参数。"""
    parser.add_argument('--yaml', default=_DEFAULT_YAML, help='战役任务 YAML 路径')
    parser.add_argument('--times', type=int, default=1, help='执行战役次数')
    parser.add_argument('--pause-at', choices=_BREAKPOINTS, default=None, help='插入检查的断点')
    parser.add_argument(
        '--check',
        choices=_CHECK_TYPES,
        default='expedition_check',
        help='断点插入的检查任务',
    )
    parser.add_argument(
        '--ship-name-alias',
        action='append',
        default=[],
        metavar='CUSTOM=STANDARD',
        help='用户舰名映射，可重复传入',
    )


def _aliases(ctx: Any, values: list[str]) -> dict[str, str] | None:
    """合并配置和命令行舰名映射。"""
    ocr_config = getattr(getattr(ctx, 'config', None), 'ocr', None)
    result = dict(getattr(ocr_config, 'ship_name_aliases', {}) or {})
    for value in values:
        alias, separator, standard = value.partition('=')
        if not separator or not alias.strip() or not standard.strip():
            return None
        result[alias.strip()] = standard.strip()
    return result


def run(rt: Any) -> bool:
    """执行一次战役任务并验证断点交接。"""
    from autowsgr.application.ui.navigation import identify_current_page
    from autowsgr.common.types import PageName
    from autowsgr.dispatch import Processor, Request

    args = rt.args
    if not 1 <= args.times <= 8:
        rt.note('times 必须在 1-8 范围内')
        return False
    aliases = _aliases(rt.ctx, args.ship_name_alias)
    if aliases is None:
        rt.note('无效舰名映射')
        return False

    request = rt.action(
        '加载战役任务 YAML',
        Request.from_yaml,
        args.yaml,
        source='cli',
        count=args.times,
        ship_name_aliases=aliases,
    )
    if request is rt.FAILED:
        return False

    processor = Processor(rt.ctx)
    events: list[str] = []
    paused_page: list[str | None] = []
    interrupted = [False]

    def on_event(event: str, **_data: Any) -> None:
        events.append(event)
        if event == 'paused':
            paused_page.append(identify_current_page(rt.ctx))
        if args.pause_at == event and not interrupted[0]:
            interrupted[0] = True
            processor.interrupt(Request(task_type=args.check, source='dependency'))
            rt.note(f'断点 [{event}] 插入 {args.check}')

    processor.on_event = on_event
    processor.submit(request)
    outcomes = rt.action('执行战役任务', processor.run_pending)
    if outcomes is rt.FAILED:
        return False

    campaign_done = [
        result
        for status, item, result in outcomes
        if status == 'done' and item.task_type == 'campaign'
    ]
    check_done = [
        item.task_type
        for status, item, _result in outcomes
        if status == 'done' and item.task_type in _CHECK_TYPES
    ]
    rt.note(f'事件流水: {events}')
    rt.check('战役完成次数一致', lambda: len(campaign_done) == args.times)
    if args.pause_at:
        rt.check('目标断点已触发', lambda: interrupted[0])
        rt.check('打断后回到首页', lambda: paused_page == [PageName.MAIN.value])
        rt.check('插入检查已完成', lambda: check_done == [args.check])
    rt.check('终态回到首页', lambda: identify_current_page(rt.ctx) == PageName.MAIN.value)
    return rt.state.failed == 0
