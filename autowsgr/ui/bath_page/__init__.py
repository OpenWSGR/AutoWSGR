"""浴室页面 UI 模块。

将 bath_page 从单文件重构为 package，便于拆分页面控制与 OCR 识别逻辑。

公开 API::

    from autowsgr.ui.bath_page import BathPage, RepairShipInfo
"""

from .page import (
    BathPage,
    RepairShipInfo,
)
from .recognition import recognize_repair_cards


__all__ = [
    'BathPage',
    'RepairShipInfo',
    'recognize_repair_cards',
]
