"""出征面板 Mixin — 章节选择、地图节点导航与进入出征准备。"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.types import PageName
from autowsgr.ui.map.base import BaseMapPage
from autowsgr.ui.map.data import (
    CHAPTER_MAP_COUNTS,
    CHAPTER_NAV_DELAY,
    CHAPTER_NAV_MAX_ATTEMPTS,
    CHAPTER_SPACING,
    CLICK_ENTER_SORTIE,
    CLICK_MAP_NEXT,
    CLICK_MAP_PREV,
    LOOT_COUNT_CROP,
    SHIP_COUNT_CROP,
    SIDEBAR_CLICK_X,
    SIDEBAR_SCAN_Y_RANGE,
    TOTAL_CHAPTERS,
    MapPanel,
)
from autowsgr.ui.utils import click_and_wait_for_page
from autowsgr.vision import PixelChecker


if TYPE_CHECKING:
    import numpy as np


_log = get_logger('ui')


# ── 数据类 ──


@dataclass(frozen=True, slots=True)
class LootShipCount:
    """出征面板右上角的掉落计数。

    Attributes
    ----------
    loot:
        战利品 (胖次) 已获取数量，识别失败时为 ``None``。
    loot_max:
        战利品上限 (通常 50)，识别失败时为 ``None``。
    ship:
        舰船已获取数量，识别失败时为 ``None``。
    ship_max:
        舰船上限 (通常 500)，识别失败时为 ``None``。
    """

    loot: int | None = None
    loot_max: int | None = None
    ship: int | None = None
    ship_max: int | None = None


# ── 内部工具 ──

_FRACTION_RE = re.compile(r'(\d+)\s*[/|]\s*(\d+)')
"""匹配 "X/Y" 格式的正则 (兼容 OCR 把 / 识别为 | 的情况)。"""

_KNOWN_DENOMS = (500, 50)
"""已知分母值, 用于 OCR 将 ``/`` 误识为 ``1`` 时的回退解析 (长的优先匹配)。"""


def _parse_fraction(text: str) -> tuple[int, int] | None:
    """解析 ``"123/500"`` 格式文本, 返回 ``(numerator, denominator)``。"""
    m = _FRACTION_RE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2))

    # 回退: OCR 有时将 '/' 误识为 '1', 导致纯数字串如 "17150" (实为 "17/50")。
    # 尝试去掉已知分母前的多余 '1' 来还原。
    digits = ''.join(c for c in text if c.isdigit())
    if digits:
        for denom in _KNOWN_DENOMS:
            suffix = '1' + str(denom)
            if digits.endswith(suffix) and len(digits) > len(suffix):
                numerator = int(digits[: -len(suffix)])
                if numerator >= 0 and numerator <= denom:
                    return numerator, denom
    return None


class SortiePanelMixin(BaseMapPage):
    """Mixin: 出征面板操作 — 选择章节 / 地图节点 / 进入出征准备。"""

    # ═══════════════════════════════════════════════════════════════════════
    # 章节 / 地图导航
    # ═══════════════════════════════════════════════════════════════════════

    def click_prev_chapter(self, screen: np.ndarray | None = None) -> bool:
        """点击侧边栏上方章节 (前一章)。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        sel_y = self.find_selected_chapter_y(screen)
        if sel_y is None:
            _log.warning('[UI] 侧边栏未找到选中章节，无法切换')
            return False
        target_y = sel_y - CHAPTER_SPACING
        if target_y < SIDEBAR_SCAN_Y_RANGE[0]:
            _log.warning('[UI] 已在最前章节，无法继续向前')
            return False
        _log.info('[UI] 地图页面 -> 上一章 (y={:.3f})', target_y)
        self._ctrl.click(SIDEBAR_CLICK_X, target_y)
        return True

    def click_next_chapter(self, screen: np.ndarray | None = None) -> bool:
        """点击侧边栏下方章节 (后一章)。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        sel_y = self.find_selected_chapter_y(screen)
        if sel_y is None:
            _log.warning('[UI] 侧边栏未找到选中章节，无法切换')
            return False
        target_y = sel_y + CHAPTER_SPACING
        if target_y > SIDEBAR_SCAN_Y_RANGE[1]:
            _log.warning('[UI] 已在最后章节，无法继续向后')
            return False
        _log.info('[UI] 地图页面 -> 下一章 (y={:.3f})', target_y)
        self._ctrl.click(SIDEBAR_CLICK_X, target_y)
        return True

    def navigate_to_chapter(self, target: int) -> int | None:
        """导航到指定章节 (通过 OCR 识别当前位置并逐步点击)。

        Parameters
        ----------
        target:
            目标章节编号 (1-9)。
        """
        if not 1 <= target <= TOTAL_CHAPTERS:
            raise ValueError(f'章节编号必须为 1-{TOTAL_CHAPTERS}，收到: {target}')
        if self._ocr is None:
            raise RuntimeError('需要 OCR 引擎才能导航到指定章节')

        for attempt in range(CHAPTER_NAV_MAX_ATTEMPTS):
            screen = self._ctrl.screenshot()
            info = self.recognize_map(screen, self._ocr)
            if info is None:
                _log.warning('[UI] 章节导航: OCR 识别失败 (第 {} 次尝试)', attempt + 1)
                return None

            current = info.chapter
            if current == target:
                _log.info('[UI] 章节导航: 已到达第 {} 章', target)
                return current

            _log.info(
                '[UI] 章节导航: 当前第 {} 章 -> 目标第 {} 章',
                current,
                target,
            )

            if current > target:
                ok = self.click_prev_chapter(screen)
            else:
                ok = self.click_next_chapter(screen)

            if not ok:
                _log.warning('[UI] 章节导航: 点击失败，终止')
                return None

            time.sleep(CHAPTER_NAV_DELAY)

        _log.warning(
            '[UI] 章节导航: 超过最大尝试次数 ({}), 目标第 {} 章',
            CHAPTER_NAV_MAX_ATTEMPTS,
            target,
        )
        return None

    def navigate_to_map(self, map_num: int | str) -> None:
        """通过 OCR 识别当前地图编号并左右翻页至目标。"""
        map_num = int(map_num)
        screen = self._ctrl.screenshot()
        info = self.recognize_map(screen, self._ocr)
        if info is not None:
            current_map = info.map_num
            if current_map != map_num:
                delta = map_num - current_map
                if delta > 0:
                    for _ in range(delta):
                        self._ctrl.click(*CLICK_MAP_NEXT)
                        time.sleep(0.3)
                else:
                    for _ in range(-delta):
                        self._ctrl.click(*CLICK_MAP_PREV)
                        time.sleep(0.3)
                time.sleep(0.5)

    # ═══════════════════════════════════════════════════════════════════════
    # 掉落数量读取
    # ═══════════════════════════════════════════════════════════════════════

    def get_loot_and_ship_count(
        self,
        screen: np.ndarray | None = None,
    ) -> LootShipCount:
        """读取出征面板右上角的已获取舰船/战利品数量。

        通过 OCR 识别 ``X/Y`` 格式的数字。需要先处于出征面板。

        Parameters
        ----------
        screen:
            截图，为 ``None`` 时自动截取。
        """
        if self._ocr is None:
            raise RuntimeError('需要 OCR 引擎才能读取掉落数量')
        if screen is None:
            screen = self._ctrl.screenshot()

        loot = loot_max = ship = ship_max = None

        # -- 战利品 (胖次) --
        loot_img = PixelChecker.crop(screen, *LOOT_COUNT_CROP)
        loot_text = self._ocr.recognize_single(loot_img, allowlist='0123456789/|').text.strip()
        if loot_text:
            parsed = _parse_fraction(loot_text)
            if parsed:
                loot, loot_max = parsed
                _log.info('[UI] 战利品数量: {}/{}', loot, loot_max)
            else:
                _log.warning("[UI] 战利品数量 OCR 解析失败: '{}'", loot_text)
        else:
            _log.warning('[UI] 战利品数量 OCR 无结果')

        # -- 舰船 --
        ship_img = PixelChecker.crop(screen, *SHIP_COUNT_CROP)
        ship_text = self._ocr.recognize_single(ship_img, allowlist='0123456789/|').text.strip()
        if ship_text:
            parsed = _parse_fraction(ship_text)
            if parsed:
                ship, ship_max = parsed
                _log.info('[UI] 舰船数量: {}/{}', ship, ship_max)
            else:
                _log.warning("[UI] 舰船数量 OCR 解析失败: '{}'", ship_text)
        else:
            _log.warning('[UI] 舰船数量 OCR 无结果')

        return LootShipCount(loot=loot, loot_max=loot_max, ship=ship, ship_max=ship_max)

    # ═══════════════════════════════════════════════════════════════════════
    # 进入出征
    # ═══════════════════════════════════════════════════════════════════════

    def enter_sortie(self, chapter: int | str, map_num: int | str) -> None:
        """进入出征: 选择指定章节和地图节点，直接到达出征准备页面。

        Parameters
        ----------
        chapter:
            目标章节编号 (1-9) 或事件地图标识字符串。
        map_num:
            目标地图节点编号 (1-6) 或事件地图标识字符串。

        Raises
        ------
        ValueError
            章节或地图编号无效 (仅数字模式)。
        NavigationError
            导航超时。
        """
        from autowsgr.ui.battle.preparation import BattlePreparationPage

        _log.info('[UI] 地图页面 → 进入出征 {}-{}', chapter, map_num)

        # 1. 确保在出征面板
        self.ensure_panel(MapPanel.SORTIE)
        time.sleep(0.5)

        # 2. 导航到指定章节
        if isinstance(chapter, int):
            max_maps = CHAPTER_MAP_COUNTS.get(chapter, 0)
            if max_maps == 0:
                raise ValueError(f'章节 {chapter} 不在已知地图数据中')
            if isinstance(map_num, int) and not 1 <= map_num <= max_maps:
                raise ValueError(f'章节 {chapter} 的地图编号必须为 1-{max_maps}，收到: {map_num}')
            result = self.navigate_to_chapter(chapter)
            if result is None:
                from autowsgr.ui.utils import NavigationError

                raise NavigationError(
                    f'无法导航到第 {chapter} 章',
                    screen=self._ctrl.screenshot(),
                )

        # 3. 切换到指定地图节点
        self.navigate_to_map(map_num)

        # 4. 点击进入出征准备
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_ENTER_SORTIE,
            checker=BattlePreparationPage.is_current_page,
            source=f'地图-出征 {chapter}-{map_num}',
            target=PageName.BATTLE_PREP,
        )
