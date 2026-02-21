"""血量颜色检测。

提供统一的舰船血量状态检测函数，基于像素颜色的欧氏距离判断。
供出征准备页面和战斗结算页面共同使用。

五种血量颜色特征:

- **绿血** → :attr:`ShipDamageState.NORMAL`
- **黄血** → :attr:`ShipDamageState.MODERATE`
- **红血** → :attr:`ShipDamageState.SEVERE`
- **空血** → :attr:`ShipDamageState.SEVERE` （血条耗尽，同样判定为大破）
- **蓝色无** → :attr:`ShipDamageState.NO_SHIP`
"""

from __future__ import annotations

from autowsgr.types import ShipDamageState
from autowsgr.vision import Color


# ═══════════════════════════════════════════════════════════════════════════════
# 血量颜色特征 (RGB)
# ═══════════════════════════════════════════════════════════════════════════════

BLOOD_GREEN = Color.of(75, 168, 118)
"""绿血 — 正常。"""

BLOOD_YELLOW = Color.of(246, 184, 51)
"""黄血 — 中破。"""

BLOOD_RED = Color.of(171, 18, 17)
"""红血 — 大破。"""

BLOOD_EMPTY = Color.of(58, 60, 62)
"""空血 — 血条耗尽（判定为大破）。"""

BLOOD_NO_SHIP = Color.of(43, 87, 112)
"""蓝色 — 无舰船。"""

_BLOOD_COLORS: tuple[tuple[Color, ShipDamageState], ...] = (
    (BLOOD_GREEN, ShipDamageState.NORMAL),
    (BLOOD_YELLOW, ShipDamageState.MODERATE),
    (BLOOD_RED, ShipDamageState.SEVERE),
    (BLOOD_EMPTY, ShipDamageState.SEVERE),
    (BLOOD_NO_SHIP, ShipDamageState.NO_SHIP),
)
"""颜色 → 血量状态映射表。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 检测函数
# ═══════════════════════════════════════════════════════════════════════════════


def classify_blood(pixel: Color) -> ShipDamageState:
    """根据像素颜色判断血量状态。

    计算像素与五种参考颜色的欧氏距离，返回距离最近的对应状态。

    Parameters
    ----------
    pixel:
        从血条探测点采样的像素颜色。

    Returns
    -------
    ShipDamageState
    """
    best_state = ShipDamageState.NORMAL
    best_dist = float("inf")
    for ref_color, state in _BLOOD_COLORS:
        dist = pixel.distance(ref_color)
        if dist < best_dist:
            best_dist = dist
            best_state = state
    return best_state
