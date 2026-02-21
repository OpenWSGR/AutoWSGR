"""决战地图页 UI 子包。

包含决战地图页的 overlay 检测、坐标常量、像素签名，
以及 ``DecisiveMapController`` — 决战地图页所有 UI 操作的封装。

模块结构::

    decisive/
    ├── __init__.py           ← 本文件 (统一导出)
    ├── overlay.py            ← 签名/坐标常量/检测函数/DecisiveOverlay
    └── map_controller.py     ← DecisiveMapController (地图页 UI 操作)
"""

from autowsgr.ui.decisive.map_controller import DecisiveMapController
from autowsgr.ui.decisive.overlay import (
    ADVANCE_CARD_POSITIONS,
    CLICK_ADVANCE_CONFIRM,
    CLICK_BUY_EXP,
    CLICK_FLEET_CLOSE,
    CLICK_FLEET_EDIT,
    CLICK_FLEET_REFRESH,
    CLICK_LEAVE,
    CLICK_RETREAT_BUTTON,
    CLICK_RETREAT_CONFIRM,
    CLICK_SKILL,
    CLICK_SORTIE,
    COST_AREA,
    FLEET_CARD_CLICK_Y,
    FLEET_CARD_X_POSITIONS,
    RESOURCE_AREA,
    SHIP_NAME_X_RANGES,
    SHIP_NAME_Y_RANGE,
    DecisiveOverlay,
    detect_decisive_overlay,
    get_overlay_signature,
    is_advance_choice,
    is_confirm_exit,
    is_decisive_map_page,
    is_fleet_acquisition,
)

__all__ = [
    # Overlay
    "DecisiveOverlay",
    "detect_decisive_overlay",
    "get_overlay_signature",
    "is_decisive_map_page",
    "is_fleet_acquisition",
    "is_advance_choice",
    "is_confirm_exit",
    # 坐标常量
    "CLICK_RETREAT_BUTTON",
    "CLICK_SORTIE",
    "CLICK_FLEET_EDIT",
    "CLICK_BUY_EXP",
    "CLICK_SKILL",
    "CLICK_FLEET_REFRESH",
    "CLICK_FLEET_CLOSE",
    "FLEET_CARD_X_POSITIONS",
    "FLEET_CARD_CLICK_Y",
    "SHIP_NAME_X_RANGES",
    "SHIP_NAME_Y_RANGE",
    "COST_AREA",
    "RESOURCE_AREA",
    "CLICK_LEAVE",
    "CLICK_RETREAT_CONFIRM",
    "CLICK_ADVANCE_CONFIRM",
    "ADVANCE_CARD_POSITIONS",
    # 地图控制器
    "DecisiveMapController",
]
