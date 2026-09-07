"""链路自检 case — 最小可用示例: ADB 连接 + 截图 + 页面识别。

不动游戏状态 (建议配 ``--no-launch``), 30 秒验证 "设备 → 截图 → 识别" 全链路。
也是新 case 的最小模板: 复制本文件, 改 DESC 和 run() 即可。
"""

from __future__ import annotations

from typing import Any


# 一句话描述 (--list 时显示)
DESC = '链路自检: 连接 + 截图 + 页面识别 (建议 --no-launch)'


def run(rt: Any) -> bool:
    """执行链路自检步骤。"""
    from autowsgr.ui.page import get_current_page

    # 步骤1: 截图 (失败时框架自动截图存证并返回 rt.FAILED)
    screen = rt.action('截图', rt.ctx.ctrl.screenshot)
    if screen is rt.FAILED:
        return False

    # 步骤2: 识别当前页面
    page = rt.action('识别当前页面', get_current_page, screen)
    if page is rt.FAILED:
        return False

    rt.note(f'当前页面: {page}')
    return True
