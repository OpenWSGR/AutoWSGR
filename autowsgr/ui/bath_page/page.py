"""浴室页面 UI 控制器。

页面入口:
    - 主页面 -> 后院 -> 浴室
    - 出征准备 -> 右上角 -> 浴室 (跨级快捷通道)

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
    secs = page.repair_ship("胡德")  # 按名字修理指定舰船, 返回修理秒数或 -1(浴场满)
    page.go_back()  # overlay 打开时关闭 overlay, 否则返回上一页
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ui.bath_page.signatures import (
    BATH_FULL_TIMEOUT,
    CHOOSE_REPAIR_OVERLAY_SIGNATURE,
    CLICK_BACK,
    CLICK_CHOOSE_REPAIR,
    CLICK_CLOSE_OVERLAY,
    CLICK_FIRST_REPAIR_SHIP,
    CLICK_REPAIR_ALL,
    CLOSE_OVERLAY_BUTTON_COLOR,
    PAGE_SIGNATURE,
    REPAIR_ALL_BUTTON_COLOR,
    SWIPE_DELAY,
    SWIPE_DURATION,
    SWIPE_END,
    SWIPE_START,
)
from autowsgr.vision import Color, PixelChecker


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.context import GameContext


_log = get_logger('ui')


@dataclass(frozen=True, slots=True)
class RepairShipInfo:
    """选择修理 overlay 中识别到的舰船信息。

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
    repair_time: str = ''

    @property
    def repair_seconds(self) -> int:
        """将 repair_time (HH:MM:SS) 转换为秒数。解析失败返回 0。"""
        return _time_str_to_seconds(self.repair_time)


def _time_str_to_seconds(time_str: str) -> int:
    """将 HH:MM:SS 格式的时间字符串转换为秒数。

    Parameters
    ----------
    time_str:
        格式为 ``"HH:MM:SS"`` 的时间字符串。

    Returns
    -------
    int
        总秒数, 解析失败返回 0。
    """
    if not time_str:
        return 0
    parts = time_str.split(':')
    if len(parts) != 3:
        return 0
    try:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return 0


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

    def __init__(self, ctx: GameContext) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为浴室页面 (含 overlay 状态)。

        无论选择修理 overlay 是否打开，都识别为浴室页面。

        Parameters
        ----------
        screen:
            截图 (HxWx3, RGB)。
        """
        # 先检查基础浴室签名
        if PixelChecker.check_signature(screen, PAGE_SIGNATURE).matched:
            return True
        # overlay 打开时基础签名可能被遮挡，单独检查 overlay 签名
        return PixelChecker.check_signature(screen, CHOOSE_REPAIR_OVERLAY_SIGNATURE).matched

    @staticmethod
    def has_choose_repair_overlay(screen: np.ndarray) -> bool:
        """判断截图中选择修理 overlay 是否打开。

        Parameters
        ----------
        screen:
            截图 (HxWx3, RGB)。
        """
        return PixelChecker.check_signature(
            screen,
            CHOOSE_REPAIR_OVERLAY_SIGNATURE,
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
        from autowsgr.ui.utils import wait_for_page

        _log.info('[UI] 浴室 → 打开选择修理 overlay')
        if not self.has_choose_repair_overlay(self._ctrl.screenshot()):
            self._ctrl.click(*CLICK_CHOOSE_REPAIR)
        wait_for_page(
            self._ctrl,
            BathPage.has_choose_repair_overlay,
            source='浴室',
            target='选择修理 overlay',
        )

    def close_choose_repair_overlay(self) -> None:
        """关闭选择修理 overlay，回到浴室页面 (无 overlay)。

        Raises
        ------
        NavigationError
            超时 overlay 未关闭。
        """
        from autowsgr.ui.utils import wait_for_page

        _log.info('[UI] 关闭选择修理 overlay')
        self._ctrl.click(*CLICK_CLOSE_OVERLAY)
        # 等待 overlay 消失，基础浴室签名恢复（放宽条件，延长超时以兼容动画过渡）
        wait_for_page(
            self._ctrl,
            lambda s: (
                PixelChecker.check_signature(s, PAGE_SIGNATURE).matched
                and not BathPage.has_choose_repair_overlay(s)
            ),
            source='选择修理 overlay',
            target='浴室',
            timeout=10.0,
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
        from autowsgr.ui.utils import NavigationError

        _log.info('[UI] 选择修理 → 点击第一个舰船')

        # 确认 overlay 已打开
        screen = self._ctrl.screenshot()
        if not BathPage.has_choose_repair_overlay(screen):
            raise NavigationError('选择修理 overlay 未打开，无法点击舰船', screen=screen)

        self._ctrl.click(*CLICK_FIRST_REPAIR_SHIP)

        # 点击舰船后 overlay 自动关闭，等待回到浴室基础页面
        self._wait_overlay_auto_close()

    def click_repair_all(self) -> None:
        """在选择修理 overlay 中点击全部修理按钮。

        点击后若 overlay 未自动关闭，则手动点击关闭按钮。

        Raises
        ------
        NavigationError
            overlay 未打开，或点击后未能关闭。
        """
        from autowsgr.ui.utils import NavigationError

        screen = self._ctrl.screenshot()
        if not BathPage.has_choose_repair_overlay(screen):
            raise NavigationError('选择修理 overlay 未打开，无法点击全部修理', screen=screen)

        # 可选：校验全部修理按钮颜色
        btn_color, btn_tol = REPAIR_ALL_BUTTON_COLOR
        px = PixelChecker.get_pixel(screen, *CLICK_REPAIR_ALL)
        if not px.near(Color.from_rgb_tuple(btn_color), btn_tol):
            _log.warning('[UI] 未检测到全部修理按钮，回退到点击第一个舰船')
            self.click_first_repair_ship()
            return

        _log.info('[UI] 选择修理 → 点击全部修理')
        self._ctrl.click(*CLICK_REPAIR_ALL)
        time.sleep(1.0)

        # 等待 overlay 自动关闭或手动关闭，最多 10s
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            screen = self._ctrl.screenshot()
            if not BathPage.has_choose_repair_overlay(screen):
                _log.debug('[UI] 全部修理后 overlay 已自动关闭')
                return

            # 若检测到关闭按钮颜色，说明 overlay 仍在，主动关闭
            close_color, close_tol = CLOSE_OVERLAY_BUTTON_COLOR
            close_px = PixelChecker.get_pixel(screen, *CLICK_CLOSE_OVERLAY)
            if close_px.near(Color.from_rgb_tuple(close_color), close_tol):
                _log.debug('[UI] 全部修理后 overlay 仍在，手动关闭')
                self._ctrl.click(*CLICK_CLOSE_OVERLAY)
                # 手动关闭后再给 2s 让动画完成
                time.sleep(2.0)
                return

            time.sleep(0.5)

        raise NavigationError('全部修理后 overlay 未关闭', screen=self._ctrl.screenshot())

    def repair_ship(self, ship_name: str) -> int:
        """在选择修理 overlay 中修理指定名称的舰船。

        扫描 overlay 并逐页滑动查找指定舰船，找到后点击修理。

        Parameters
        ----------
        ship_name:
            要修理的舰船名称 (中文)。

        Returns
        -------
        int
            修理时间 (秒)。若浴场已满 (点击后 overlay 未关闭) 则返回 ``-1``。

        Raises
        ------
        NavigationError
            选择修理 overlay 未打开，或舰船未找到。
        """
        from autowsgr.ui.utils import NavigationError

        screen = self._ctrl.screenshot()
        if not BathPage.has_choose_repair_overlay(screen):
            raise NavigationError('选择修理 overlay 未打开，无法修理指定舰船', screen=screen)

        # 最多翻页 10 次查找
        for _attempt in range(10):
            ships = self.recognize_repair_ships()
            for ship in ships:
                if ship.name == ship_name:
                    _log.info('[UI] 选择修理: 找到 {} (耗时 {})，点击', ship_name, ship.repair_time)
                    repair_secs = ship.repair_seconds
                    self._ctrl.click(*ship.position)

                    # 检测浴场是否已满: overlay 未关闭说明浴场满
                    if self._try_wait_overlay_close():
                        _log.info('[UI] 修理成功: {} ({}s)', ship_name, repair_secs)
                        return repair_secs

                    _log.warning('[UI] 浴场已满, 无法修理 {}', ship_name)
                    return -1
            # 未找到，滑动翻页
            self._swipe_left()

        raise NavigationError(
            f'选择修理 overlay 中未找到舰船 "{ship_name}"',
            screen=self._ctrl.screenshot(),
        )

    def recognize_repair_ships(self) -> list[RepairShipInfo]:
        """识别选择修理 overlay 中当前可见的待修理舰船。

        Returns
        -------
        list[RepairShipInfo]
            当前可见待修理舰船列表。
        """
        from autowsgr.ui.bath_page.recognition import recognize_repair_cards
        from autowsgr.vision import OCREngine

        screen = self._ctrl.screenshot()
        ocr = OCREngine.create()
        return recognize_repair_cards(screen, ocr)

    def _swipe_left(self) -> None:
        """在选择修理 overlay 中向左滑动，查看更多待修理舰船。

        从右侧滑到左侧，使列表向左滚动以显示后续舰船。

        旧代码参考: ``timer.relative_swipe(0.33, 0.5, 0.66, 0.5)`` (反向)。
        """
        _log.debug('[UI] 选择修理 overlay: 向左滑动')
        self._ctrl.swipe(
            *SWIPE_START,
            *SWIPE_END,
            duration=SWIPE_DURATION,
        )
        time.sleep(SWIPE_DELAY)

    def _wait_overlay_auto_close(self) -> None:
        """等待选择修理 overlay 自动关闭 (点击舰船后)。

        点击一个舰船进行修理后，游戏会自动关闭 overlay 并返回浴室页面。
        """
        from autowsgr.ui.utils import wait_for_page

        wait_for_page(
            self._ctrl,
            lambda s: (
                PixelChecker.check_signature(s, PAGE_SIGNATURE).matched
                and not BathPage.has_choose_repair_overlay(s)
            ),
            source='选择修理 overlay (自动关闭)',
            target='浴室',
        )

    def _try_wait_overlay_close(self) -> bool:
        """尝试等待 overlay 关闭, 超时返回 False (浴场已满)。

        Returns
        -------
        bool
            ``True`` 表示 overlay 已关闭 (修理成功),
            ``False`` 表示超时 overlay 仍打开 (浴场已满)。
        """
        deadline = time.monotonic() + BATH_FULL_TIMEOUT
        while time.monotonic() < deadline:
            screen = self._ctrl.screenshot()
            if PixelChecker.check_signature(
                screen, PAGE_SIGNATURE
            ).matched and not BathPage.has_choose_repair_overlay(screen):
                return True
            time.sleep(0.5)
        return False

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
        from autowsgr.ui.utils import wait_leave_page

        screen = self._ctrl.screenshot()
        if BathPage.has_choose_repair_overlay(screen):
            # overlay 打开时，先关闭 overlay
            self.close_choose_repair_overlay()
            return

        _log.info('[UI] 浴室 → 返回')
        self._ctrl.click(*CLICK_BACK)
        wait_leave_page(
            self._ctrl,
            BathPage.is_current_page,
            source='浴室',
            target='后院/出征准备',
        )
