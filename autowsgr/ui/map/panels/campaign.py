"""战役面板 Mixin — 难度选择与进入战役出征准备。"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from autowsgr.infra.logger import get_logger
from autowsgr.types import PageName
from autowsgr.ui.map.base import BaseMapPage
from autowsgr.ui.map.data import (
    CAMPAIGN_POSITIONS,
    CLICK_DIFFICULTY,
    DIFFICULTY_EASY_COLOR,
    DIFFICULTY_HARD_COLOR,
    LOOT_COUNT_CROP,
    SHIP_COUNT_CROP,
    MapPanel,
)
from autowsgr.ui.page import wait_for_page
from autowsgr.vision import PixelChecker


_log = get_logger('ui')


class CampaignPanelMixin(BaseMapPage):
    """Mixin: 战役面板操作 — 难度识别 / 切换 / 进入战役。"""

    # ── 查询 ─────────────────────────────────────────────────────────────

    def recognize_difficulty(self) -> str | None:
        """通过检测难度按钮颜色识别当前难度。

        切换图标为蓝色时，说明可以切换为 easy，当前为 hard；反之亦然。

        Returns
        -------
        str | None
            ``"easy"`` / ``"hard"``，识别失败返回 ``None``。

        Raises
        ------
        RuntimeError
            超过重试次数仍无法识别。
        """
        retry = 0
        while retry < 10:
            screen = self._ctrl.screenshot()
            px = PixelChecker.get_pixel(screen, *CLICK_DIFFICULTY)
            if px.near(DIFFICULTY_EASY_COLOR, tolerance=50):
                return 'hard'
            elif px.near(DIFFICULTY_HARD_COLOR, tolerance=50):
                return 'easy'
            time.sleep(0.25)
            retry += 1

        _log.warning('[UI] 无法识别难度: 检测点颜色不匹配简单或困难')
        raise RuntimeError('无法识别战役难度')

    # ── 操作 ─────────────────────────────────────────────────────────────

    def enter_campaign(
        self,
        map_index: int = 2,
        difficulty: str = 'hard',
        campaign_name: str = '未知',
    ) -> None:
        """进入战役: 选择难度和战役类型，直接到达出征准备页面。

        Parameters
        ----------
        map_index:
            战役编号 (1–5: 航母/潜艇/驱逐/巡洋/战列)。
        difficulty:
            难度 ``"easy"`` 或 ``"hard"``。
        campaign_name:
            战役名称 (仅用于日志)。

        Raises
        ------
        ValueError
            战役编号或难度无效。
        NavigationError
            导航超时。
        """
        from autowsgr.ui.battle.preparation import BattlePreparationPage

        if map_index not in CAMPAIGN_POSITIONS:
            raise ValueError(f'战役编号必须为 1–5，收到: {map_index}')
        if difficulty not in ('easy', 'hard'):
            raise ValueError(f'难度必须为 easy 或 hard，收到: {difficulty}')

        _log.info(
            '[UI] 地图页面 → 进入战役 {} ({})',
            campaign_name,
            difficulty,
        )

        # 1. 切换到战役面板
        self.ensure_panel(MapPanel.BATTLE)

        # 2. 选择难度
        if self.recognize_difficulty() != difficulty:
            self._ctrl.click(*CLICK_DIFFICULTY)
        while self.recognize_difficulty() != difficulty:
            _log.debug('[UI] 等待难度切换到 {}…', difficulty)
            time.sleep(0.25)
        time.sleep(0.75)

        # 3. 选择战役
        self._ctrl.click(*CAMPAIGN_POSITIONS[map_index])
        time.sleep(0.5)

        # 等待到达出征准备
        wait_for_page(
            self._ctrl,
            checker=BattlePreparationPage.is_current_page,
            source=f'地图-战役 {campaign_name}',
            target=PageName.BATTLE_PREP,
        )

    # ── 今日获取数量 ──────────────────────────────────────────────────────

    @dataclass
    class AcquisitionCounts:
        """今日获取数量。"""

        ship_count: int | None = None
        """今日已获取舰船数量。"""
        ship_max: int | None = None
        """今日舰船获取上限。"""
        loot_count: int | None = None
        """今日已获取战利品数量。"""
        loot_max: int | None = None
        """今日战利品获取上限。"""

    def _recognize_acquisition_counts(
        self,
        screen,
    ) -> AcquisitionCounts:
        """从截图中 OCR 识别今日舰船与战利品获取数量。

        读取出征面板右上角的 ``X/500`` (舰船) 和 ``X/50`` (战利品) 文本。

        Parameters
        ----------
        screen:
            当前截图 (numpy 数组)。

        Returns
        -------
        AcquisitionCounts
            识别到的数量信息，无法识别的字段为 ``None``。
        """
        result = self.AcquisitionCounts()
        ocr = self._ocr
        if ocr is None:
            _log.warning('[UI] 未提供 OCR 引擎，无法识别获取数量')
            return result

        # ── 战利品 ──
        loot_img = PixelChecker.crop(screen, *LOOT_COUNT_CROP)
        loot_text = ocr.recognize_single(loot_img, allowlist='0123456789/').text.strip()
        parsed = self._parse_fraction(loot_text)
        if parsed is not None:
            result.loot_count, result.loot_max = parsed
            _log.info('[UI] 今日战利品: {}/{}', result.loot_count, result.loot_max)
        else:
            _log.warning("[UI] 战利品数量识别失败: '{}'", loot_text)

        # ── 舰船 ──
        ship_img = PixelChecker.crop(screen, *SHIP_COUNT_CROP)
        ship_text = ocr.recognize_single(ship_img, allowlist='0123456789/').text.strip()
        parsed = self._parse_fraction(ship_text)
        if parsed is not None:
            result.ship_count, result.ship_max = parsed
            _log.info('[UI] 今日舰船: {}/{}', result.ship_count, result.ship_max)
        else:
            _log.warning("[UI] 舰船数量识别失败: '{}'", ship_text)

        return result

    def get_acquisition_counts(self) -> AcquisitionCounts:
        """获取今日舰船与战利品获取数量。

        自动确保当前位于出征面板，然后截图并执行 OCR 识别。

        Returns
        -------
        AcquisitionCounts
            识别到的数量信息。
        """
        self.ensure_panel(MapPanel.SORTIE)
        time.sleep(0.5)
        screen = self._ctrl.screenshot()
        return self._recognize_acquisition_counts(screen)

    @staticmethod
    def _parse_fraction(text: str) -> tuple[int, int] | None:
        """解析 ``"X/Y"`` 格式文本为 ``(X, Y)``。

        容错处理: OCR 可能把 ``/`` 识别为 ``1`` 或其他字符，
        对常见格式做特殊处理。
        """
        # 标准格式: "12/500"
        m = re.match(r'(\d+)\s*/\s*(\d+)', text)
        if m:
            return int(m.group(1)), int(m.group(2))

        # OCR 把 "/" 识别为 "1" 等情况: "121500" → 尝试按已知上限拆分
        digits = re.sub(r'\D', '', text)
        if digits:
            # 尝试常见上限: 50 (战利品) 和 500 (舰船)
            for max_val_str in ('500', '50'):
                if digits.endswith(max_val_str):
                    current = digits[: -len(max_val_str)]
                    if current.isdigit():
                        return int(current), int(max_val_str)
        return None
