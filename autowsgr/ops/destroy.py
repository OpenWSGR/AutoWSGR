"""解装舰船操作。

涉及跨页面操作: 任意页面 → 侧边栏 → 建造(解体标签) → 解装 → 返回。

旧代码参考: ``game_operation.destroy_ship``

- 导航到建造页面解体标签
- 点击添加
- 选择舰船类型 (可选)
- 快速选择
- 确认解装
- 卸下装备 (可选)
- 返回主页面
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ops.navigate import goto_page
from autowsgr.ui.build_page import BuildPage, BuildTab


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标常量 (参照旧代码 destroy_ship)
# ═══════════════════════════════════════════════════════════════════════════════

# 绝对坐标 → 相对坐标 (除以 960×540)
_CLICK_ADD: tuple[float, float] = (0.0938, 0.3815)
"""点击添加按钮。旧代码: timer.click(90, 206)"""

_CLICK_SHIP_TYPE_FILTER: tuple[float, float] = (0.912, 0.681)
"""打开舰船类型过滤器。"""

_CLICK_CONFIRM_FILTER: tuple[float, float] = (0.9, 0.85)
"""确认舰船类型过滤。"""

_CLICK_QUICK_SELECT: tuple[float, float] = (0.91, 0.3)
"""快速选择按钮。旧代码: timer.relative_click(0.91, 0.3)"""

_CLICK_CONFIRM_SELECT: tuple[float, float] = (0.915, 0.906)
"""确认选择。旧代码: timer.relative_click(0.915, 0.906)"""

_CLICK_REMOVE_EQUIP: tuple[float, float] = (0.837, 0.646)
"""卸下装备复选框。旧代码: timer.relative_click(0.837, 0.646)"""

_CLICK_DESTROY: tuple[float, float] = (0.9, 0.9)
"""解装确认按钮。旧代码: timer.relative_click(0.9, 0.9)"""

_CLICK_FOUR_STAR_CONFIRM: tuple[float, float] = (0.38, 0.567)
"""四星确认。旧代码: timer.relative_click(0.38, 0.567)"""

# ── 步骤间延迟 ──
_STEP_DELAY: float = 1.5
"""操作步骤间延迟 (秒), 与旧代码一致。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 公开函数
# ═══════════════════════════════════════════════════════════════════════════════


def destroy_ships(
    ctrl: AndroidController,
    *,
    remove_equipment: bool = True,
) -> None:
    """解装舰船 (全部解装 + 可选保留装备)。

    流程 (参照旧代码 ``destroy_ship``):

    1. 导航到建造页面、切换到解体标签
    2. 点击添加
    3. 快速选择
    4. 确认选择
    5. 若 ``remove_equipment=True``, 点击卸下装备
    6. 点击解装
    7. 四星确认
    8. 返回主页面

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    remove_equipment:
        是否卸下装备 (默认 True)。

    .. note::
        舰船类型过滤功能可在后续迭代中增加。
        当前实现为全类型解装 (与旧代码默认行为一致)。
    """
    goto_page(ctrl, "建造页面")

    page = BuildPage(ctrl)
    page.switch_tab(BuildTab.DESTROY)
    time.sleep(0.5)

    # 点击添加
    ctrl.click(*_CLICK_ADD)
    time.sleep(_STEP_DELAY)

    # 快速选择
    ctrl.click(*_CLICK_QUICK_SELECT)
    time.sleep(_STEP_DELAY)

    # 确认选择
    ctrl.click(*_CLICK_CONFIRM_SELECT)
    time.sleep(_STEP_DELAY)

    # 卸下装备
    if remove_equipment:
        ctrl.click(*_CLICK_REMOVE_EQUIP)
        time.sleep(_STEP_DELAY)

    # 解装
    ctrl.click(*_CLICK_DESTROY)
    time.sleep(_STEP_DELAY)

    # 四星确认
    ctrl.click(*_CLICK_FOUR_STAR_CONFIRM)
    time.sleep(_STEP_DELAY)

    logger.info("[OPS] 解装操作完成 (卸下装备={})", remove_equipment)

    goto_page(ctrl, "主页面")
