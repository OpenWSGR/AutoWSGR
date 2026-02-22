"""浴室修理操作。

涉及跨页面操作: 任意页面 → 后院 → 浴室 → 选择修理 (overlay)。

选择修理是浴室页面上的一个 overlay，打开后仍识别为浴室页面。
点击某个舰船进行修理后 overlay 自动关闭。

旧代码参考: ``game_operation.repair_by_bath``
"""

from __future__ import annotations

from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.ops.navigate import goto_page
from autowsgr.types import PageName
from autowsgr.ui.bath_page import BathPage


# ═══════════════════════════════════════════════════════════════════════════════
# 公开函数
# ═══════════════════════════════════════════════════════════════════════════════


def repair_in_bath(ctrl: AndroidController) -> None:
    """使用浴室修理修理时间最长的舰船。

    流程: 导航到浴室 → 打开选择修理 overlay → 点击第一个待修理舰船
    (overlay 自动关闭)。

    旧代码参考: ``repair_by_bath(timer)``
    """
    goto_page(ctrl, PageName.BATH)

    page = BathPage(ctrl)
    page.go_to_choose_repair()
    page.click_first_repair_ship()

    # 点击舰船后 overlay 自动关闭，已回到浴室页面
    logger.info("[OPS] 浴室修理操作完成")


def repair_ship_by_name(ctrl: AndroidController, ship_name: str) -> None:
    """使用浴室修理指定名称的舰船。

    .. note::
        当前为预留接口，依赖 BathPage.repair_ship() 的 OCR 实现。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。
    ship_name:
        要修理的舰船名称 (中文)。

    Raises
    ------
    NotImplementedError
        OCR 识别功能尚未实现。
    """
    goto_page(ctrl, PageName.BATH)

    page = BathPage(ctrl)
    page.go_to_choose_repair()
    page.repair_ship(ship_name)

    logger.info("[OPS] 浴室修理操作完成: {}", ship_name)
