"""浴室修理操作。

涉及跨页面操作: 任意页面 → 后院 → 浴室 → 选择修理。

旧代码参考: ``game_operation.repair_by_bath``

- 导航到浴室页面
- 进入选择修理
- 点击第一个舰船进行修理
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ops.navigate import goto_page
from autowsgr.ui.bath_page import BathPage


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标常量 (参照旧代码 repair_by_bath)
# ═══════════════════════════════════════════════════════════════════════════════

_CLICK_FIRST_SHIP: tuple[float, float] = (0.1198, 0.4315)
"""选择修理页面中第一个舰船的位置。

旧代码: timer.click(115, 233) → (115/960, 233/540).
"""

_STEP_DELAY: float = 1.0
"""操作步骤间延迟 (秒)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 公开函数
# ═══════════════════════════════════════════════════════════════════════════════


def repair_in_bath(ctrl: AndroidController) -> None:
    """使用浴室修理修理时间最长的舰船。

    流程 (参照旧代码 ``repair_by_bath``):

    1. 导航到浴室页面
    2. 进入选择修理
    3. 点击第一个舰船 (修理时间最长的自动排在第一个)

    Parameters
    ----------
    ctrl:
        Android 设备控制器。

    .. note::
        旧代码在点击后会检测页面状态来判断修理是否成功:
        - 若仍在选择修理页面 → 操作成功, 可继续修理
        - 若返回到浴室页面 → 操作完成 (无更多可修理的舰船)
        当前版本仅执行点击操作。
    """
    goto_page(ctrl, "浴室页面")

    page = BathPage(ctrl)
    page.go_to_choose_repair()
    time.sleep(_STEP_DELAY)

    # 点击第一个舰船
    ctrl.click(*_CLICK_FIRST_SHIP)
    time.sleep(_STEP_DELAY)

    # 检查是否回到浴室页面 (表示修理已启动或无可修理舰船)
    screen = ctrl.screenshot()
    if BathPage.is_current_page(screen):
        logger.info("[OPS] 浴室修理完成 (已返回浴室页面)")
    else:
        logger.info("[OPS] 浴室修理: 已选择舰船修理")
