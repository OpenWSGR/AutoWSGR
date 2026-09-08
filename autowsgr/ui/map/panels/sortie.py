"""出征面板 Mixin — 章节选择、地图节点导航与进入出征准备。

与计数器相关的纯函数 (OCR 识别 LootShipCount) 已拆分至
``sortie_counters.py``, 本文件只保留 UI 导航 / 面板交互逻辑。
对外 API（campaign / panels ``__init__`` / e2e 等调用方）的导入
路径保持不变: ``from autowsgr.ui.map.panels.sortie import X``,
本文件通过 ``from .sortie_counters import ...`` 重导出实现透明迁移。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.types import PageName
from autowsgr.ui.map.base import BaseMapPage
from autowsgr.ui.map.data import (
    CHAPTER_MAP_COUNTS,
    CHAPTER_NAV_MAX_ATTEMPTS,
    CHAPTER_SLOT_CENTERS,
    CHAPTER_SLOT_CENTER_INDEX,
    CLICK_ENTER_SORTIE,
    CLICK_MAP_NEXT,
    CLICK_MAP_PREV,
    MAP_NAV_SETTLE_DELAY,
    SIDEBAR_CLICK_X,
    TOTAL_CHAPTERS,
    ChapterSlot,
    MapPanel,
    choose_chapter_slot,
)
# ── 计数器模块 (OCR 纯函数) 重导出 — 保持 sortie.py 对外符号不变 ──
from autowsgr.ui.map.panels.sortie_counters import (  # noqa: F401  重新导出
    LOOT_MAX,
    SHIP_MAX,
    LootShipCount,
    recognize_loot_count,
    recognize_ship_count,
)
from autowsgr.ui.utils import click_and_wait_for_page


if TYPE_CHECKING:
    import numpy as np


_log = get_logger('ui')


class SortiePanelMixin(BaseMapPage):
    """Mixin: 出征面板操作 — 选择章节 / 地图节点 / 进入出征准备。"""

    # ═══════════════════════════════════════════════════════════════════════
    # 章节 / 地图导航
    # ═══════════════════════════════════════════════════════════════════════

    def click_chapter_slot(self, index: int) -> None:
        """Click one of the five fixed chapter slots."""
        if not 0 <= index < len(CHAPTER_SLOT_CENTERS):
            raise ValueError(f'章节槽位索引必须为 0-{len(CHAPTER_SLOT_CENTERS) - 1}, 收到: {index}')
        self._ctrl.click(SIDEBAR_CLICK_X, CHAPTER_SLOT_CENTERS[index])
        _log.info('[UI] 地图页面→点击章节槽位 {} (y={:.3f})', index, CHAPTER_SLOT_CENTERS[index])

    def navigate_to_chapter(self, target: int) -> int | None:
        """Navigate to a chapter through fixed sidebar slots and OCR feedback.

        Parameters
        ----------
        target:
            目标章节编号 (1-9)。
        """
        if not 1 <= target <= TOTAL_CHAPTERS:
            raise ValueError(f'章节编号必须为 1-{TOTAL_CHAPTERS}，收到: {target}')
        if self._ocr is None:
            raise RuntimeError('需要 OCR 引擎才能导航到指定章节')

        def _read_slots() -> tuple[tuple[ChapterSlot, ...], int | None]:
            screen = self._ctrl.screenshot()
            slots = self.read_chapter_slots(screen)
            title = self.recognize_map(screen, self._ocr)
            current = slots[CHAPTER_SLOT_CENTER_INDEX].chapter
            if current is None and title is not None:
                current = title.chapter
            if current is not None and title is not None and title.chapter != current:
                _log.warning(
                    '[UI] 章节状态不一致: 侧边栏第{}章, 标题第{}章',
                    current,
                    title.chapter,
                )
            return slots, current

        confirm_hits = 0
        previous_current: int | None = None
        no_progress = 0

        for attempt in range(CHAPTER_NAV_MAX_ATTEMPTS):
            slots, current = _read_slots()
            slot_state = [slot.chapter if slot.chapter is not None else slot.text or '---' for slot in slots]
            if current is None:
                _log.warning('[UI] 章节导航: 中间章节槽位识别失败 (第 {} 次尝试)', attempt + 1)
                time.sleep(MAP_NAV_SETTLE_DELAY)
                continue

            if previous_current == current:
                no_progress += 1
            else:
                no_progress = 0
            previous_current = current
            if no_progress >= 3:
                _log.warning('[UI] 章节导航: 连续无进展, 槽位={}', slot_state)
                return None

            if current == target:
                confirm_hits += 1
                _log.info(
                    '[UI] 章节导航: 命中目标第 {} 章，确认 {}/2, 槽位={}',
                    target,
                    confirm_hits,
                    slot_state,
                )
                if confirm_hits >= 2:
                    _log.info('[UI] 章节导航: 已到达第 {} 章', target)
                    return current
                time.sleep(MAP_NAV_SETTLE_DELAY)
                continue

            confirm_hits = 0
            index = choose_chapter_slot(current, target, slots)
            if index is None:
                _log.warning(
                    '[UI] 章节导航: 目标第 {} 章没有可用槽位 (当前={}, 槽位={})',
                    target,
                    current,
                    slot_state,
                )
                time.sleep(MAP_NAV_SETTLE_DELAY)
                continue

            self.click_chapter_slot(index)
            time.sleep(MAP_NAV_SETTLE_DELAY)

        _log.warning(
            '[UI] 章节导航: 超过最大尝试次数 ({}), 目标第 {} 章',
            CHAPTER_NAV_MAX_ATTEMPTS,
            target,
        )
        return None

    def navigate_to_map(self, map_num: int | str) -> None:
        """在当前章节内, 翻页(←/→)至目标地图节点并 OCR 二次确认。

        与 :meth:`navigate_to_chapter` 采用同等强度的稳健策略:
        外层 ``CHAPTER_NAV_MAX_ATTEMPTS`` 次 attempt,
        每次 3-OCR 稳定读取当前 map_num, 每步单次 OCR 回检确认真的翻了,
        卡住 ≥2 次自动重启 attempt。
        """
        map_num = int(map_num)
        if self._ocr is None:
            raise RuntimeError('需要 OCR 引擎才能导航到指定地图节点')
        # 当前章最大地图数 (没有则退化为 99 让上层决定, 一般 enter_sortie 前置校验已挡住)
        cur_max = 99
        try:
            info_probe = self.recognize_map(self._ctrl.screenshot(), self._ocr)
            if info_probe is not None:
                cur_max = CHAPTER_MAP_COUNTS.get(int(info_probe.chapter), 99)
        except Exception:  # noqa: BLE001 - 探测失败不致命, 继续
            pass
        if not 1 <= map_num <= cur_max:
            raise ValueError(
                f'地图编号 map_num={map_num} 超出范围 [1, {cur_max}] '
                '(若当前章识别失败请先调用 navigate_to_chapter 正确选章)',
            )
        MAP_NAV_DELAY = MAP_NAV_SETTLE_DELAY

        def _read_map(
            samples: int = 3, delay: float = 0.15
        ) -> tuple[int | None, bool]:
            maps: list[int] = []
            for i in range(samples):
                screen = self._ctrl.screenshot()
                info = self.recognize_map(screen, self._ocr)
                if info is not None:
                    maps.append(info.map_num)
                if i < samples - 1:
                    time.sleep(delay)
            if not maps:
                return None, False
            if len(maps) >= 2 and maps[-1] == maps[-2]:
                return maps[-1], True
            if len(maps) == samples and len(set(maps)) == 1:
                return maps[0], True
            candidate = max(set(maps), key=maps.count)
            _log.warning('[UI] 地图节点导航: OCR 抖动 {}, 本轮不点击'.format(maps))
            return candidate, False

        def _quick_map() -> int | None:
            screen = self._ctrl.screenshot()
            info = self.recognize_map(screen, self._ocr)
            return info.map_num if info is not None else None

        confirm = 0
        for attempt in range(CHAPTER_NAV_MAX_ATTEMPTS):
            current, stable = _read_map()
            if current is None:
                _log.warning('[UI] 地图节点导航: OCR 识别失败 (attempt %d/%d)', attempt + 1, CHAPTER_NAV_MAX_ATTEMPTS)
                continue

            if current == map_num:
                confirm += 1
                _log.info('[UI] 地图节点导航: 命中目标 %d-%d 确认 %d/2', current, map_num, confirm)
                if confirm >= 2:
                    _log.info('[UI] 地图节点导航: 已到达当前章第 %d 节 (地图编号 %d)', map_num, map_num)
                    return
                time.sleep(MAP_NAV_DELAY)
                continue

            confirm = 0
            if not stable:
                time.sleep(MAP_NAV_DELAY)
                continue

            delta = map_num - current
            remaining = abs(map_num - current)
            stuck = 0
            misses = 0
            steps = 0
            MAX_STUCK = 3
            MAX_MISSES = 6

            _log.info(
                '[UI] 地图节点导航: 当前 %d -> 目标 %d (delta=%+d)',
                current, map_num, delta,
            )

            while remaining > 0 and stuck < MAX_STUCK and misses < MAX_MISSES:
                direction = 1 if map_num > current else -1
                if direction == 1:
                    self._ctrl.click(*CLICK_MAP_NEXT)
                    _log.info('[UI] 地图节点导航: → 下一节 (remaining %d, steps %d)', remaining, steps + 1)
                else:
                    self._ctrl.click(*CLICK_MAP_PREV)
                    _log.info('[UI] 地图节点导航: ← 上一节 (remaining %d, steps %d)', remaining, steps + 1)
                steps += 1
                remaining -= 1
                time.sleep(MAP_NAV_DELAY + 0.20)  # 翻页动画比章节切换长

                qc = _quick_map()
                if qc is None:
                    misses += 1
                    continue
                misses = 0
                if (direction == 1 and qc <= current) or (direction == -1 and qc >= current):
                    if qc == current and stuck == 0:
                        stuck = 1
                    else:
                        stuck += 1
                    _log.warning(
                        '[UI] 地图节点导航: 翻页后仍是第%d节 (cur=%d, stuck=%d/%d)',
                        qc, current, stuck, MAX_STUCK,
                    )
                else:
                    stuck = 0
                    current = qc
                    remaining = abs(map_num - current)
            if stuck >= MAX_STUCK or misses >= MAX_MISSES:
                _log.warning('[UI] 地图节点导航: 卡住/识别失败超限 (stuck=%d misses=%d), 重启 attempt', stuck, misses)
                continue

        raise RuntimeError(
            f'地图节点导航超过最大尝试次数 {CHAPTER_NAV_MAX_ATTEMPTS}, 目标节 {map_num} 未到达',
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 掉落数量读取
    # ═══════════════════════════════════════════════════════════════════════

    def get_loot_and_ship_count(
        self,
        screen: np.ndarray | None = None,
        *,
        read_loot: bool = True,
    ) -> LootShipCount:
        """读取出征面板右上角的已获取舰船/战利品数量。

        通过 OCR 识别数字。需要先处于出征面板。

        Parameters
        ----------
        screen:
            截图，为 ``None`` 时自动截取。
        read_loot:
            是否识别战利品 (胖次) 数量。仅在 YAML 开启 ``stop_max_loot``
            (战利品检查) 时为 True; 无战利品活动时置 False 跳过该区域 OCR,
            避免对不存在的计数器进行无效识别。
        """
        if self._ocr is None:
            raise RuntimeError('需要 OCR 引擎才能读取掉落数量')
        if screen is None:
            screen = self._ctrl.screenshot()

        loot = recognize_loot_count(screen, self._ocr) if read_loot else None
        ship = recognize_ship_count(screen, self._ocr)

        return LootShipCount(loot=loot, ship=ship)

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
        time.sleep(MAP_NAV_SETTLE_DELAY)

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
