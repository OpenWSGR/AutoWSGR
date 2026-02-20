"""任务奖励收取。

涉及跨页面操作: 主页 → 任务页 → 领取 → 返回。

旧代码参考: ``game_operation.get_rewards``

- 检测主页面任务通知
- 进入任务页面
- 使用图像模板匹配点击 "一键领取" 或 "单个领取"
- 点击确认弹窗
- 返回主页面
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ops.image_resources import Templates
from autowsgr.ops.navigate import goto_page
from autowsgr.ui.main_page import MainPage
from autowsgr.vision.image_matcher import ImageChecker


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════════════════════

_CONFIRM_CLICK: tuple[float, float] = (0.5, 0.5)
"""确认弹窗默认点击位置 (屏幕中央)。"""


def _try_confirm(ctrl: AndroidController, *, timeout: float = 5.0) -> bool:
    """尝试点击确认弹窗。

    在 *timeout* 秒内反复截图检测确认弹窗模板，
    若匹配则点击确认并返回 ``True``。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    timeout:
        最大等待秒数。

    Returns
    -------
    bool
        是否成功点击了确认。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        screen = ctrl.screenshot()
        detail = ImageChecker.find_any(screen, Templates.Confirm.all())
        if detail is not None:
            ctrl.click(*detail.center)
            logger.debug("[OPS] 确认弹窗已点击")
            time.sleep(0.5)
            return True
        time.sleep(0.3)
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 公开函数
# ═══════════════════════════════════════════════════════════════════════════════


def collect_rewards(ctrl: AndroidController) -> bool:
    """检查并收取任务奖励。

    流程 (参照旧代码 ``get_rewards``):

    1. 回到主页面
    2. 检测是否有可领取的任务 (主页面红点)
    3. 进入任务页面
    4. 尝试点击 "一键领取" 按钮 (game_ui[15])
    5. 若不存在, 尝试点击 "单个领取" 按钮 (game_ui[12])
    6. 点击确认弹窗
    7. 返回主页面

    Parameters
    ----------
    ctrl:
        Android 设备控制器。

    Returns
    -------
    bool
        是否成功领取了奖励。
    """
    goto_page(ctrl, "主页面")

    screen = ctrl.screenshot()
    if not MainPage.has_task_ready(screen):
        logger.info("[OPS] 无可领取的任务奖励")
        return False

    # 导航到任务页面
    goto_page(ctrl, "任务页面")
    time.sleep(0.5)

    # 尝试点击 "一键领取"
    screen = ctrl.screenshot()
    detail = ImageChecker.find_template(screen, Templates.GameUI.REWARD_COLLECT_ALL)
    if detail is not None:
        ctrl.click(*detail.center)
        logger.info("[OPS] 点击一键领取")
        time.sleep(0.5)
        # 领取后点击屏幕中央确认
        ctrl.click(0.5, 0.5)
        time.sleep(0.3)
        _try_confirm(ctrl, timeout=5.0)
        goto_page(ctrl, "主页面")
        return True

    # 尝试点击 "单个领取"
    screen = ctrl.screenshot()
    detail = ImageChecker.find_template(screen, Templates.GameUI.REWARD_COLLECT)
    if detail is not None:
        ctrl.click(*detail.center)
        logger.info("[OPS] 点击单个领取")
        time.sleep(0.5)
        _try_confirm(ctrl, timeout=5.0)
        goto_page(ctrl, "主页面")
        return True

    logger.info("[OPS] 任务页面未找到领取按钮")
    goto_page(ctrl, "主页面")
    return False
