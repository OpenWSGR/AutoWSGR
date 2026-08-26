"""出征面板 Mixin — 章节选择、地图节点导航与进入出征准备。"""

from __future__ import annotations

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
    TOTAL_CHAPTERS,
    MapPanel,
)
from autowsgr.ui.utils import click_and_wait_for_page
from autowsgr.vision import PixelChecker


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.vision import OCREngine


_log = get_logger('ui')

LOOT_MAX = 50
"""战利品 (胖次) 上限, 固定值。"""

SHIP_MAX = 500
"""舰船上限, 固定值。"""


# ── 数据类 ──


@dataclass(frozen=True, slots=True)
class LootShipCount:
    """出征面板右上角的掉落计数。

    Attributes
    ----------
    loot:
        战利品 (胖次) 已获取数量, 识别失败时为 ``None``。
    loot_max:
        战利品上限, 固定 50。
    ship:
        舰船已获取数量, 识别失败时为 ``None``。
    ship_max:
        舰船上限, 固定 500。
    """

    loot: int | None = None
    loot_max: int = LOOT_MAX
    ship: int | None = None
    ship_max: int = SHIP_MAX


# ── 独立识别函数 ──

_OCR_ALLOWLIST = '0123456789/|'
"""OCR 字符白名单。包含 ``/`` 和 ``|`` 使 OCR 正确识别斜线而非误读为 ``1``。"""


def _parse_numerator(text: str, max_val: int) -> int:
    """从 ``"X/Y"`` 格式的 OCR 文本中提取分子 (``/`` 前的数字)。

    - 优先按 ``/`` 或 ``|`` 分割取第一段。
    - 回退: 若无分隔符, 按已知分母剥离末尾后缀。
    """
    # 优先: 按 "/" 或 "|" 分割
    for sep in ('/', '|'):
        if sep in text:
            left = text.split(sep, 1)[0]
            digits = ''.join(c for c in left if c.isdigit())
            if digits:
                return int(digits)
            raise ValueError(f'分子部分无数字: "{text}"')

    # 回退: OCR 偶尔把 "/" 识别为 "1", 导致纯数字串如 "17150"。
    # 已知分母为 max_val, 则后缀为 "1" + str(max_val)。
    digits = ''.join(c for c in text if c.isdigit())
    if not digits:
        raise ValueError(f'文本中无数字: "{text}"')
    suffix = '1' + str(max_val)
    if digits.endswith(suffix) and len(digits) > len(suffix):
        return int(digits[: -len(suffix)])
    # 无 "1" 前缀: 可能分母直接拼接
    denom_str = str(max_val)
    if digits.endswith(denom_str) and len(digits) > len(denom_str):
        return int(digits[: -len(denom_str)])
    return None


def recognize_loot_count(screen: np.ndarray, ocr: OCREngine) -> int | None:
    """识别出征面板战利品 (胖次) 已获取数量。

    OCR ``X/50`` 区域并提取 ``/`` 前的数字, 上限固定为 50。
    """
    img = PixelChecker.crop(screen, *LOOT_COUNT_CROP)
    text = ocr.recognize_single(img, allowlist=_OCR_ALLOWLIST).text.strip()
    if not text:
        _log.warning('[UI] 战利品数量 OCR 无结果')
        return None
    count = _parse_numerator(text, LOOT_MAX)
    if count > 50 and str(count).endswith('1'):
        count = int(str(count)[:-1])  # 可能 OCR 把 "/50" 识别成 "150"
    if count is not None:
        _log.info('[UI] 战利品数量: {}/{}', count, LOOT_MAX)
    else:
        _log.warning("[UI] 战利品数量 OCR 解析失败: '{}'", text)
    return count


def recognize_ship_count(screen: np.ndarray, ocr: OCREngine) -> int | None:
    """识别出征面板舰船已获取数量。

    OCR ``X/500`` 区域并提取 ``/`` 前的数字, 上限固定为 500。
    """
    img = PixelChecker.crop(screen, *SHIP_COUNT_CROP)
    text = ocr.recognize_single(img, allowlist=_OCR_ALLOWLIST).text.strip()
    if not text:
        _log.warning('[UI] 舰船数量 OCR 无结果')
        return None
    count = _parse_numerator(text, SHIP_MAX)
    if count is not None:
        _log.info('[UI] 舰船数量: {}/{}', count, SHIP_MAX)
    else:
        _log.warning("[UI] 舰船数量 OCR 解析失败: '{}'", text)
    return count


class SortiePanelMixin(BaseMapPage):
    """Mixin: 出征面板操作 — 选择章节 / 地图节点 / 进入出征准备。"""

    # ═══════════════════════════════════════════════════════════════════════
    # 章节 / 地图导航
    # ═══════════════════════════════════════════════════════════════════════

    def click_chapter(self, num: int):
        """点击侧边栏章节。

        若目标章在可视范围内则直接点击；否则先在侧边栏区域滑动将列表
        滚动到目标章附近，再点击。滚动后重新识别高亮位置保证坐标有效。

        Parameters
        ----------
        num:
            跳转数量, 正数为向下跳转, 负数为向上跳转。
            允许输入[-3, 3]。
        """
        if not -3 <= num <= 3:
            raise ValueError(f'跳转数量必须为 -3 到 3, 收到: {num}')
        if num == 0:
            return

        y_min, y_max = SIDEBAR_SCAN_Y_RANGE
        safe_min = y_min + 0.04   # 安全上内边距 (避免点到边缘空白)
        safe_max = y_max - 0.04   # 安全下内边距

        # ── 第 1 轮: 截图定位当前选中章 ──
        screen = self._ctrl.screenshot()
        sel_y = self.find_selected_chapter_y(screen)
        if sel_y is None:
            _log.warning('[UI] 无法定位选中章, 尝试先轻滑复位侧边栏')
            # 无法定位时先小幅上下滑动让列表复位, 给一次重试机会
            if num > 0:
                self._ctrl.swipe(SIDEBAR_CLICK_X, 0.78, SIDEBAR_CLICK_X, 0.22, duration=0.35)
            else:
                self._ctrl.swipe(SIDEBAR_CLICK_X, 0.22, SIDEBAR_CLICK_X, 0.78, duration=0.35)
            time.sleep(0.25)
            screen = self._ctrl.screenshot()
            sel_y = self.find_selected_chapter_y(screen)
            if sel_y is None:
                _log.warning('[UI] 侧边栏复位后仍无法定位选中章, 跳过跳转')
                return

        target_y = sel_y + num * CHAPTER_SPACING
        _log.info(
            '[UI] 地图页面→跳转章节 {}  sel_y={:.3f}→target_y={:.3f}',
            num, sel_y, target_y,
        )

        # ── 第 2 轮: 目标超出安全范围 → 先滑动侧边栏滚动列表 ──
        if not (safe_min <= target_y <= safe_max):
            _log.debug(
                '[UI] 目标 y={:.3f} 超出安全区 [{:.2f},{:.2f}], 先滑动侧边栏',
                target_y, safe_min, safe_max,
            )
            direction = 1 if num > 0 else -1  # +1=想往下跳(列表需向上滚)
            # 滑动幅度: 每条约 CHAPTER_SPACING, 再多滑一点作余量
            delta_y = abs(num) * CHAPTER_SPACING + 0.04
            if direction == 1:
                # 列表向上滚动: 手指从下向上滑
                from_y = min(safe_max, sel_y + 0.08)
                to_y = max(safe_min, from_y - delta_y - 0.02)
            else:
                # 列表向下滚动: 手指从上向下滑
                from_y = max(safe_min, sel_y - 0.08)
                to_y = min(safe_max, from_y + delta_y + 0.02)

            self._ctrl.swipe(
                SIDEBAR_CLICK_X, from_y,
                SIDEBAR_CLICK_X, to_y,
                duration=0.4,
            )
            time.sleep(CHAPTER_NAV_DELAY)  # 等滚动动画停下

            # 滑动后重新定位选中章
            screen = self._ctrl.screenshot()
            sel_y = self.find_selected_chapter_y(screen)
            if sel_y is None:
                _log.warning('[UI] 滑动侧边栏后仍无法定位选中章, 点击屏幕中部附近兜底')
                # 兜底: 按方向在安全区中部点击 (至少触发一次切换)
                fallback_y = (safe_min + safe_max) / 2 + direction * CHAPTER_SPACING
                self._ctrl.click(SIDEBAR_CLICK_X, fallback_y)
                return
            target_y = sel_y + num * CHAPTER_SPACING
            # 滑动后再次截断到安全范围 (应已在范围内, 留双重保险)
            target_y = max(safe_min, min(safe_max, target_y))

        self._ctrl.click(SIDEBAR_CLICK_X, target_y)

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

        confirm_hits = 0

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
            while remaining > 0:
                step = min(remaining, 3) * direction
                self.click_chapter(step)
                remaining -= abs(step)
                _log.info(f'[UI] 章节导航: 跳转{step}章, 剩余{remaining}章')
                time.sleep(CHAPTER_NAV_DELAY * abs(step))

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
