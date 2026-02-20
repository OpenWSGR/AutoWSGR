"""远征操作。

涉及跨页面操作: 任意页面 → 地图页面(远征面板) → 收取/派遣。

旧代码参考: ``game/expedition.py``

- 检测远征通知 (橙色圆点)
- 进入远征面板
- 收取已完成远征
- 使用确认弹窗模板处理收取后的确认
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ops.image_resources import Templates
from autowsgr.ops.navigate import goto_page
from autowsgr.ui.main_page import MainPage
from autowsgr.ui.map_page import MapPage, MapPanel
from autowsgr.vision.image_matcher import ImageChecker


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标常量
# ═══════════════════════════════════════════════════════════════════════════════

_CLICK_SCREEN_CENTER: tuple[float, float] = (0.5, 0.5)
"""屏幕中央 — 用于跳过动画和确认弹窗。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════════════════════


def _try_collect_and_redispatch(ctrl: AndroidController) -> int:
    """尝试收取远征并重新派遣。

    在远征面板中反复点击已完成远征的收取按钮，
    然后确认重新派遣。此过程使用确认弹窗模板来确认操作。

    Returns
    -------
    int
        收取的远征数量。
    """
    collected = 0
    max_attempts = 6  # 最多 4 支远征队 + 冗余

    for _ in range(max_attempts):
        screen = ctrl.screenshot()

        # 检查是否还有远征通知
        has_notif = MapPage.has_expedition_notification(screen)
        if not has_notif and collected > 0:
            break

        # 点击远征面板中确认弹窗 (收取/重新派遣)
        detail = ImageChecker.find_any(screen, Templates.Confirm.all())
        if detail is not None:
            ctrl.click(*detail.center)
            time.sleep(1.0)
            collected += 1
            continue

        # 如果有通知但没找到确认按钮, 点击屏幕尝试触发
        if has_notif:
            ctrl.click(*_CLICK_SCREEN_CENTER)
            time.sleep(1.0)
        else:
            break

    return collected


# ═══════════════════════════════════════════════════════════════════════════════
# 公开函数
# ═══════════════════════════════════════════════════════════════════════════════


def collect_expedition(ctrl: AndroidController) -> bool:
    """收取已完成的远征。

    流程 (参照旧代码 ``Expedition.run``):

    1. 回到主页面, 检测远征通知
    2. 导航到地图页面远征面板
    3. 反复尝试收取并确认重新派遣
    4. 返回主页面

    Parameters
    ----------
    ctrl:
        Android 设备控制器。

    Returns
    -------
    bool
        是否执行了收取操作。
    """
    # 先在主页面检测是否有远征完成
    goto_page(ctrl, "主页面")
    screen = ctrl.screenshot()
    if not MainPage.has_expedition_ready(screen):
        logger.info("[OPS] 无已完成的远征")
        return False

    # 导航到地图页面
    goto_page(ctrl, "地图页面")
    time.sleep(0.5)

    page = MapPage(ctrl)

    # 确认远征通知
    screen = ctrl.screenshot()
    if not MapPage.has_expedition_notification(screen):
        logger.info("[OPS] 地图页面无远征通知")
        goto_page(ctrl, "主页面")
        return False

    # 切换到远征面板
    page.switch_panel(MapPanel.EXPEDITION)
    time.sleep(1.0)

    # 收取远征
    collected = _try_collect_and_redispatch(ctrl)

    if collected > 0:
        logger.info("[OPS] 远征收取完成, 共收取 {} 支远征队", collected)
    else:
        logger.info("[OPS] 未能收取任何远征")

    goto_page(ctrl, "主页面")
    return collected > 0
