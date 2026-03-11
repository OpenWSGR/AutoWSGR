"""浴室页面 UI 模块。

公开 API::

    from autowsgr.ui.bath_page import BathPage, RepairShipInfo
"""

from .page import (
    BathPage,
    RepairShipInfo,
)
from .recognition import recognize_repair_cards
from .signatures import (
    CHOOSE_REPAIR_OVERLAY_SIGNATURE,
    PAGE_SIGNATURE,
)


__all__ = [
    'CHOOSE_REPAIR_OVERLAY_SIGNATURE',
    'PAGE_SIGNATURE',
    'BathPage',
    'RepairShipInfo',
    'recognize_repair_cards',
]
