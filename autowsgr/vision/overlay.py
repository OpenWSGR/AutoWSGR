"""均匀蒙版浮层检测 (双帧, 操作驱动)。

检测一次操作 (如点击地图节点) 是否触发了**均匀半透明黑罩浮层**——游戏常见的
modal: 中央弹出面板, 整页被半透明黑罩按某系数 ``t`` 压暗。

算法 (ratio clustering + 拓扑, 已用实机数据验证, 一组参数适用所有均匀蒙版浮层)
---------------------------------------------------------------------------
均匀半透明黑罩 = 乘性压暗 ``after ≈ before x t`` (t<1)。浮层几何 = 外围 (底层页)
被压暗 + 中心 (面板) 不压暗。据此:

1. **ratio clustering**: 全页 ``after/before`` 灰度比值找众数 ``t`` (压暗系数,
   自适应不同浮层不透明度: 浴室 ~0.3, 确认弹窗 ~0.45)。
2. 用 ``t`` 反蒙版 (unmask) 整页, 标记"匹配像素"(``diff<3``, 即被精确还原者)。
3. **拓扑判定** (不要求浮窗形状规则, 只要求拓扑):
   - 最外 1 像素匹配率高 (``outer``): 任何浮窗都有边距, 最外圈必然是未被覆盖的
     底层页 → 被均匀压暗则 unmask 后精确还原。真浮层 ≥28%, 非浮层 ≤4%。
   - 外圈匹配 > 中心 (``edge > center``): 环形包围 (外围底层页匹配, 中心面板不匹配)。

判定: ``raw_diff≥5`` 且 ``0<t<0.55`` 且 ``outer>10%`` 且 ``edge>center`` → 均匀蒙版。

双帧语义
--------
``detect(before, after)`` 中 *before* 是**无浮层参照帧**, *after* 是待测帧。
*before* 来源灵活: 可以是实时操作前截图 (典型: 点击前截一张干净页), 也可以是
导航栈留存的历史帧 (用于无实时干净 before 的静态/反向场景, 如战斗回港后的返回)。
这是"操作驱动"检测——对比操作前后两帧判定浮层是否出现, **不依赖浮层的固定外观**,
因此新活动无需为每个浮层截图专属模板。

与单帧像素签名浮层识别的区别
----------------------------
``decisive``/``main_page`` 等用单帧像素签名识别"当前帧是否叠加某固定浮层" (供
页面识别候选集 ``ui.stack.OVERLAY_CANDIDATES``); 本 API 是双帧对比, 判定"这次操作是否触发
浮层"。二者互补, 不等价 (双帧可借留存帧降级覆盖部分单帧场景)。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from autowsgr.vision.image_matcher import ImageChecker


# ═══════════════════════════════════════════════════════════════════════════════
# 常量 (一组参数适用所有均匀蒙版浮层, 非逐浮层调参)
# ═══════════════════════════════════════════════════════════════════════════════

DARKEN_TOL: float = 0.04
"""``after/before`` 比值落在 ``t±tol`` 内即视为该系数压暗。"""

DARKEN_SCAN: list[float] = [round(0.20 + 0.025 * i, 3) for i in range(21)]
"""压暗系数扫描范围 0.200..0.700 (步长 0.025)。"""

DARKEN_T_MAX: float = 0.55
"""压暗系数上限 (>此非明显压暗, 多为页跳转亮度噪声)。"""

NOCHANGE_GLOBAL: float = 5.0
"""全页平均 diff 低于此 = 前后几乎未变 (判定为无变化, 非浮层)。"""

BG_THRESH: int = 10
"""*before* 灰度低于此 (近黑) 跳过, 避免除零噪声。"""

PERFECT_DIFF: float = 3.0
"""unmask 后 diff 低于此 = 完美还原 (uint8 量化级)。"""

EDGE_BAND: int = 20
"""外圈带宽度 (像素), 用于外围 vs 中心拓扑对比。"""

TOPO_OUTER_MIN: float = 0.10
"""最外 1 像素匹配率下限 (浮窗必有边距, 最外圈=被压暗底层页; 真浮层≥0.28, 非浮层≤0.04)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 结果
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class OverlayDetectResult:
    """浮层检测结果。

    Attributes
    ----------
    matched:
        是否检测到均匀蒙版浮层。
    darken_factor:
        压暗系数 ``t`` (0=未检测到明显压暗)。
    outer_frac:
        最外 1 像素匹配率 (外围底层页还原比例)。
    edge_frac:
        外圈 ``EDGE_BAND`` 像素带匹配率。
    center_frac:
        中心区匹配率。
    raw_diff:
        全页平均 diff (前后 MAE), 供调试; :meth:`OverlayChecker.page_changed` 复用同值。
    """

    matched: bool
    darken_factor: float
    outer_frac: float
    edge_frac: float
    center_frac: float
    raw_diff: float


# ═══════════════════════════════════════════════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════════════════════════════════════════════


def _per_pixel_mae(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """逐像素 MAE (channel 维取均), 返回 HxW float32。"""
    return np.abs(a.astype(np.float32) - b.astype(np.float32)).mean(axis=2)


def _ratio_cluster(before: np.ndarray, after: np.ndarray, tol: float = DARKEN_TOL) -> float:
    """找乘性压暗系数 ``t`` (使 ``after/before≈t`` 的像素最多的 t)。

    直接捕获"被均匀半透明黑罩压暗"的物理特征, 不依赖浮窗边界。
    无明显压暗时返回 ``0.0``。
    """
    bg = before.mean(axis=2)
    ag = after.mean(axis=2)
    valid = bg > BG_THRESH
    if not valid.any():
        return 0.0
    ratio = (ag[valid] / bg[valid]).astype(np.float32)
    counts = [int((np.abs(ratio - t) <= tol).sum()) for t in DARKEN_SCAN]
    best_count = max(counts) if counts else 0
    if best_count == 0:
        return 0.0
    # 多个 scan 点因 tol 重叠而 count 相同时 (ratio 高度集中, 如理想浮层),
    # 选最接近 ratio 中位数者, 避免 scan 顺序偏向最小 t 导致 unmask 失准。
    med = float(np.median(ratio))
    candidates = [DARKEN_SCAN[i] for i, c in enumerate(counts) if c == best_count]
    return float(min(candidates, key=lambda t: abs(t - med)))


# ═══════════════════════════════════════════════════════════════════════════════
# 检测器
# ═══════════════════════════════════════════════════════════════════════════════


class OverlayChecker:
    """均匀蒙版浮层检测器 (双帧, 操作驱动)。

    全部方法为静态, 无状态——调用方负责提供 *before* 参照帧 (实时截图或栈留存帧)。
    """

    @staticmethod
    def detect_uniform_mask(
        before: np.ndarray, after: np.ndarray, *, tol: float = DARKEN_TOL
    ) -> OverlayDetectResult:
        """检测 *after* 相对 *before* 是否出现了均匀半透明黑罩浮层。

        Parameters
        ----------
        before:
            无浮层参照帧 (HxWx3, RGB, uint8)。来源灵活: 实时操作前截图或导航栈留存历史帧。
        after:
            待测帧 (与 *before* 同尺寸)。
        tol:
            ``after/before`` 比值落 ``t±tol`` 内即视为该系数压暗; 默认 :data:`DARKEN_TOL`。
            供分析工具做容差敏感性测试, 业务调用用默认即可。

        Returns
        -------
        OverlayDetectResult
            ``matched=True`` 即判定 *after* 上叠了均匀蒙版浮层。
        """
        raw_diff = float(_per_pixel_mae(before, after).mean())
        darken_t = _ratio_cluster(before, after, tol=tol)

        outer_frac = edge_frac = center_frac = 0.0
        if darken_t > 0:
            bg = before.mean(axis=2)
            umg = ImageChecker._unmask(after, darken_t).mean(axis=2)
            match = np.abs(bg - umg) < PERFECT_DIFF
            # 最外 1 像素: 浮窗必有边距, 最外圈=未被覆盖的底层页 → 被压暗则 unmask 后精确还原
            outer = np.zeros_like(match)
            outer[0, :] = outer[-1, :] = outer[:, 0] = outer[:, -1] = True
            outer_frac = float(match[outer].mean())
            # 外圈带 vs 中心: 环形包围拓扑 (外围匹配 > 中心, 因面板在中心)
            band = np.zeros_like(match)
            k = EDGE_BAND
            band[:k, :] = band[-k:, :] = band[:, :k] = band[:, -k:] = True
            edge_frac = float(match[band].mean())
            center_frac = float(match[~band].mean()) if (~band).any() else 0.0

        matched = (
            raw_diff >= NOCHANGE_GLOBAL
            and 0 < darken_t < DARKEN_T_MAX
            and outer_frac > TOPO_OUTER_MIN
            and edge_frac > center_frac
        )
        return OverlayDetectResult(
            matched=matched,
            darken_factor=darken_t,
            outer_frac=outer_frac,
            edge_frac=edge_frac,
            center_frac=center_frac,
            raw_diff=raw_diff,
        )

    @staticmethod
    def page_changed(
        before: np.ndarray, after: np.ndarray, *, threshold: float = NOCHANGE_GLOBAL
    ) -> bool:
        """两帧是否有实质变化 (全页平均 MAE ≥ *threshold*)。

        用于无干净 *before* 参照的静态场景 (如战斗回港后的 :meth:`go_back`):
        点击返回若前后几乎无变化 → 点击被模态浮层吸收 → 浮层挡道, 需先关浮层。
        """
        return float(_per_pixel_mae(before, after).mean()) >= threshold
