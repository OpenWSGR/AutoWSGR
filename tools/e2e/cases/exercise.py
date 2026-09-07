"""演习断点打断 E2E — 处理器暂停 + 后勤检查插入 + 重跑计数。

验证用户敲定的五个场景 (一次运行验证一个断点场景, 演习对手打完即无):
    1. --pause-at panel_ready      导航结束后暂停 → 插后勤检查 → 回主页
    2. --pause-at formation_entered 进入编队后暂停 → 插后勤检查 → 回主页
    3. --pause-at ship_selected    选船完成后暂停 → 插后勤检查 → 回主页
    4. --pause-at before_start     出征前暂停 → 插后勤检查 → 回主页
    5. --pause-at rival_done       战斗完成后暂停 (计数保留) → 插后勤检查 → 回主页
    6. 不带 --pause-at              直接跑完并统计计数

多轮模式 (--rounds N):
    每个请求只挑战一个对手，默认按 2,3 队伍循环；前两轮连续执行，
    第二轮后插入一次后勤任务验证非连续导航。``--rounds 6`` 用于完整六轮验证。

接力模式 (--relay):
    同一趟演习里依次覆盖导航入口、进入编队、一次选船、出征前和战斗结束
    五个交接断点，每次插入一次后勤检查并自动恢复; 配合 --with-init
    在演习前先跑初始化链路 (含每日浮层清理)。

核心语义 (2026-08 用户敲定): 一次提交 = 持续打到没有对手 (以「打一个」
为基础单元循环); 每打完一个对手计数 +1; 中间被更高优先级任务打断时在断点
暂停 → 高优任务执行 → 恢复后接着打剩余的 → 直到没有对手。

打断机制: 事件回调里收到目标事件 → processor.interrupt(后勤检查请求)
→ 演习执行器在最近的 _wait 断点回主页、抛 TaskPaused → 处理器清信号、
重排队 → 后勤检查先跑 → 演习重跑 (已打对手变灰自动跳过, 计数保留)。

用法::

    # 场景4: 打完一个对手后打断一次
    python tools/e2e/run.py --with-ocr exercise --pause-at rival_done

    # 场景5: 不打断, 跑完全部并统计
    python tools/e2e/run.py --with-ocr exercise

    # 接力: 初始化(清弹窗) → 五类断点各插一次后勤检查 → 打完
    python tools/e2e/run.py --with-ocr exercise --relay --with-init

    # 换计划 YAML
    python tools/e2e/run.py --with-ocr exercise --yaml <路径>

    # 六轮演习: 五个断点 + 队伍 2/3 切换 + 连续/非连续导航
    python tools/e2e/run.py --with-ocr --fast-ocr exercise --rounds 6 \
        --fleet-sequence 2,3 --continuous-rounds 2 --relay --with-init \
        --checks expedition_check,reward_check,expedition_check,reward_check,expedition_check
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    import argparse

DESC = '演习: 断点/多轮队伍切换/任务衔接验证 (需 --with-ocr)'

# 默认计划: GUI 系统预设的队伍2演习 (用户提供的驱动 YAML)
_DEFAULT_YAML = str(
    Path(__file__).resolve().parents[3] / 'testing' / 'fixtures' / 'exercise_team2.yaml'
)

# 可单独验证的断点事件；旧的 rival_confirmed/fleet_ready 继续保留兼容。
_BREAKPOINTS = (
    'panel_ready',
    'rival_confirmed',
    'formation_entered',
    'fleet_ready',
    'ship_selected',
    'before_start',
    'rival_done',
)

# 接力模式覆盖用户要求的五类交接节点；每类只在第一次上报时触发。
_RELAY_PAUSES = (
    'panel_ready',
    'formation_entered',
    'ship_selected',
    'before_start',
    'rival_done',
)

_CHECK_TYPES = ('expedition_check', 'reward_check')


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """定义 case 专属命令行参数。"""
    parser.add_argument('--yaml', default=_DEFAULT_YAML, help='演习计划 YAML 路径')
    parser.add_argument('--fleet-id', type=int, default=None, help='仅本次 E2E 覆盖舰队编号')
    parser.add_argument(
        '--ship-name-alias',
        action='append',
        default=[],
        metavar='CUSTOM=STANDARD',
        help='用户舰名映射，可重复传入',
    )
    parser.add_argument(
        '--rivals-limit',
        type=int,
        default=None,
        help='仅本次 E2E 限制挑战对手数量，便于分次验证',
    )
    parser.add_argument(
        '--pause-at',
        choices=_BREAKPOINTS,
        default=None,
        help='在哪个断点触发处理器打断 (不指定 = 不打断直接跑完)',
    )
    parser.add_argument(
        '--relay',
        action='store_true',
        help='接力模式: 五类交接断点依次各打断一次',
    )
    parser.add_argument(
        '--with-init',
        action='store_true',
        help='演习前先跑初始化链路 (任意状态 → 首页 + 每日浮层清理)',
    )
    parser.add_argument(
        '--check',
        choices=('expedition_check', 'reward_check'),
        default='expedition_check',
        help='断点插入的后勤检查任务 (默认: expedition_check)',
    )
    parser.add_argument(
        '--checks',
        default=None,
        help='接力模式按断点顺序插入的检查任务, 逗号分隔 (共 5 项)',
    )
    parser.add_argument('--rounds', type=int, default=1, help='按单场请求执行的演习轮数 (最多 6)')
    parser.add_argument(
        '--fleet-sequence',
        default='2,3',
        help='多轮模式循环使用的队伍编号，例如 2,3',
    )
    parser.add_argument(
        '--continuous-rounds',
        type=int,
        default=2,
        help='多轮模式中连续任务阶段的轮数',
    )


def _resolve_checks(args: Any) -> tuple[str, ...]:
    """解析断点检查序列; 未指定序列时保留旧的单检查行为。"""
    raw = getattr(args, 'checks', None)
    if raw is None:
        checks = (args.check,) * len(_RELAY_PAUSES) if args.relay else (args.check,)
    else:
        checks = tuple(item.strip() for item in raw.split(',') if item.strip())
    if any(check not in _CHECK_TYPES for check in checks):
        raise ValueError(f'检查任务必须属于: {", ".join(_CHECK_TYPES)}')
    expected = len(_RELAY_PAUSES) if args.relay else 1
    if len(checks) != expected:
        raise ValueError(f'当前模式需要 {expected} 个检查任务, 收到 {len(checks)} 个')
    return checks


def _resolve_rounds(args: Any) -> tuple[int, tuple[int, ...], int]:
    """校验多轮演习的次数、队伍循环和连续阶段边界。"""
    rounds = int(getattr(args, 'rounds', 1))
    if not 1 <= rounds <= 6:
        raise ValueError('rounds 必须在 1-6 范围内')
    sequence = tuple(
        int(value.strip())
        for value in str(getattr(args, 'fleet_sequence', '2,3')).split(',')
        if value.strip()
    )
    if not sequence or any(fleet_id not in range(1, 5) for fleet_id in sequence):
        raise ValueError('fleet-sequence 必须是 1-4 的队伍编号列表')
    continuous = int(getattr(args, 'continuous_rounds', 2))
    if not 1 <= continuous < rounds:
        raise ValueError('continuous-rounds 必须小于 rounds 且至少为 1')
    return rounds, sequence, continuous


def _collect_aliases(ctx: Any, args: Any) -> dict[str, str] | None:
    """合并用户配置和命令行舰名映射。"""
    ocr_config = getattr(getattr(ctx, 'config', None), 'ocr', None)
    aliases = dict(getattr(ocr_config, 'ship_name_aliases', {}) or {})
    for value in args.ship_name_alias:
        alias, separator, standard = value.partition('=')
        if not separator or not alias.strip() or not standard.strip():
            return None
        aliases[alias.strip()] = standard.strip()
    return aliases


def _run_multiple_rounds(  # noqa: PLR0915 - one E2E case owns the full scenario assertions
    rt: Any,
    ctx: Any,
    args: Any,
    aliases: dict[str, str],
    checks: tuple[str, ...],
) -> bool:
    """提交多个单场请求，验证队伍切换和连续/非连续任务衔接。"""
    from autowsgr.application.ui.navigation import identify_current_page
    from autowsgr.common.types import PageName
    from autowsgr.dispatch.processor import Processor, Request

    rounds, fleet_sequence, continuous_rounds = _resolve_rounds(args)
    processor = Processor(ctx)
    requests: list[Request] = []
    request_index: dict[str, int] = {}
    events: list[tuple[str, dict[str, Any]]] = []
    snapshots: dict[str, Any] = {
        'paused_pages': [],
        'paused_rounds': [],
        'round_start_pages': [],
        'noncontinuous_check': False,
    }

    for round_number in range(1, rounds + 1):
        fleet_id = fleet_sequence[(round_number - 1) % len(fleet_sequence)]
        request = rt.action(
            f'加载第 {round_number} 轮演习 YAML（队伍 {fleet_id}）',
            Request.from_yaml,
            args.yaml,
            source='cli',
            ship_name_aliases=aliases,
        )
        if request is rt.FAILED:
            return False
        request = replace(
            request,
            params={
                **request.params,
                'fleet_id': fleet_id,
                'rivals_limit': 1,
            },
        )
        requests.append(request)
        request_index[request.request_id] = round_number

    relay_index = [0]
    relay_fired = [False] * len(_RELAY_PAUSES)
    scheduled_rounds = {1}

    def interrupt_now(event: str, check: str) -> None:
        rt.note(f'>> 断点 [{event}] 触发后勤任务: {check}')
        processor.interrupt(Request(task_type=check, source='dependency'))

    def on_event(event: str, **data: Any) -> None:
        events.append((event, dict(data)))
        round_number = request_index.get(str(data.get('task_id', '')))
        if event == 'running' and data.get('task_type') == 'exercise':
            page = identify_current_page(ctx)
            snapshots['round_start_pages'].append((round_number, page))
        if event == 'paused':
            page = identify_current_page(ctx)
            snapshots['paused_pages'].append(page)
            snapshots['paused_rounds'].append(round_number)
        if args.relay:
            index = relay_index[0]
            if (
                index < len(_RELAY_PAUSES)
                and event == _RELAY_PAUSES[index]
                and not relay_fired[index]
            ):
                relay_fired[index] = True
                relay_index[0] = index + 1
                interrupt_now(event, checks[index])
        if (
            event == 'completed'
            and data.get('task_type') == 'exercise'
            and round_number is not None
            and round_number < rounds
            and round_number + 1 not in scheduled_rounds
        ):
            if round_number == continuous_rounds and not snapshots['noncontinuous_check']:
                snapshots['noncontinuous_check'] = True
                processor.submit(Request(task_type=args.check, source='dependency'))
                rt.note('>> 连续任务阶段结束，插入后勤任务验证非连续导航')
            processor.submit(requests[round_number])
            scheduled_rounds.add(round_number + 1)

    processor.on_event = on_event
    processor.submit(requests[0])
    outcomes = rt.action(f'执行{rounds}轮单场演习任务', processor.run_pending)
    if outcomes is rt.FAILED:
        return False

    done_exercises = [
        (request, result)
        for status, request, result in outcomes
        if status == 'done' and request.task_type == 'exercise'
    ]
    done_types = [request.task_type for status, request, _ in outcomes if status == 'done']
    expected_fleets = [fleet_sequence[i % len(fleet_sequence)] for i in range(rounds)]
    actual_fleets = [request.params.get('fleet_id') for request, _ in done_exercises]

    rt.note(f'{rounds}轮事件流水: {[event for event, _ in events]}')
    rt.note(f'任务完成流水: {done_types}')
    rt.check(f'{rounds}轮演习全部完成', lambda: len(done_exercises) == rounds)
    rt.check(
        '每轮只挑战一个对手',
        lambda: all(isinstance(result, list) and len(result) == 1 for _, result in done_exercises),
    )
    rt.check('队伍按 2→3 循环切换', lambda: actual_fleets == expected_fleets)
    rt.check(
        '连续任务阶段导航从首页开始',
        lambda: all(page == PageName.MAIN for _, page in snapshots['round_start_pages']),
    )
    rt.check(
        '连续任务存在相邻演习请求',
        lambda: any(
            done_types[i : i + 2] == ['exercise', 'exercise'] for i in range(len(done_types) - 1)
        ),
    )
    rt.check(
        '非连续任务经过后勤检查',
        lambda: (
            snapshots['noncontinuous_check']
            and any(
                done_types[i] == 'exercise'
                and done_types[i + 1] in _CHECK_TYPES
                and done_types[i + 2] == 'exercise'
                for i in range(len(done_types) - 2)
            )
        ),
    )
    if args.relay:
        rt.check('五个断点全部触发', lambda: all(relay_fired))
        rt.check(
            '断点暂停均回到首页',
            lambda: (
                len(snapshots['paused_pages']) >= len(_RELAY_PAUSES)
                and all(page == PageName.MAIN for page in snapshots['paused_pages'])
            ),
        )
        completed_checks = [
            request.task_type
            for status, request, _ in outcomes
            if status == 'done' and request.task_type in _CHECK_TYPES
        ]
        rt.check(
            '断点后勤检查按顺序执行',
            lambda: completed_checks[: len(checks)] == list(checks),
        )
    rt.check(f'{rounds}轮任务最终回到首页', lambda: identify_current_page(ctx) == PageName.MAIN)
    return rt.state.failed == 0


def run(rt: Any) -> bool:  # noqa: C901, PLR0912, PLR0915 - one E2E case owns its assertions
    """执行演习断点打断验证 (单断点 / 接力 / 可带初始化前置)。"""
    from autowsgr.application.ui.navigation import identify_current_page
    from autowsgr.common.types import PageName
    from autowsgr.dispatch.processor import Processor, Request

    args = rt.args
    ctx = rt.ctx
    checks = _resolve_checks(args)
    rounds = int(getattr(args, 'rounds', 1))
    rt.note(f'计划: {args.yaml}')
    if args.relay:
        rt.note(f'模式: 接力 ({">".join(_RELAY_PAUSES)})')
    else:
        rt.note(f'打断点: {args.pause_at or "(不打断, 场景5)"}')
    rt.note(f'插入检查: {checks}')

    # ── 阶段零 (可选): 初始化链路 + 每日浮层清理 ────────────────
    if args.with_init:
        from autowsgr.application.runtime.initialize.initialize import initialize
        from autowsgr.application.ui.controller.main_page import MainPage
        from autowsgr.application.ui.controller.main_page.overlays import detect_overlay

        if rt.action('初始化 (任意状态 → 首页 + 清浮层)', initialize, ctx) is rt.FAILED:
            return False
        rt.check('初始化后: 主页面基础态', MainPage.is_base_page, ctx.ctrl.screenshot())
        rt.check(
            '初始化后: 无浮层残留',
            lambda: detect_overlay(ctx.ctrl.screenshot()) is None,
        )

    # ── 准备: 演习请求 (YAML 驱动) + 处理器 ─────────────────────
    aliases = _collect_aliases(ctx, args)
    if aliases is None:
        rt.note('无效舰名映射')
        return False
    if rounds > 1:
        return _run_multiple_rounds(rt, ctx, args, aliases, checks)
    exercise_req = rt.action(
        '加载演习计划 YAML',
        Request.from_yaml,
        args.yaml,
        source='cli',
        ship_name_aliases=aliases,
    )
    if exercise_req is rt.FAILED:
        return False
    overrides: dict[str, Any] = {}
    if args.fleet_id is not None:
        overrides['fleet_id'] = args.fleet_id
    if args.rivals_limit is not None:
        overrides['rivals_limit'] = args.rivals_limit
    if overrides:
        exercise_req = replace(
            exercise_req,
            params={**exercise_req.params, **overrides},
        )
    rt.note(f'task_type={exercise_req.task_type} params={exercise_req.params} → 持续打到没有对手')

    processor = Processor(ctx)
    events: list[tuple[str, dict]] = []  # 事件流水 (供断言与人工核对)
    snapshots: dict[str, Any] = {}  # 关键时刻的状态快照
    # 接力模式: 当前断点队列下标 + 各断点是否已触发 (重跑会重复上报事件)
    relay_index = [0]
    relay_fired: list[bool] = [False] * len(_RELAY_PAUSES)

    def interrupt_now(event: str, check: str) -> None:
        """在断点插入后勤检查 (处理器加急)。"""
        rt.note(f'>> 断点 [{event}] 触发处理器加急: 插入 {check}')
        processor.interrupt(Request(task_type=check, source='dependency'))

    def on_event(event: str, **data: Any) -> None:
        events.append((event, dict(data)))
        if event == 'paused':
            # paused 上报发生在回主页之后 → 立即验证锚点铁律
            page = identify_current_page(ctx)
            fought = exercise_req.progress.get('fought', 0)
            if args.relay:
                snapshots.setdefault('paused_pages', []).append(page)
                snapshots.setdefault('paused_fought', []).append(fought)
            else:
                snapshots['paused_page'] = page
                snapshots['paused_fought'] = fought
        if args.relay:
            # 依次消费断点队列: 每个断点只在第一次上报时触发
            idx = relay_index[0]
            if idx < len(_RELAY_PAUSES) and event == _RELAY_PAUSES[idx] and not relay_fired[idx]:
                relay_fired[idx] = True
                relay_index[0] = idx + 1
                interrupt_now(event, checks[idx])
        elif event == args.pause_at and not snapshots.get('interrupted'):
            # 到达目标断点 → 模拟下游依赖加急插入后勤检查
            snapshots['interrupted'] = True
            interrupt_now(event, checks[0])

    processor.on_event = on_event

    # ── 阶段一: 首次提交 (可能被断点打断后恢复) ──────────────────
    processor.submit(exercise_req)
    outcomes = rt.action('首次提交 (演习 + 可能的打断恢复)', processor.run_pending)
    if outcomes is rt.FAILED:
        return False

    status_flow = [(status, req.task_type) for status, req, _ in outcomes]
    rt.note(f'执行流: {status_flow}')
    rt.note(f'事件流水: {[e for e, _ in events]}')

    if args.relay:
        # 接力模式: 演习暂停 x5 → 后勤检查 x5 → 演习重跑完成
        expected_flow: list[tuple[str, str]] = []
        for check in checks:
            expected_flow += [('paused', 'exercise'), ('done', check)]
        expected_flow.append(('done', 'exercise'))
        rt.check('执行流 = (暂停→后勤检查) x5 → 重跑完成', lambda: status_flow == expected_flow)
        rt.check('五个交接断点全部触发过', lambda: all(relay_fired))
        paused_pages = snapshots.get('paused_pages', [])
        rt.check(
            '每次打断都在主页面 (锚点铁律)',
            lambda: (
                len(paused_pages) == len(_RELAY_PAUSES)
                and all(page == PageName.MAIN for page in paused_pages)
            ),
        )
    elif args.pause_at:
        # 打断场景: 演习暂停 → 后勤检查先跑 → 演习重跑完成
        rt.check(
            '执行流 = 暂停 → 后勤检查 → 重跑完成',
            lambda: (
                status_flow == [('paused', 'exercise'), ('done', checks[0]), ('done', 'exercise')]
            ),
        )
        rt.check(
            '打断时已回到主页面 (锚点铁律)', lambda: snapshots.get('paused_page') == PageName.MAIN
        )
        rt.check(f'打断点 [{args.pause_at}] 确实触发过', lambda: bool(snapshots.get('interrupted')))
        if args.pause_at == 'rival_done':
            # 战斗完成后打断: 计数已保留 (打过的那一场不丢)
            rt.check(
                '打断时计数已保留 (fought >= 1)', lambda: snapshots.get('paused_fought', 0) >= 1
            )
    else:
        # 场景5: 不打断, 一趟完成
        rt.check('执行流 = 单趟完成', lambda: status_flow == [('done', 'exercise')])

    # ── 计数统计: 一次提交打光全部 (rival_done 逐场累计) ─────────
    done_results = next(
        (r for s, req, r in outcomes if s == 'done' and req.task_type == 'exercise'),
        [],
    )
    total = exercise_req.progress.get('fought', 0)
    # 最后一次打断时的保留计数 (接力 = 打一场后; 单断点 = 该断点时刻; 无打断 = 0)
    paused_fought = (
        snapshots.get('paused_fought', [0])[-1] if args.relay else snapshots.get('paused_fought', 0)
    )
    rt.note(
        f'计数统计: 本任务共打 {total} 场 '
        f'(打断时已保留 {paused_fought} 场, 重跑补打 {len(done_results)} 场)',
    )
    if total == 0:
        # 无可挑战对手 (今日该时段已打完) — 空完成本身是正确行为, 不算失败
        rt.note('无可挑战对手 (今日该时段已打完), 空完成收尾属正常')
    else:
        rt.check(
            '每场战斗都有 rival_done 计数 (一场一计)',
            lambda: len(done_results) == total - paused_fought,
        )
    rt.check('累计计数 = 暂停保留 + 重跑场数', lambda: total == paused_fought + len(done_results))

    # 后勤检查执行过 (打断场景) 且终态回主页
    if args.relay or args.pause_at:
        rt.check(
            '后勤检查按断点顺序执行',
            lambda: (
                [
                    req.task_type
                    for status, req, _ in outcomes
                    if status == 'done' and req.task_type in _CHECK_TYPES
                ]
                == list(checks)
            ),
        )
    rt.check('终态: 主页面', lambda: identify_current_page(ctx) == PageName.MAIN)

    return rt.state.failed == 0
