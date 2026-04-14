"""浴室页面像素签名与坐标常量。"""

from autowsgr.vision import MatchStrategy, PixelRule, PixelSignature


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_SIGNATURE = PixelSignature(
    name='浴场页',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8458, 0.1102, (74, 132, 178), tolerance=30.0),
        PixelRule.of(0.8604, 0.0889, (253, 254, 255), tolerance=30.0),
        PixelRule.of(0.8734, 0.0454, (52, 146, 198), tolerance=30.0),
        PixelRule.of(0.9875, 0.1019, (69, 133, 181), tolerance=30.0),
    ],
)
"""浴室页面像素签名 (无 overlay 时)。"""

CHOOSE_REPAIR_OVERLAY_SIGNATURE = PixelSignature(
    name='选择修理',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.6797, 0.1750, (27, 122, 212), tolerance=30.0),
        PixelRule.of(0.8383, 0.1750, (25, 123, 210), tolerance=30.0),
        PixelRule.of(0.3039, 0.1750, (93, 183, 122), tolerance=30.0),
        PixelRule.of(0.2852, 0.0944, (23, 90, 158), tolerance=30.0),
        PixelRule.of(0.9047, 0.0958, (3, 124, 207), tolerance=30.0),
    ],
)
"""选择修理 overlay 像素签名。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标 (相对坐标 0.0-1.0, 参考分辨率 960x540)
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_REPAIR_ALL: tuple[float, float] = (0.6802, 0.1704)
"""全部修理按钮 (选择修理 overlay 右上角)。"""

REPAIR_ALL_BUTTON_COLOR: tuple[tuple[int, int, int], float] = ((17, 119, 216), 30.0)
"""全部修理按钮颜色 (蓝) 及容差。"""

CLOSE_OVERLAY_BUTTON_COLOR: tuple[tuple[int, int, int], float] = ((197, 199, 194), 30.0)
"""关闭按钮颜色 (灰) 及容差。"""

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)。"""

CLICK_CHOOSE_REPAIR: tuple[float, float] = (0.9375, 0.0556)
"""选择修理按钮 (右上角)。

坐标换算: 旧代码 (900, 30) / (960, 540)。
"""

CLICK_CLOSE_OVERLAY: tuple[float, float] = (0.9563, 0.0903)
"""关闭选择修理 overlay 的按钮。

坐标换算: 旧代码 (916, 45 附近) / (960, 540)。
"""

CLICK_FIRST_REPAIR_SHIP: tuple[float, float] = (0.1198, 0.4315)
"""选择修理 overlay 中第一个舰船的位置。

旧代码: timer.click(115, 233) -> (115/960, 233/540)。
"""

# ── 滑动坐标 ──────────────────────────────────────────────────────────

SWIPE_START: tuple[float, float] = (0.66, 0.5)
"""overlay 内向左滑动起始点 (右侧)。"""

SWIPE_END: tuple[float, float] = (0.33, 0.5)
"""overlay 内向左滑动终点 (左侧)。

旧代码: relative_swipe(0.33, 0.5, 0.66, 0.5) 为向右滑,
此处反向 (0.66->0.33) 为向左滑, 用于查看更多待修理舰船。
"""

SWIPE_DURATION: float = 0.5
"""滑动持续时间 (秒)。"""

SWIPE_DELAY: float = 1.0
"""滑动后等待内容刷新的延迟 (秒)。"""

BATH_FULL_TIMEOUT: float = 3.0
"""点击舰船后等待 overlay 关闭的超时 (秒)。超时则判定浴场已满。"""
