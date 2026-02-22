"""浴室页面 UI 控制器。

已完成

页面入口:
    - 主页面 → 后院 → 浴室
    - 出征准备 → 右上角 🔧 → 浴室 (跨级快捷通道)

导航目标:

- **选择修理 (overlay)**: 右上角按钮，弹出选择修理浮层

跨级通道:

- 从出征准备页面可直接进入浴室 (旧代码的 cross-edge)
- 浴室可直接返回战斗准备页面 (旧代码的 cross-edge)

Overlay 机制:

    "选择修理" 是浴室页面上的一个 overlay (浮层)。
    打开后仍识别为浴室页面 (``is_current_page`` 返回 ``True``)。
    使用 ``has_choose_repair_overlay`` 判断 overlay 是否打开。
    ``go_back`` 在 overlay 打开时先关闭 overlay 而非返回上一页。

使用方式::

    from autowsgr.ui.bath_page import BathPage

    page = BathPage(ctrl)
    page.go_to_choose_repair()   # 打开 overlay
    page.click_first_repair_ship()  # 点击第一个需修理舰船 (自动关闭 overlay)
    # 或
    page.repair_ship("胡德")  # 按名字修理指定舰船 (TODO: 待实现 OCR)
    page.go_back()  # overlay 打开时关闭 overlay，否则返回上一页
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.vision import (
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_SIGNATURE = PixelSignature(
    name="浴场页",
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
    name="选择修理",
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
# 点击坐标 (相对坐标 0.0–1.0, 参考分辨率 960×540)
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)。"""

CLICK_CHOOSE_REPAIR: tuple[float, float] = (0.9375, 0.0556)
"""选择修理按钮 (右上角)。

坐标换算: 旧代码 (900, 30) ÷ (960, 540)。
"""

CLICK_CLOSE_OVERLAY: tuple[float, float] = (0.9563, 0.0903)
"""关闭选择修理 overlay 的按钮。

坐标换算: 旧代码 (916, 45 附近) ÷ (960, 540)。
"""

CLICK_FIRST_REPAIR_SHIP: tuple[float, float] = (0.1198, 0.4315)
"""选择修理 overlay 中第一个舰船的位置。

旧代码: timer.click(115, 233) → (115/960, 233/540)。
"""

# ── 滑动坐标 ──────────────────────────────────────────────────────────

_SWIPE_START: tuple[float, float] = (0.66, 0.5)
"""overlay 内向左滑动起始点 (右侧)。"""

_SWIPE_END: tuple[float, float] = (0.33, 0.5)
"""overlay 内向左滑动终点 (左侧)。

旧代码: relative_swipe(0.33, 0.5, 0.66, 0.5) 为向右滑，
此处反向 (0.66→0.33) 为向左滑，用于查看更多待修理舰船。
"""

_SWIPE_DURATION: float = 0.5
"""滑动持续时间 (秒)。"""

_SWIPE_DELAY: float = 1.0
"""滑动后等待内容刷新的延迟 (秒)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 舰船修理信息 (预留数据结构)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class RepairShipInfo:
    """选择修理 overlay 中识别到的舰船信息。

    .. note::
        目前为预留结构，待 OCR 识别接口实现后填充。

    Attributes
    ----------
    name:
        舰船名称 (中文)。
    position:
        舰船在 overlay 中的点击坐标 (相对坐标)。
    repair_time:
        预估修理时长描述 (如 ``"01:23:45"``)，尚未解析时为空字符串。
    """

    name: str
    position: tuple[float, float]
    repair_time: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class BathPage:
    """浴室页面控制器。

    支持 **选择修理 overlay** — 浴室页面上的一个浮层。
    overlay 打开时仍识别为浴室页面，通过 :meth:`has_choose_repair_overlay`
    判断浮层是否打开。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。
    """

    def __init__(self, ctrl: AndroidController) -> None:
        self._ctrl = ctrl

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为浴室页面 (含 overlay 状态)。

        无论选择修理 overlay 是否打开，都识别为浴室页面。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        # 先检查基础浴室签名
        if PixelChecker.check_signature(screen, PAGE_SIGNATURE).matched:
            return True
        # overlay 打开时基础签名可能被遮挡，单独检查 overlay 签名
        if PixelChecker.check_signature(screen, CHOOSE_REPAIR_OVERLAY_SIGNATURE).matched:
            return True
        return False

    @staticmethod
    def has_choose_repair_overlay(screen: np.ndarray) -> bool:
        """判断截图中选择修理 overlay 是否打开。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        return PixelChecker.check_signature(
            screen, CHOOSE_REPAIR_OVERLAY_SIGNATURE,
        ).matched

    # ── Overlay 操作 ──────────────────────────────────────────────────────

    def go_to_choose_repair(self) -> None:
        """点击右上角按钮，打开选择修理 overlay。

        点击后等待 overlay 出现。

        Raises
        ------
        NavigationError
            超时 overlay 未出现。
        """
        from autowsgr.ui.page import wait_for_page

        logger.info("[UI] 浴室 → 打开选择修理 overlay")
        self._ctrl.click(*CLICK_CHOOSE_REPAIR)
        wait_for_page(
            self._ctrl,
            BathPage.has_choose_repair_overlay,
            source="浴室",
            target="选择修理 overlay",
        )

    def close_choose_repair_overlay(self) -> None:
        """关闭选择修理 overlay，回到浴室页面 (无 overlay)。

        Raises
        ------
        NavigationError
            超时 overlay 未关闭。
        """
        from autowsgr.ui.page import wait_for_page

        logger.info("[UI] 关闭选择修理 overlay")
        self._ctrl.click(*CLICK_CLOSE_OVERLAY)
        # 等待 overlay 消失，基础浴室签名恢复
        wait_for_page(
            self._ctrl,
            lambda s: (
                PixelChecker.check_signature(s, PAGE_SIGNATURE).matched
                and not BathPage.has_choose_repair_overlay(s)
            ),
            source="选择修理 overlay",
            target="浴室",
        )

    def click_first_repair_ship(self) -> None:
        """在选择修理 overlay 中点击第一个需修理的舰船。

        点击后 overlay 自动关闭，返回浴室页面。

        旧代码参考: ``timer.click(115, 233)``

        Raises
        ------
        NavigationError
            超时 overlay 未关闭。
        """
        from autowsgr.ui.page import NavigationError

        logger.info("[UI] 选择修理 → 点击第一个舰船")

        # 确认 overlay 已打开
        screen = self._ctrl.screenshot()
        if not BathPage.has_choose_repair_overlay(screen):
            raise NavigationError("选择修理 overlay 未打开，无法点击舰船")

        self._ctrl.click(*CLICK_FIRST_REPAIR_SHIP)

        # 点击舰船后 overlay 自动关闭，等待回到浴室基础页面
        self._wait_overlay_auto_close()

    def repair_ship(self, ship_name: str) -> None:
        """在选择修理 overlay 中修理指定名称的舰船。

        .. note::
            当前实现为 **预留接口**，待 OCR 识别接口完成后实现。
            目前会扫描 overlay 并逐页滑动查找指定舰船。

        Parameters
        ----------
        ship_name:
            要修理的舰船名称 (中文)。

        Raises
        ------
        NavigationError
            选择修理 overlay 未打开。
        NotImplementedError
            OCR 识别功能尚未实现。
        """
        from autowsgr.ui.page import NavigationError

        screen = self._ctrl.screenshot()
        if not BathPage.has_choose_repair_overlay(screen):
            raise NavigationError("选择修理 overlay 未打开，无法修理指定舰船")

        # TODO: 实现 OCR 识别 + 滑动查找
        # 大致流程:
        # 1. recognize_repair_ships() 获取当前可见舰船
        # 2. 在列表中查找 ship_name
        # 3. 若未找到，_swipe_left() 翻页后重复
        # 4. 找到后点击对应位置
        # 5. _wait_overlay_auto_close()
        raise NotImplementedError(
            f"repair_ship('{ship_name}') 尚未实现: "
            "需要 OCR 识别接口完成后实现舰船名称匹配"
        )

    def recognize_repair_ships(self) -> list[RepairShipInfo]:
        """识别选择修理 overlay 中当前可见的待修理舰船。

        .. note::
            当前实现为 **预留接口**，待 OCR 识别接口完成后实现。
            将返回当前 overlay 中可见的所有舰船信息 (名称、位置、修理时间)。

        Returns
        -------
        list[RepairShipInfo]
            当前可见待修理舰船列表。

        Raises
        ------
        NotImplementedError
            OCR 识别功能尚未实现。
        """
        # TODO: 实现 OCR 识别
        # 大致流程:
        # 1. 截图
        # 2. 对 overlay 区域进行 OCR
        # 3. 解析舰船名称和修理时间
        # 4. 返回 RepairShipInfo 列表
        raise NotImplementedError(
            "recognize_repair_ships() 尚未实现: 需要 OCR 识别接口"
        )

    def _swipe_left(self) -> None:
        """在选择修理 overlay 中向左滑动，查看更多待修理舰船。

        从右侧滑到左侧，使列表向左滚动以显示后续舰船。

        旧代码参考: ``timer.relative_swipe(0.33, 0.5, 0.66, 0.5)`` (反向)。
        """
        logger.debug("[UI] 选择修理 overlay: 向左滑动")
        self._ctrl.swipe(
            *_SWIPE_START, *_SWIPE_END,
            duration=_SWIPE_DURATION,
        )
        time.sleep(_SWIPE_DELAY)

    def _wait_overlay_auto_close(self) -> None:
        """等待选择修理 overlay 自动关闭 (点击舰船后)。

        点击一个舰船进行修理后，游戏会自动关闭 overlay 并返回浴室页面。
        """
        from autowsgr.ui.page import wait_for_page

        wait_for_page(
            self._ctrl,
            lambda s: (
                PixelChecker.check_signature(s, PAGE_SIGNATURE).matched
                and not BathPage.has_choose_repair_overlay(s)
            ),
            source="选择修理 overlay (自动关闭)",
            target="浴室",
        )

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """智能回退。

        - 若选择修理 overlay 打开 → 关闭 overlay (回到浴室)
        - 若无 overlay → 点击回退按钮 (◁)，返回后院/出征准备

        Raises
        ------
        NavigationError
            超时未完成回退。
        """
        from autowsgr.ui.page import wait_leave_page

        screen = self._ctrl.screenshot()
        if BathPage.has_choose_repair_overlay(screen):
            # overlay 打开时，先关闭 overlay
            self.close_choose_repair_overlay()
            return

        logger.info("[UI] 浴室 → 返回")
        self._ctrl.click(*CLICK_BACK)
        wait_leave_page(
            self._ctrl,
            BathPage.is_current_page,
            source="浴室",
            target="后院/出征准备",
        )
