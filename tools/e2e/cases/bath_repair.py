"""浴场修理链路 E2E — business.logistics.repair 实机验证。

验证链路契约: 首页 → 浴场 → 选择修理 overlay → 派修 → 回首页。
覆盖点:
    - goto_page 跨页导航 (浴场页位于 application/ui/controller/bath_page/)
    - 选择修理 overlay 开关机制 (点击舰船后自动关闭)
    - OCR 选船 (修理时间最长优先) + BathRoom 状态机 occupy

说明: repair_one_available 在无空闲槽时直接跳过 (不进页面), 属正常路径;
      返回 False 不算失败, 终态判定只看是否回到主页面。

用法::

    python tools/e2e/run.py bath_repair
"""

from __future__ import annotations


DESC = '浴场修理链路: 首页 → 浴场 → 派修 → 回首页'


def run(rt) -> bool:
    """执行浴场修理链路并验证终态契约。"""
    from autowsgr.application.ui.controller.main_page import MainPage
    from autowsgr.application.ui.navigation import identify_current_page
    from autowsgr.business.logistics.repair.bath_repair import repair_one_available

    ctx = rt.ctx

    # ① 主体: 调度入口版本的浴场修理 (状态机判断 + 循环派修 + 回主页)
    result = rt.action('执行 repair_one_available', repair_one_available, ctx)
    if result is rt.FAILED:
        return False
    rt.note(f'派修结果: {result} (False = 无空槽/无船可修, 属正常跳过)')

    # ② 终态契约验证: 回到主页面
    rt.check('终态: 主页面基础态', MainPage.is_base_page, ctx.ctrl.screenshot())
    rt.note(f'当前页面: {identify_current_page(ctx)}')
    return rt.state.failed == 0
