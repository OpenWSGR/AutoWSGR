"""初始化链路 E2E — application.runtime.initialize 实机验证。

验证终态契约: 任意状态 → [首页 + 浮层已清 + 待机]。
配合 ``--no-launch`` 使用 (跳过框架自己的 ensure_ready, 让 initialize 全权处理):
- 默认: 游戏保持当前状态, 验证分支 1/2 (已在首页 / 游戏内导航回首页)
- ``--cold``: 先强杀游戏, 验证完整冷启动分支 3 (启动 → 进入 → 首页 → 清浮层)

用法::

    python tools/e2e/run.py --no-launch initialize
    python tools/e2e/run.py --no-launch initialize --cold
"""

from __future__ import annotations

import time


DESC = '初始化链路: 任意状态 → 首页待机 (SL 兜底)'


def add_arguments(parser) -> None:
    """case 专属参数。"""
    parser.add_argument('--cold', action='store_true', help='先强杀游戏再初始化 (测冷启动分支)')


def run(rt) -> bool:
    """执行初始化链路并验证终态契约。"""
    from autowsgr.application.runtime.initialize.initialize import _package_of, initialize
    from autowsgr.application.ui.controller.main_page import MainPage
    from autowsgr.application.ui.controller.main_page.overlays import detect_overlay
    from autowsgr.application.ui.navigation import identify_current_page

    ctx = rt.ctx

    # ① 初始状态记录 (对照用, 不参与判定)
    start_page = rt.action('识别初始页面', identify_current_page, ctx)
    if start_page is not rt.FAILED:
        rt.note(f'初始页面: {start_page}')

    # ② --cold: 强杀游戏 → 强制走冷启动分支
    if rt.args.cold:
        package = _package_of(ctx)
        if rt.action(f'强杀游戏 ({package})', ctx.ctrl.stop_app, package) is rt.FAILED:
            return False
        time.sleep(2.0)

    # ③ 主体: initialize (内部含三分支判定 + SL 兜底)
    if rt.action('执行 initialize', initialize, ctx) is rt.FAILED:
        return False

    # ④ 终态契约验证: 首页 + 浮层已清
    rt.check('终态: 主页面基础态', MainPage.is_base_page, ctx.ctrl.screenshot())
    rt.check('终态: 无浮层残留', lambda: detect_overlay(ctx.ctrl.screenshot()) is None)
    return rt.state.failed == 0
