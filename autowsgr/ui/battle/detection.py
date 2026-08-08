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
from autowsgr.types import ShipDamageState, ShipType
from autowsgr.ui.battle.base import BaseBattlePreparation
from autowsgr.ui.utils.ship_list import extract_ship_type_from_text
from autowsgr.vision import PixelChecker
from autowsgr.vision.ocr_rules import (
    LEVEL_NOISY_PATTERN,
    LEVEL_PATTERN,
    LEVEL_SHORT_PATTERN,
    EasyOCRProfile,
    is_valid_ship_level,
    normalize_level_digits,
)

from .blood import classify_blood
from .constants import (
    BLOOD_BAR_PROBE,
    SHIP_LEVEL_CROP,
    SHIP_TYPE_CROP,
)


if TYPE_CHECKING:
    from collections.abc import Collection

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

    def to_ships(self, names: list[str | None] | list[str] | None = None) -> list[Ship]:
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
                name = names[i] or ''
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
        slots: Collection[int] | None = None,
    ) -> dict[int, int | None]:
        """从准备页截图中 OCR 识别每艘舰船的等级。

        读取各舰船卡片上的 ``Lv.XX`` / ``Lv XX`` 文本，提取数字部分。

        Parameters
        ----------
        screen:
            出征准备页的截图。
        slots:
            仅识别指定槽位。未指定时按原逻辑先检测血条，再识别全部有船槽位。

        Returns
        -------
        dict[int, int | None]
            槽位号 (0-5) → 等级。无法识别或无舰船则为 ``None``。
        """
        requested_slots = list(range(6)) if slots is None else sorted(set(slots))
        levels: dict[int, int | None] = dict.fromkeys(requested_slots)
        ocr = self._preferred_ocr
        if ocr is None:
            _log.warning('[UI] 未提供 OCR 引擎，无法识别舰船等级')
            return levels

        if slots is None:
            damage = self.detect_ship_damage(screen)
            target_slots = [
                slot for slot in requested_slots if damage.get(slot) != ShipDamageState.NO_SHIP
            ]
        else:
            target_slots = requested_slots

        for slot in target_slots:
            crop_region = SHIP_LEVEL_CROP.get(slot)
            if crop_region is None:
                continue

            prepared = PixelChecker.crop(screen, *crop_region)
            if self._ship_ocr is None:
                prepared = cv2.resize(
                    prepared,
                    None,
                    fx=2,
                    fy=2,
                    interpolation=cv2.INTER_CUBIC,
                )
                gray = cv2.cvtColor(prepared, cv2.COLOR_RGB2GRAY)
                _, binary = cv2.threshold(
                    gray,
                    0,
                    255,
                    cv2.THRESH_BINARY + cv2.THRESH_OTSU,
                )
                prepared = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)

            # 两种引擎统一使用等级字符集和同一套结果解析规则。
            ocr_results = ocr.recognize_line(
                prepared,
                easyocr_profile=EasyOCRProfile.FLEET_SHIP_LEVEL,
            )
            level = self._best_level_from_results(ocr_results)
            levels[slot] = level

            _log.debug(
                '[准备页] 等级OCR原始及后处理: 物理槽位={} raw={} parsed={}',
                slot + 1,
                ocr_results,
                level,
            )
        return levels

    # ── 舰种 OCR ─────────────────────────────────────────────────────────

    def _recognize_fleet_ship_types(
        self,
        screen: np.ndarray,
        slots: Collection[int] | None = None,
    ) -> dict[int, ShipType | None]:
        """从准备页截图中 OCR 识别每艘舰船的舰种。

        读取各舰船卡片上的舰种文本 (如 ``轻巡(J国)``)，用于首次换船快照，
        使已就位的目标舰船可以跳过船池二次确认。
        """
        requested_slots = list(range(6)) if slots is None else sorted(set(slots))
        ship_types: dict[int, ShipType | None] = dict.fromkeys(requested_slots)
        ocr = self._preferred_ocr
        if ocr is None:
            _log.warning('[UI] 未提供 OCR 引擎，无法识别舰种')
            return ship_types

        if slots is None:
            damage = self.detect_ship_damage(screen)
            target_slots = [
                slot for slot in requested_slots if damage.get(slot) != ShipDamageState.NO_SHIP
            ]
        else:
            target_slots = requested_slots

        for slot in target_slots:
            crop_region = SHIP_TYPE_CROP.get(slot)
            if crop_region is None:
                continue

            cropped = PixelChecker.crop(screen, *crop_region)
            # 4x 上采样提升小字 OCR 准确率 (对齐等级识别)
            upscaled = cv2.resize(
                cropped,
                (cropped.shape[1] * 4, cropped.shape[0] * 4),
            )
            ocr_results = ocr.recognize(upscaled)
            ship_type = self._best_ship_type_from_results(ocr_results)
            ship_types[slot] = ship_type

            _log.debug(
                '[准备页] 舰种OCR原始及后处理: 物理槽位={} raw={} parsed={}',
                slot + 1,
                ocr_results,
                ship_type.value if ship_type is not None else None,
            )
        return ship_types

    @staticmethod
    def _best_ship_type_from_results(results: list) -> ShipType | None:
        """从多个 OCR 结果中提取唯一舰种；歧义或无法识别返回 None。"""
        detected: ShipType | None = None
        for r in results:
            text = str(getattr(r, 'text', '')).strip()
            if not text:
                continue
            ship_type = extract_ship_type_from_text(text)
            if ship_type is None:
                continue
            if detected is not None and detected != ship_type:
                return None
            detected = ship_type
        return detected

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

        def parse_digits(raw: str) -> int | None:
            normalized = normalize_level_digits(raw)
            if normalized is None:
                return None
            value = int(normalized)
            return value if is_valid_ship_level(value) else None

        # 1) 优先使用共享规则解析标准、噪声和缺失 V 的等级标签。
        for pattern in (LEVEL_PATTERN, LEVEL_NOISY_PATTERN, LEVEL_SHORT_PATTERN):
            match = pattern.search(text)
            if match is None:
                continue
            level = parse_digits(match.group(1))
            if level is not None:
                return level

        # 2) 兼容缺失 L、只剩 V.XX 的结果。
        m = re.search(r'(?i)v\.?\s*([0-9liodsb]{1,3})', text)
        if m:
            return parse_digits(m.group(1))

        # 3) 回退: 取最后一个合法数字 (跳过星级等前缀噪声)
        for m in reversed(list(re.finditer(r'\d+', text))):
            val = int(m.group())
            if is_valid_ship_level(val):
                return val
            # 3 位以上超出等级上限时尝试去掉首位 (星级粘连)
            s = m.group()
            if len(s) >= 3:
                val2 = int(s[1:])
                if is_valid_ship_level(val2):
                    return val2

        return None

    @classmethod
    def _best_level_from_results(cls, results: list) -> int | None:
        """从多个 OCR 结果中选取最佳等级值。

        优先选择包含 LV/V 模式或可完整拼接的结果。独立数字结果按
        OCR 置信度排序，避免低置信度噪声抢在真实等级前面。
        """
        combined = ''.join(r.text.strip() for r in results)
        if re.search(r'(?i)v', combined) or LEVEL_SHORT_PATTERN.search(combined):
            combined_level = cls._parse_level(combined)
            if combined_level is not None:
                return combined_level

        compact = re.sub(r'[.\s]', '', combined)
        if re.fullmatch(r'(?i)(?:[dsb]|[0-9liodsb]{2,3})', compact):
            normalized = normalize_level_digits(compact)
            if normalized is not None:
                combined_level = int(normalized)
                if is_valid_ship_level(combined_level):
                    return combined_level

        # 按优先级分桶: lv_match > fallback；桶内按置信度选择。
        lv_candidates: list[tuple[float, int]] = []
        fallback_candidates: list[tuple[float, int]] = []

        for r in results:
            text = r.text.strip()
            if not text:
                continue

            val = cls._parse_level(text)
            if val is None:
                continue
            candidates = lv_candidates if re.search(r'(?i)v', text) else fallback_candidates
            candidates.append((r.confidence, val))

        if lv_candidates:
            return max(lv_candidates, key=lambda item: item[0])[1]
        if fallback_candidates:
            return max(fallback_candidates, key=lambda item: item[0])[1]
        return None
