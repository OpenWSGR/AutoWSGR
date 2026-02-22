"""决战 UI 子包。

包含决战相关的 UI 控制器:

- ``DecisiveBattlePage`` — 决战总览页 (章节导航/购买/进入地图)
- ``DecisiveMapController`` — 决战地图页 (overlay/出征/修理)
- ``DecisiveBattlePreparationPage`` — 决战出征准备页 (决战专用换船)

以及内部模块:

- ``overlay.py`` — 像素签名/坐标常量/overlay 检测函数
- ``battle_page.py`` — 总览页控制器
- ``map_controller.py`` — 地图页控制器
- ``fleet_ocr.py`` — 舰队 OCR 识别 (map_controller 内部委托)
- ``preparation.py`` — 决战专用出征准备页控制器

模块结构::

    decisive/
    ├── __init__.py           ← 本文件 (统一导出)
    ├── battle_page.py        ← DecisiveBattlePage (总览页)
    ├── overlay.py            ← 签名/坐标常量/检测函数/DecisiveOverlay
    ├── map_controller.py     ← DecisiveMapController (地图页 UI 操作)
    ├── fleet_ocr.py          ← 舰队 OCR 识别函数
    └── preparation.py        ← DecisiveBattlePreparationPage (决战换船)
"""

from autowsgr.ui.decisive.battle_page import DecisiveBattlePage
from autowsgr.ui.decisive.map_controller import DecisiveMapController
from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage

__all__ = [
    "DecisiveBattlePage",
    "DecisiveMapController",
    "DecisiveBattlePreparationPage",
]
