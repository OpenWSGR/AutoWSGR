"""地图页面子包。

re-export 公开 API，外部统一通过 ``autowsgr.ui.map`` 导入。
"""

from autowsgr.ui.map.data import (
    CAMPAIGN_NAMES,
    CAMPAIGN_POSITIONS,
    CHAPTER_MAP_COUNTS,
    CLICK_PANEL,
    MAP_DATABASE,
    MAP_NODE_POSITIONS,
    MapIdentity,
    MapPanel,
    PANEL_LIST,
    PANEL_TO_INDEX,
    TOTAL_CHAPTERS,
    parse_map_title,
)
from autowsgr.ui.map.page import MapPage

__all__ = [
    "CAMPAIGN_NAMES",
    "CAMPAIGN_POSITIONS",
    "CHAPTER_MAP_COUNTS",
    "CLICK_PANEL",
    "MAP_DATABASE",
    "MAP_NODE_POSITIONS",
    "MapIdentity",
    "MapPage",
    "MapPanel",
    "PANEL_LIST",
    "PANEL_TO_INDEX",
    "TOTAL_CHAPTERS",
    "parse_map_title",
]
