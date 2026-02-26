"""出征准备 — 舰船状态检测与舰队信息识别。

提供血量检测、等级 OCR 识别等静态 / 实例方法。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.types import ShipDamageState
from autowsgr.ui.battle.base import BaseBattlePreparation
from autowsgr.vision import PixelChecker

from .blood import classify_blood
from .constants import (
    BLOOD_BAR_PROBE,
    SHIP_LEVEL_CROP,
)


if TYPE_CHECKING:
    import numpy as np


_log = get_logger('ui.preparation')


# ═══════════════════════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FleetInfo:
    """舰队详细信息。"""

    fleet_id: int | None = None
    """舰队编号 (1–4)，``None`` 表示未指定。"""
    ship_levels: dict[int, int | None] = field(default_factory=dict)
    """槽位号 (0–5) → 等级，无法识别或无舰船则为 ``None``。"""
    ship_damage: dict[int, ShipDamageState] = field(default_factory=dict)
    """槽位号 (0–5) → 血量状态。"""


# ═══════════════════════════════════════════════════════════════════════════════
# Mixin
# ═══════════════════════════════════════════════════════════════════════════════


class DetectionMixin(BaseBattlePreparation):
    """舰船状态检测 Mixin。

    依赖 :class:`~autowsgr.ui.battle.base.BaseBattlePreparation` 提供的
    ``_ctrl``, ``_ocr``, ``get_selected_fleet``, ``select_fleet``。
    """

    # ── 血量检测 ──────────────────────────────────────────────────────────

    @staticmethod
    def detect_ship_damage(screen: np.ndarray) -> dict[int, ShipDamageState]:
        """检测 6 个舰船槽位的血量状态。

        Returns
        -------
        dict[int, ShipDamageState]
            槽位号 (0–5) → 血量状态。
        """
        result: dict[int, ShipDamageState] = {}
        for slot, (x, y) in BLOOD_BAR_PROBE.items():
            pixel = PixelChecker.get_pixel(screen, x, y)
            result[slot] = classify_blood(pixel)
        _log.debug(
            '[准备页] 血量检测: {}',
            ' | '.join(f'槽{i}={result[i].name}' for i in range(len(result))),
        )
        return result

    # ── 等级 OCR ──────────────────────────────────────────────────────────

    def _recognize_fleet_levels(
        self,
        screen: np.ndarray,
    ) -> dict[int, int | None]:
        """从准备页截图中 OCR 识别每艘舰船的等级。

        读取各舰船卡片上的 ``Lv.XX`` / ``Lv XX`` 文本，提取数字部分。

        Parameters
        ----------
        screen:
            出征准备页的截图。

        Returns
        -------
        dict[int, int | None]
            槽位号 (0–5) → 等级。无法识别或无舰船则为 ``None``。
        """
        levels: dict[int, int | None] = {}
        ocr = self._ocr
        if ocr is None:
            _log.warning('[UI] 未提供 OCR 引擎，无法识别舰船等级')
            return dict.fromkeys(range(6))

        # 先检测哪些槽位有舰船
        damage = self.detect_ship_damage(screen)

        for slot in range(6):
            if damage.get(slot) == ShipDamageState.NO_SHIP:
                levels[slot] = None
                continue

            crop_region = SHIP_LEVEL_CROP.get(slot)
            if crop_region is None:
                levels[slot] = None
                continue

            cropped = PixelChecker.crop(screen, *crop_region)
            text = ocr.recognize_single(cropped, allowlist='0123456789Llv.V').text.strip()

            level = self._parse_level(text)
            levels[slot] = level

            if level is not None:
                _log.debug('[UI] 槽位{} 等级: Lv.{}', slot, level)
            else:
                _log.debug("[UI] 槽位{} 等级识别失败: '{}'", slot, text)

        _log.info(
            '[准备页] 等级检测: {}',
            ' | '.join(
                f'槽{i}={"Lv." + str(levels[i]) if levels[i] is not None else "无"}'
                for i in range(6)
            ),
        )
        return levels

    # ── 舰队信息聚合 ─────────────────────────────────────────────────────

    def detect_fleet_info(
        self,
        fleet_id: int | None = None,
    ) -> FleetInfo:
        """识别指定舰队的详细信息（等级、血量）。

        若 ``fleet_id`` 不为 ``None`` 且与当前选中的舰队不同，
        将先切换到目标舰队。

        Parameters
        ----------
        fleet_id:
            目标舰队编号 (1–4)。为 ``None`` 则不切换舰队。

        Returns
        -------
        FleetInfo
            包含舰队编号、各舰船等级和血量信息。
        """
        if fleet_id is not None:
            screen = self._ctrl.screenshot()
            current_fleet = self.get_selected_fleet(screen)
            if current_fleet != fleet_id:
                self.select_fleet(fleet_id)
                time.sleep(0.5)

        screen = self._ctrl.screenshot()
        actual_fleet = self.get_selected_fleet(screen)
        damage = self.detect_ship_damage(screen)
        levels = self._recognize_fleet_levels(screen)

        info = FleetInfo(
            fleet_id=actual_fleet,
            ship_levels=levels,
            ship_damage=damage,
        )

        _log.info(
            '[UI] 舰队 {} 信息: {}',
            actual_fleet or '?',
            ' | '.join(
                f'槽{i}=Lv.{levels.get(i, "?")} {damage[i].name if i in damage else "?"}'
                for i in range(6)
            ),
        )
        return info

    # ── 工具 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_level(text: str) -> int | None:
        """解析等级文本。

        支持格式: ``"Lv.120"``, ``"Lv120"``, ``"lv 98"``, ``"120"`` 等。
        """
        cleaned = re.sub(r'(?i)^l\s*v\.?\s*', '', text)
        m = re.search(r'(\d+)', cleaned)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 200:
                return val
        return None
