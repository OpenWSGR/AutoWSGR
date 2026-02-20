"""浴室修理操作。

涉及跨页面操作: 任意页面 → 后院 → 浴室 → 选择修理。

旧代码参考: ``game_operation.repair_by_bath``
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.ops.navigate import goto_page
from autowsgr.ui.bath_page import BathPage

_STEP_DELAY: float = 1.0
"""操作步骤间延迟 (秒)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 公开函数
# ═══════════════════════════════════════════════════════════════════════════════


def repair_in_bath(ctrl: AndroidController) -> None:
    """使用浴室修理修理时间最长的舰船。"""
    goto_page(ctrl, "浴室页面")

    page = BathPage(ctrl)
    page.go_to_choose_repair()
    time.sleep(_STEP_DELAY)

    page.click_first_repair_ship()
    time.sleep(_STEP_DELAY)

    logger.info("[OPS] 浴室修理操作完成")
