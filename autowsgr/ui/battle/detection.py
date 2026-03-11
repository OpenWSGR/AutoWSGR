"""出征准备 — 舰船状态检测与舰队信息识别。

提供血量检测、等级 OCR 识别等静态 / 实例方法。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import cv2

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

    from autowsgr.context.ship import Ship


_log = get_logger('ui.preparation')


# ═══════════════════════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FleetInfo:
    """舰队详细信息。"""

    fleet_id: int | None = None
    """舰队编号 (1-4)，``None`` 表示未指定。"""
    ship_levels: dict[int, int | None] = field(default_factory=dict)
    """槽位号 (0-5) → 等级，无法识别或无舰船则为 ``None``。"""
    ship_damage: dict[int, ShipDamageState] = field(default_factory=dict)
    """槽位号 (0-5) → 血量状态。"""

    def to_ships(self, names: list[str | None] | None = None) -> list[Ship]:
        """将舰队信息转换为 Ship 列表。

        Parameters
        ----------
        names:
            可选的舰船名称列表 (0-indexed, 与槽位对应)。
            ``None`` 元素或缺少的索引将使用空字符串。

        Returns
        -------
        list[Ship]
            按槽位顺序排列，跳过无舰船的槽位。
        """
        from autowsgr.context.ship import Ship

        ships: list[Ship] = []
        for i in range(6):
            damage = self.ship_damage.get(i, ShipDamageState.NORMAL)
            if damage == ShipDamageState.NO_SHIP:
                continue
            name = ''
            if names and i < len(names) and names[i] is not None:
                name = names[i]
            ships.append(
                Ship(
                    name=name,
                    level=self.ship_levels.get(i) or 0,
                    damage_state=damage,
                )
            )
        return ships


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
            槽位号 (0-5) → 血量状态。
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
            槽位号 (0-5) → 等级。无法识别或无舰船则为 ``None``。
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
            # 4x 上采样提升小字 OCR 准确率 (对齐 legacy check_level)
            upscaled = cv2.resize(
                cropped,
                (cropped.shape[1] * 4, cropped.shape[0] * 4),
            )

            # 用多结果模式避免 recognize_single 选中噪声文本
            level = self._best_level_from_results(
                ocr.recognize(upscaled, allowlist='0123456789Llv.V'),
            )
            levels[slot] = level

            if level is not None:
                _log.debug('[UI] 槽位{} 等级: Lv.{}', slot, level)
            else:
                _log.debug('[UI] 槽位{} 等级识别失败', slot)

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
            目标舰队编号 (1-4)。为 ``None`` 则不切换舰队。

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
        OCR 常见噪声: ``"0.106"`` (L 误识为 0), ``"1V.31"`` (前缀数字),
        ``"497"`` (星级数字粘连) 等。
        """
        # 1) 尝试匹配 [L10I]V.XX 模式 (L 可被 OCR 误识为 1/0/I)
        m = re.search(r'(?i)[l10i]\s*v\.?\s*(\d{1,3})', text)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 200:
                return val

        # 2) 尝试匹配 V.XX 模式 (缺失 L)
        m = re.search(r'(?i)v\.?\s*(\d{1,3})', text)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 200:
                return val

        # 3) 回退: 取最后一个合法数字 (跳过星级等前缀噪声)
        for m in reversed(list(re.finditer(r'\d+', text))):
            val = int(m.group())
            if 1 <= val <= 200:
                return val
            # 3 位以上数字 > 200 时尝试去掉首位 (星级粘连)
            s = m.group()
            if val > 200 and len(s) >= 3:
                val2 = int(s[1:])
                if 1 <= val2 <= 200:
                    return val2

        return None

    @classmethod
    def _best_level_from_results(cls, results: list) -> int | None:
        """从多个 OCR 结果中选取最佳等级值。

        优先选择包含 LV/V 模式的结果 (更可能是等级文本),
        其次选择纯数字回退结果，避免噪声文本干扰。
        """
        # 按优先级分桶: lv_match > fallback
        lv_candidates: list[int] = []
        fallback_candidates: list[int] = []

        for r in results:
            text = r.text.strip()
            if not text:
                continue

            # 有 V 字母 → 大概率是 LV.XX
            if re.search(r'(?i)v', text):
                val = cls._parse_level(text)
                if val is not None:
                    lv_candidates.append(val)
            else:
                val = cls._parse_level(text)
                if val is not None:
                    fallback_candidates.append(val)

        if lv_candidates:
            return lv_candidates[0]
        if fallback_candidates:
            return fallback_candidates[0]
        return None
