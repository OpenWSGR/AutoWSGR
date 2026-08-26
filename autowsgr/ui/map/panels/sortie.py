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
    CHAPTER_NAV_DELAY,
    CHAPTER_NAV_MAX_ATTEMPTS,
    CHAPTER_SPACING,
    CLICK_ENTER_SORTIE,
    CLICK_MAP_NEXT,
    CLICK_MAP_PREV,
    SIDEBAR_CLICK_X,
    SIDEBAR_SCAN_Y_RANGE,
    TOTAL_CHAPTERS,
    MapPanel,
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

    # click_chapter 内部「方向 fallback 探针」轮换使用的候选 y, 保证每次点不同位置避免死点同坐标
    #  +1 (下一条): 中下半区;  -1 (上一条): 中上半区 (都在安全区 [0.16, 0.84] 内)
    _PROBE_Y = {
        1:  (0.700, 0.645, 0.755, 0.590),
        -1: (0.300, 0.355, 0.245, 0.410),
    }

    def click_chapter(self, num: int, *, probe_cycle: int = 0) -> bool:
        """点击侧边栏章节（单步跳转 ±1 最稳，num∈[-3,3]仅相邻可靠）。

        优先使用高亮条 sel_y + CHAPTER_SPACING 并加微小抖动防死点；
        若 sel_y 连续两次找不到 → 按方向用预定义的 4 个 fallback 探针
        坐标轮换点击 (probe_cycle 传入 navigate 的点击次数累加即可)。

        Parameters
        ----------
        num:
            跳转数量, 正数向下跳转, 负数向上跳转。单步 ±1 最可靠。
        probe_cycle:
            同一方向连续失败时用于轮换 fallback 探针位置, 0~3 自动取模。

        Returns
        -------
        bool
            True = 实际发生了点击; False = 未点击 (两步都没有 sel_y)。
        """
        if not -3 <= num <= 3:
            raise ValueError(f'跳转数量必须为 -3 到 3, 收到: {num}')
        if num == 0:
            return False

        y_min, y_max = SIDEBAR_SCAN_Y_RANGE
        safe_min = y_min + 0.04
        safe_max = y_max - 0.04
        direction = 1 if num > 0 else -1

        def _jitter(base: float, amp: float = 0.006) -> float:
            """给 base y 加微小均匀抖动 ±amp, 避免每次点同一像素无效。"""
            offset = ((id(self) + probe_cycle * 37) % 100) / 100.0 * 2 - 1  # [-1, 1)
            return max(safe_min, min(safe_max, base + offset * amp))

        # ── 第 1 轮: 截图定位当前选中章 ──
        screen = self._ctrl.screenshot()
        sel_y = self.find_selected_chapter_y(screen)
        if sel_y is None:
            _log.debug('[UI] click_chapter 第1轮未找到高亮, 尝试复位侧边栏')
            if num > 0:
                self._ctrl.swipe(SIDEBAR_CLICK_X, 0.80, SIDEBAR_CLICK_X, 0.20, duration=0.35)
            else:
                self._ctrl.swipe(SIDEBAR_CLICK_X, 0.20, SIDEBAR_CLICK_X, 0.80, duration=0.35)
            time.sleep(0.30)
            screen = self._ctrl.screenshot()
            sel_y = self.find_selected_chapter_y(screen)
            if sel_y is None:
                _log.warning(
                    '[UI] click_chapter 复位后仍无高亮条, 启用方向探针 fallback (cycle=%d)',
                    probe_cycle,
                )
                probes = self._PROBE_Y[direction]
                probe_y = probes[probe_cycle % len(probes)]
                target_y = _jitter(probe_y, amp=0.008)
                self._ctrl.click(SIDEBAR_CLICK_X, target_y)
                # fallback 探针一定是点击了, 不做点击成功与否判定 (由上层 OCR 回检兜底)
                return True

        target_y = sel_y + num * CHAPTER_SPACING
        _log.info(
            '[UI] 地图页面→跳转章节 {}  sel_y={:.3f}→target_y={:.3f}',
            num, sel_y, target_y,
        )

        # ── 第 2 轮: 目标超出安全范围 → 先 swipe 滚动侧边栏 ──
        if not (safe_min <= target_y <= safe_max):
            _log.debug(
                '[UI] 目标 y={:.3f} 超出安全区 [{:.2f},{:.2f}], 先 swipe 滚动列表',
                target_y, safe_min, safe_max,
            )
            delta_y = abs(num) * CHAPTER_SPACING + 0.06
            if direction == 1:
                from_y = min(safe_max, sel_y + 0.10)
                to_y = max(safe_min, from_y - delta_y - 0.04)
            else:
                from_y = max(safe_min, sel_y - 0.10)
                to_y = min(safe_max, from_y + delta_y + 0.04)
            self._ctrl.swipe(
                SIDEBAR_CLICK_X, from_y,
                SIDEBAR_CLICK_X, to_y,
                duration=0.45,
            )
            time.sleep(CHAPTER_NAV_DELAY + 0.10)

            screen = self._ctrl.screenshot()
            sel_y2 = self.find_selected_chapter_y(screen)
            if sel_y2 is None:
                # swipe 后高亮还是看不清 → 改用 fallback 探针
                probes = self._PROBE_Y[direction]
                probe_y = probes[probe_cycle % len(probes)]
                target_y = _jitter(probe_y, amp=0.010)
                _log.warning('[UI] swipe 后无高亮条, 启用方向探针 y=%.3f', target_y)
                self._ctrl.click(SIDEBAR_CLICK_X, target_y)
                return True
            target_y = sel_y2 + num * CHAPTER_SPACING
            target_y = max(safe_min, min(safe_max, target_y))

        # 加 ±0.006 抖动, 避免连续 9 次点到完全相同的像素
        click_y = _jitter(target_y, amp=0.006)
        self._ctrl.click(SIDEBAR_CLICK_X, click_y)
        return True

    def navigate_to_chapter(self, target: int) -> int | None:
        """导航到指定章节 (通过 OCR 识别当前位置并批量点击)。

        远距离章节切换时采用批量点击 + 充分等待的策略，
        避免单步验证导致动画过渡期的 OCR 抖动浪费尝试次数。

        Parameters
        ----------
        target:
            目标章节编号 (1-9)。
        """
        if not 1 <= target <= TOTAL_CHAPTERS:
            raise ValueError(f'章节编号必须为 1-{TOTAL_CHAPTERS}，收到: {target}')
        if self._ocr is None:
            raise RuntimeError('需要 OCR 引擎才能导航到指定章节')

        def _read_chapter(
            samples: int = 3, delay: float = 0.15
        ) -> tuple[int | None, np.ndarray | None, bool]:
            chapters: list[int] = []
            last_screen: np.ndarray | None = None

            for i in range(samples):
                screen = self._ctrl.screenshot()
                last_screen = screen
                info = self.recognize_map(screen, self._ocr)
                if info is not None:
                    chapters.append(info.chapter)
                if i < samples - 1:
                    time.sleep(delay)

            if not chapters:
                return None, last_screen, False

            # 稳定策略：优先以"最后连续两次一致"为准，防止过渡态旧值占多数
            if len(chapters) >= 2 and chapters[-1] == chapters[-2]:
                candidate = chapters[-1]
                stable = True
            elif len(chapters) == samples and len(set(chapters)) == 1:
                candidate = chapters[0]
                stable = True
            else:
                candidate = max(set(chapters), key=chapters.count) if chapters else None
                stable = False
                _log.warning('[UI] 章节导航: OCR 抖动 {}，本轮不点击', chapters)
            return candidate, last_screen, stable

        def _quick_chapter() -> int | None:
            """单次 OCR 快速回检 (用于点击后立即确认有没有真的切换章)。"""
            screen = self._ctrl.screenshot()
            info = self.recognize_map(screen, self._ocr)
            return info.chapter if info is not None else None

        confirm_hits = 0
        strategy_switches = 0  # 每 miss 一次就给 probe_cycle +1 (换探针位置)

        for attempt in range(CHAPTER_NAV_MAX_ATTEMPTS):
            current, screen, stable = _read_chapter()
            if current is None:
                _log.warning('[UI] 章节导航: OCR 识别失败 (第 {} 次尝试)', attempt + 1)
                return None

            if current == target:
                confirm_hits += 1
                _log.info(
                    '[UI] 章节导航: 命中目标第 {} 章，二次确认 {}/2',
                    target,
                    confirm_hits,
                )
                if confirm_hits >= 2:
                    _log.info('[UI] 章节导航: 已到达第 {} 章', target)
                    return current
                time.sleep(CHAPTER_NAV_DELAY)
                continue

            confirm_hits = 0
            _log.info(
                '[UI] 章节导航: 当前第 {} 章 -> 目标第 {} 章',
                current,
                target,
            )

            if not stable or screen is None:
                time.sleep(CHAPTER_NAV_DELAY)
                continue

            delta = target - current
            direction = 1 if delta > 0 else -1
            remaining = abs(delta)
            consec_misses = 0      # click_chapter 没点的次数
            consec_stuck = 0       # 点击后章没变的次数
            MAX_MISSES = 6
            MAX_STUCK = 3
            steps_done = 0

            while remaining > 0 and consec_misses < MAX_MISSES and consec_stuck < MAX_STUCK:
                clicked = self.click_chapter(direction, probe_cycle=strategy_switches + steps_done)
                if not clicked:
                    consec_misses += 1
                    _log.warning('[UI] 章节导航: click 无动作 %d/%d', consec_misses, MAX_MISSES)
                    time.sleep(CHAPTER_NAV_DELAY)
                    continue
                steps_done += 1
                consec_misses = 0
                remaining -= 1
                _log.info('[UI] 章节导航: 跳转{:+d}章, 剩余{}章 (已走{}步)'.format(direction, remaining, steps_done))
                time.sleep(CHAPTER_NAV_DELAY)

                # ── 每步回检 (单次OCR ~0.18s): 立即确认章号是否真的前进了 ──
                qc = _quick_chapter()
                if qc is None:
                    continue  # OCR 偶发失败跳过 (下一轮 _read_chapter 会兜底)
                if direction == 1 and qc <= current:
                    # 本该往下跳 (+1) 但章号没涨 → 卡住 (允许 current 不变一次)
                    if qc == current and consec_stuck == 0:
                        consec_stuck = 1  # 第1次相等温和记录
                    else:
                        consec_stuck += 1
                    _log.warning(
                        '[UI] 章节导航: 跳+1后第{}章, 未前进 (cur={} stuck={}/{})',
                        qc, current, consec_stuck, MAX_STUCK,
                    )
                elif direction == -1 and qc >= current:
                    if qc == current and consec_stuck == 0:
                        consec_stuck = 1
                    else:
                        consec_stuck += 1
                    _log.warning(
                        '[UI] 章节导航: 跳-1后第{}章, 未前进 (cur={} stuck={}/{})',
                        qc, current, consec_stuck, MAX_STUCK,
                    )
                else:
                    consec_stuck = 0
                    current = qc  # 同步 OCR 锚点, 后续回检以此为基准
                    remaining = abs(target - current)

                # 卡住 ≥2 次 → 紧急策略调整: 强制 swipe 侧边栏 + 换探针
                if consec_stuck >= 2:
                    strategy_switches += 1
                    _log.warning(
                        '[UI] 章节导航: 连续 %d 次卡住 → 执行侧边栏重置 swipe',
                        consec_stuck,
                    )
                    if direction == 1:
                        # +1 卡住: 先从上往下扫一下 (把列表再拉到底一点)
                        self._ctrl.swipe(SIDEBAR_CLICK_X, 0.25, SIDEBAR_CLICK_X, 0.80, duration=0.45)
                    else:
                        # -1 卡住: 从下往上扫 (把列表拉到顶一点)
                        self._ctrl.swipe(SIDEBAR_CLICK_X, 0.80, SIDEBAR_CLICK_X, 0.25, duration=0.45)
                    time.sleep(0.5)
            if consec_misses >= MAX_MISSES:
                _log.warning('[UI] 章节导航: 连续 %d 次无点击, 重启本层 attempt', consec_misses)
                continue
            if consec_stuck >= MAX_STUCK:
                _log.warning('[UI] 章节导航: 连续 %d 次没前进, 重启本层 attempt (strategy_switches=%d)', consec_stuck, strategy_switches)
                continue

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
        MAP_NAV_DELAY = CHAPTER_NAV_DELAY

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
            direction = 1 if delta > 0 else -1
            remaining = abs(delta)
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
