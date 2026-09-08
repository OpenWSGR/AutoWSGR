"""奖励收取 E2E — reward_check 执行器 (处理器路径) + 兼容层 collect_rewards。

验证:
    1. 处理器路径: 提交 ``reward_check`` → 执行流 = [('done', 'reward_check')],
       事件流水含 ``checked``, 终态回主页 (锚点铁律)。
    2. 兼容层路径: 直接调 ``collect_rewards(ctx)`` (auto_daily 定时器的调用方式),
       返回 bool, 调用后仍在主页。

无任务红点时执行器在主页空跑返回 (collected=0), 属正常安全行为;
断言只要求链路正确走完, 不要求本次一定收没收到奖励。

用法::

    # 直接验证 (不初始化)
    python tools/e2e/run.py reward

    # 先跑初始化链路 (任意状态 → 首页 + 每日浮层清理)
    python tools/e2e/run.py reward --with-init
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    import argparse

DESC = '奖励收取: reward_check 执行器 + 兼容层 collect_rewards'


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """定义 case 专属命令行参数。"""
    parser.add_argument(
        '--with-init',
        action='store_true',
        help='验证前先跑初始化链路 (任意状态 → 首页 + 每日浮层清理)',
    )


def run(rt: Any) -> bool:
    """执行奖励收取验证: 处理器路径 → 兼容层路径 → 锚点断言。"""
    from autowsgr.application.ui.navigation import identify_current_page
    from autowsgr.business.logistics.reward import collect_rewards
    from autowsgr.common.types import PageName
    from autowsgr.dispatch.processor import Processor, Request

    ctx = rt.ctx

    # ── 阶段零 (可选): 初始化链路 + 每日浮层清理 ────────────────
    if rt.args.with_init:
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

    # ── 阶段一: 处理器路径 (submit → run_pending) ────────────────
    req = Request(task_type='reward_check', source='cli')
    events: list[str] = []

    def on_event(event: str, **data: Any) -> None:  # noqa: ARG001
        events.append(event)

    processor = Processor(ctx, on_event=on_event)
    processor.submit(req)
    outcomes = rt.action('提交 reward_check → 处理器执行', processor.run_pending)
    if outcomes is rt.FAILED:
        return False

    status_flow = [(status, r.task_type) for status, r, _ in outcomes]
    rt.note(f'执行流: {status_flow}')
    rt.note(f'事件流水: {events}')

    rt.check(
        '执行流 = 单趟完成 (reward_check)',
        lambda: status_flow == [('done', 'reward_check')],
    )
    rt.check('上报了 checked 事件', lambda: 'checked' in events)
    rt.check(
        'checked 事件只有一次 (短链路不重跑)',
        lambda: events.count('checked') == 1,
    )
    rt.check('终态: 主页面', lambda: identify_current_page(ctx) == PageName.MAIN)

    # ── 阶段二: 兼容层路径 (auto_daily 的调用方式) ───────────────
    result = rt.action('兼容层 collect_rewards(ctx)', collect_rewards, ctx)
    if result is rt.FAILED:
        return False
    rt.check('collect_rewards 返回 bool', lambda: isinstance(result, bool))
    rt.check('兼容层调用后仍在主页面', lambda: identify_current_page(ctx) == PageName.MAIN)

    return rt.state.failed == 0
