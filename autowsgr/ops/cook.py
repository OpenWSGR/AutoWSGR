"""食堂做菜操作。

涉及跨页面操作: 任意页面 → 后院 → 食堂 → 选菜谱 → 做菜。

旧代码参考: ``game_operation.cook``

- 导航到食堂页面
- 选择菜谱
- 使用图像模板匹配点击 "做菜" 按钮
- 处理 "效果正在生效" 和 "用餐次数已尽" 弹窗
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ops.image_resources import Templates
from autowsgr.ops.navigate import goto_page
from autowsgr.ui.canteen_page import CanteenPage
from autowsgr.vision.image_matcher import ImageChecker


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标常量 (参照旧代码)
# ═══════════════════════════════════════════════════════════════════════════════

_CLICK_FORCE_COOK: tuple[float, float] = (0.414, 0.628)
"""「效果正在生效」弹窗中选择继续做菜按钮。

旧代码: timer.relative_click(0.414, 0.628)
"""

_CLICK_CANCEL_COOK: tuple[float, float] = (0.65, 0.628)
"""「效果正在生效」弹窗中取消做菜按钮。

旧代码: timer.relative_click(0.65, 0.628)
"""

_CLICK_DISMISS_POPUP: tuple[float, float] = (0.788, 0.207)
"""关闭弹窗按钮。

旧代码: timer.relative_click(0.788, 0.207)
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════════════════════

_COOK_BUTTON_TIMEOUT: float = 7.5
"""等待做菜按钮出现的超时 (秒, 与旧代码一致)。"""


def _wait_and_click_template(
    ctrl: AndroidController,
    template,
    *,
    timeout: float = 5.0,
    interval: float = 0.3,
) -> bool:
    """等待指定模板出现并点击。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        screen = ctrl.screenshot()
        detail = ImageChecker.find_template(screen, template)
        if detail is not None:
            ctrl.click(*detail.center)
            return True
        time.sleep(interval)
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 公开函数
# ═══════════════════════════════════════════════════════════════════════════════


def cook(
    ctrl: AndroidController,
    *,
    position: int = 1,
    force_cook: bool = False,
) -> bool:
    """在食堂做菜。

    流程 (参照旧代码 ``cook``):

    1. 导航到食堂页面
    2. 选择菜谱
    3. 等待做菜按钮 (restaurant_image/cook.PNG) 出现并点击
    4. 如果出现 "效果正在生效" 弹窗:
       - ``force_cook=True``: 点击确认继续做菜
       - ``force_cook=False``: 取消做菜
    5. 如果出现 "用餐次数已尽" 弹窗: 关闭并返回 False

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    position:
        菜谱编号 (1–3)。
    force_cook:
        当有菜正在生效时是否继续做菜 (默认 False)。

    Returns
    -------
    bool
        做菜是否成功。

    Raises
    ------
    ValueError
        菜谱编号无效。
    """
    if position < 1 or position > 3:
        raise ValueError(f"菜谱编号必须为 1–3，收到: {position}")

    goto_page(ctrl, "食堂页面")

    page = CanteenPage(ctrl)
    page.select_recipe(position)

    # 等待做菜按钮出现并点击
    if not _wait_and_click_template(
        ctrl, Templates.Cook.COOK_BUTTON, timeout=_COOK_BUTTON_TIMEOUT
    ):
        logger.warning(
            "[OPS] 做菜按钮未出现 (菜谱 {}), 可能菜谱无效或次数用尽", position
        )
        return False

    time.sleep(0.5)

    # 检测 "效果正在生效" 弹窗
    screen = ctrl.screenshot()
    if ImageChecker.template_exists(screen, Templates.Cook.HAVE_COOK):
        logger.info("[OPS] 当前菜的效果正在生效")
        if force_cook:
            ctrl.click(*_CLICK_FORCE_COOK)
            time.sleep(0.5)
            # 检测 "用餐次数已尽"
            screen = ctrl.screenshot()
            if ImageChecker.template_exists(screen, Templates.Cook.NO_TIMES):
                logger.info("[OPS] 今日用餐次数已用尽")
                ctrl.click(*_CLICK_DISMISS_POPUP)
                return False
            logger.info("[OPS] 做菜成功 (菜谱 {})", position)
        else:
            ctrl.click(*_CLICK_CANCEL_COOK)
            logger.info("[OPS] 取消做菜 (效果正在生效)")
            time.sleep(0.3)
            ctrl.click(*_CLICK_DISMISS_POPUP)
            return False

    logger.info("[OPS] 做菜完成 (菜谱 {})", position)
    return True
