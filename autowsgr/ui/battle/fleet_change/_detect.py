"""准备页舰队 OCR 检测。

1. 截取准备页下方的舰名区域。
2. 调用 OCR 读取区域内的文字和坐标。
3. 按文字横坐标从左到右整理结果。
4. 修正常见 OCR 文本后在完整船池中匹配舰名。
5. 根据文字中心位置判断所属舰队槽位。
6. expected_names 按槽位提供本次换船的目标舰名。
7. OCR 文本只能使用其所在槽位的目标解决歧义。
8. 目标上下文只接受明确片段或编辑距离内唯一的最近舰名。
9. 不传 expected_names 时继续使用完整船池匹配。
最终返回六个槽位的舰名，空槽使用 None。
普通检测和旧决战流程不会启用目标上下文。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.constants import SHIPNAMES, normalize_ship_name, ship_name_identity
from autowsgr.infra.logger import get_logger
from autowsgr.types import ShipDamageState, ShipType
from autowsgr.ui.battle.base import BaseBattlePreparation
from autowsgr.ui.battle.detection import DetectionMixin
from autowsgr.vision.ocr import (
    _fuzzy_match,
    apply_ship_patches,
)


# 仅在类型检查时导入运行逻辑不需要的类型。
if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import numpy as np


_log = get_logger('ui.preparation')

_NAME_STRIP_Y1: float = 435 / 720
_NAME_STRIP_Y2: float = 462 / 720

_SLOT_X_CENTERS: tuple[float, ...] = (
    0.1146,
    0.2292,
    0.3438,
    0.4583,
    0.5729,
    0.6875,
)

_SHIP_FUZZY_THRESHOLD: int = 2


@dataclass(slots=True)
class FleetSnapshot:
    """准备页六个槽位累计得到的最终 OCR 信息。"""

    names: list[str | None]
    occupied: list[bool]
    ship_types: list[ShipType | None] | None = None
    """槽位号 (0-5) → 舰种；未请求详细信息时整个字段为 ``None``。"""
    ship_levels: list[int | None] | None = None
    """槽位号 (0-5) → 等级；未请求详细信息时整个字段为 ``None``。"""

    @property
    def unknown_slots(self) -> list[int]:
        """返回有舰船但舰名 OCR 未识别的槽位。"""
        return [
            slot
            for slot, (name, occupied) in enumerate(zip(self.names, self.occupied, strict=True))
            if name is None and occupied
        ]

    @property
    def unknown_type_slots(self) -> list[int]:
        """返回有舰船但舰种 OCR 未识别的槽位。"""
        ship_types = self.ship_types or [None] * 6
        return [
            slot
            for slot, (ship_type, occupied) in enumerate(
                zip(ship_types, self.occupied, strict=True)
            )
            if ship_type is None and occupied
        ]

    @property
    def unknown_level_slots(self) -> list[int]:
        """返回有舰船但等级 OCR 未识别的槽位。"""
        ship_levels = self.ship_levels or [None] * 6
        return [
            slot
            for slot, (level, occupied) in enumerate(zip(ship_levels, self.occupied, strict=True))
            if level is None and occupied
        ]

    @property
    def has_unknown_details(self) -> bool:
        """返回是否仍有需要定点补识别的槽位字段。"""
        return bool(self.unknown_slots or self.unknown_type_slots or self.unknown_level_slots)


# 负责识别准备页当前六个舰队槽位。
class FleetDetectMixin(BaseBattlePreparation):
    """提供准备页舰队 OCR 检测能力。"""

    # 从剩余目标舰名中查找唯一的最近匹配。
    @staticmethod
    def _match_context_ship_name(
        text: str,
        expected_names: Sequence[str | None],
    ) -> str | None:
        """在指定槽位目标中进行安全匹配，歧义时返回 None。"""
        candidates = [
            name.strip()
            for name in dict.fromkeys(expected_names)
            if isinstance(name, str) and name.strip()
        ]
        # OCR 文本或目标舰名为空时不能进行上下文匹配。
        if not text or not candidates:
            return None

        matched = _fuzzy_match(apply_ship_patches(text), candidates, threshold=3)
        if matched is not None:
            _log.debug("[准备页] 目标槽位匹配: '{}' -> '{}'", text, matched)
        return matched

    # 识别截图中的六个舰队槽位，并按需使用目标上下文补全舰名。
    def detect_fleet(
        self,
        screen: np.ndarray | None = None,
        *,
        expected_names: Sequence[str | None] | None = None,
        expected_pool: Sequence[str] | None = None,
    ) -> list[str | None]:
        """返回长度为六的舰名列表，未占用槽位返回 None。"""
        # 未传入截图时直接获取当前屏幕。
        if screen is None:
            screen = self._ctrl.screenshot()

        h, w = screen.shape[:2]
        y1 = int(_NAME_STRIP_Y1 * h)
        y2 = int(_NAME_STRIP_Y2 * h)
        strip = screen[y1:y2, :]

        results = sorted(
            self._preferred_ocr.recognize(strip),
            key=lambda result: (
                (result.bbox[0] + result.bbox[2]) / 2 if result.bbox is not None else float('inf')
            ),
        )
        expected_slots = (
            [normalize_ship_name(name) for name in list(expected_names)[:6]]
            if expected_names is not None
            else []
        )
        expected_slots += [None] * (6 - len(expected_slots))
        normalized_pool = [
            normalized
            for name in dict.fromkeys(expected_pool or ())
            if (normalized := normalize_ship_name(name)) is not None
        ]
        prepared_results = []
        for result in results:
            raw_text = result.text.strip()
            patched_text = apply_ship_patches(raw_text)
            pool_match = (
                _fuzzy_match(patched_text, SHIPNAMES, _SHIP_FUZZY_THRESHOLD)
                if raw_text and result.bbox is not None
                else None
            )
            prepared_results.append((result, raw_text, patched_text, pool_match))

        ships: list[str | None] = [None] * 6
        recognized_ocr: list[dict[str, object]] = []

        for r, raw_text, text, pool_match in prepared_results:
            # 空文字或没有坐标的 OCR 结果无法对应舰队槽位。
            if not raw_text or r.bbox is None:
                continue
            # 文本补丁改变识别结果时记录调试日志。
            if text != raw_text:
                _log.debug("[准备页] OCR raw='{}' -> patched='{}'", raw_text, text)
            cx_rel = (r.bbox[0] + r.bbox[2]) / 2 / w
            slot = min(
                range(6),
                key=lambda i, cx=cx_rel: abs(_SLOT_X_CENTERS[i] - cx),
            )
            matched = pool_match
            expected_name = expected_slots[slot]
            # 船池结果与本槽目标不一致时，只允许本槽目标参与消歧。
            if expected_name is not None and matched is None:
                context_match = self._match_context_ship_name(text, [expected_name])
                if context_match is not None:
                    matched = context_match
            # 位置尚未对齐时，全局目标池只能补救完整船池未识别的文字。
            elif matched is None and normalized_pool:
                matched = self._match_context_ship_name(text, normalized_pool)
            recognized_ocr.append(
                {
                    'slot': slot,
                    'raw': raw_text,
                    'patched': text,
                    'matched': matched,
                }
            )
            # 完整船池和目标上下文都无法识别时跳过该文字。
            if matched is None:
                _log.debug("[准备页] OCR '{}' -> 无匹配, 跳过", raw_text)
                continue
            ships[slot] = matched
            _log.debug("[准备页] 槽位 {} OCR -> '{}'", slot, matched)

        _log.info(
            '[准备页] 编队 OCR 识别: {}',
            recognized_ocr,
        )
        _log.info('[准备页] 当前舰队: {}', ships)
        return ships

    def _recognize_fleet_names_at_slots(
        self,
        screen: np.ndarray,
        slots: Sequence[int],
        *,
        expected_pool: Sequence[str] | None = None,
    ) -> dict[int, str | None]:
        """只裁切并识别指定槽位的舰名。"""
        ocr = self._preferred_ocr
        target_slots = sorted(set(slots))
        names: dict[int, str | None] = dict.fromkeys(target_slots)
        if ocr is None:
            _log.warning('[准备页] 未提供 OCR 引擎，无法补识别舰名')
            return names

        normalized_pool = [
            normalized
            for name in dict.fromkeys(expected_pool or ())
            if (normalized := normalize_ship_name(name)) is not None
        ]
        h, w = screen.shape[:2]
        y1 = int(_NAME_STRIP_Y1 * h)
        y2 = int(_NAME_STRIP_Y2 * h)
        for slot in target_slots:
            if not 0 <= slot < len(_SLOT_X_CENTERS):
                continue
            center = _SLOT_X_CENTERS[slot]
            left_center = _SLOT_X_CENTERS[max(slot - 1, 0)]
            right_center = _SLOT_X_CENTERS[min(slot + 1, 5)]
            left = center - (right_center - center) / 2 if slot == 0 else (left_center + center) / 2
            right = (
                center + (center - left_center) / 2 if slot == 5 else (center + right_center) / 2
            )
            crop = screen[y1:y2, max(0, int(left * w)) : min(w, int(right * w))]
            results = [result for result in ocr.recognize(crop) if result.text.strip()]
            if not results:
                _log.debug('[准备页] 槽位 {} 舰名单槽 OCR 无文本', slot)
                continue

            result = max(results, key=lambda item: item.confidence)
            raw_text = result.text.strip()
            patched_text = apply_ship_patches(raw_text)
            matched = _fuzzy_match(
                patched_text,
                SHIPNAMES,
                _SHIP_FUZZY_THRESHOLD,
            )
            if matched is None and normalized_pool:
                matched = self._match_context_ship_name(patched_text, normalized_pool)
            names[slot] = matched
            _log.debug(
                "[准备页] 槽位 {} 舰名单槽 OCR: '{}' -> '{}'",
                slot,
                raw_text,
                matched,
            )
        return names

    def detect_fleet_snapshot(
        self,
        *,
        expected_names: Sequence[str | None] | None = None,
        expected_pool: Sequence[str] | None = None,
        recognize_ship_details: bool = False,
    ) -> FleetSnapshot:
        """使用同一截图识别舰名和槽位占用状态。

        Parameters
        ----------
        recognize_ship_details:
            是否在当前截图额外识别各槽位舰名、舰种和等级。四阶段换船流程
            不启用该参数，而是通过 ``fill_missing_fleet_snapshot()`` 获取新截图。
        """
        screen = self._ctrl.screenshot()
        names = self.detect_fleet(
            screen,
            expected_names=expected_names,
            expected_pool=expected_pool,
        )
        damage = DetectionMixin.detect_ship_damage(screen)
        occupied = [
            names[slot] is not None
            or damage.get(slot, ShipDamageState.NO_SHIP) != ShipDamageState.NO_SHIP
            for slot in range(6)
        ]
        if recognize_ship_details:
            unknown_name_slots = [
                slot for slot in range(6) if occupied[slot] and names[slot] is None
            ]
            if unknown_name_slots:
                names_by_slot = self._recognize_fleet_names_at_slots(
                    screen,
                    unknown_name_slots,
                    expected_pool=expected_pool,
                )
                for slot in unknown_name_slots:
                    if names_by_slot.get(slot) is not None:
                        names[slot] = names_by_slot[slot]

            occupied_slots = [slot for slot in range(6) if occupied[slot]]
            types_by_slot = self._recognize_fleet_ship_types(screen, occupied_slots)
            levels_by_slot = self._recognize_fleet_levels(screen, occupied_slots)
            ship_types = [types_by_slot.get(slot) for slot in range(6)]
            ship_levels = [levels_by_slot.get(slot) for slot in range(6)]
        else:
            ship_types = None
            ship_levels = None
        return FleetSnapshot(
            names=names,
            occupied=occupied,
            ship_types=ship_types,
            ship_levels=ship_levels,
        )

    def fill_missing_fleet_snapshot(
        self,
        snapshot: FleetSnapshot,
        *,
        expected_pool: Sequence[str] | None = None,
        detail_requirements: Mapping[str, tuple[bool, bool]] | None = None,
    ) -> FleetSnapshot:
        """获取新截图，只补充已有快照中仍为 ``None`` 的字段。

        ``detail_requirements`` 未提供时补充所有有船槽位的舰种和等级，用于
        LEVEL2/3。提供时按舰名身份映射 ``(需要舰种, 需要等级)``，用于
        LEVEL4 跳过即将被主选替换的备选舰船。
        """
        names = list(snapshot.names)
        ship_types = list(snapshot.ship_types or [None] * 6)
        ship_levels = list(snapshot.ship_levels or [None] * 6)

        def required_detail_slots() -> tuple[list[int], list[int]]:
            if detail_requirements is None:
                return snapshot.unknown_type_slots, snapshot.unknown_level_slots

            type_slots: list[int] = []
            level_slots: list[int] = []
            for slot, (name, occupied) in enumerate(
                zip(names, snapshot.occupied, strict=True),
            ):
                identity = ship_name_identity(name)
                requirements = detail_requirements.get(identity) if identity is not None else None
                if not occupied or requirements is None:
                    continue
                needs_type, needs_level = requirements
                if needs_type and ship_types[slot] is None:
                    type_slots.append(slot)
                if needs_level and ship_levels[slot] is None:
                    level_slots.append(slot)
            return type_slots, level_slots

        type_slots, level_slots = required_detail_slots()
        if not snapshot.unknown_slots and not type_slots and not level_slots:
            return snapshot

        screen = self._ctrl.screenshot()

        if snapshot.unknown_slots:
            names_by_slot = self._recognize_fleet_names_at_slots(
                screen,
                snapshot.unknown_slots,
                expected_pool=expected_pool,
            )
            for slot in snapshot.unknown_slots:
                if names_by_slot.get(slot) is not None:
                    names[slot] = names_by_slot[slot]

        # LEVEL4 的舰名可能刚在本次截图中识别成功，需要据此重新确定细节槽位。
        type_slots, level_slots = required_detail_slots()
        if type_slots:
            types_by_slot = self._recognize_fleet_ship_types(
                screen,
                type_slots,
            )
            for slot in type_slots:
                if types_by_slot.get(slot) is not None:
                    ship_types[slot] = types_by_slot[slot]

        if level_slots:
            levels_by_slot = self._recognize_fleet_levels(
                screen,
                level_slots,
            )
            for slot in level_slots:
                if levels_by_slot.get(slot) is not None:
                    ship_levels[slot] = levels_by_slot[slot]

        return FleetSnapshot(
            names=names,
            occupied=list(snapshot.occupied),
            ship_types=ship_types,
            ship_levels=ship_levels,
        )

    @staticmethod
    def _validate_fleet(
        current: list[str | None],
        desired: list[str | None],
    ) -> bool:
        """验证当前舰队是否已满足目标，目标空槽不参与比较。"""
        return all(desired[i] is None or current[i] == desired[i] for i in range(6))
