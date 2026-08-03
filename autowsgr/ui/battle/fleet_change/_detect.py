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

from typing import TYPE_CHECKING

from autowsgr.constants import SHIPNAMES
from autowsgr.infra.logger import get_logger
from autowsgr.ui.battle.base import BaseBattlePreparation
from autowsgr.vision.ocr import (
    _fuzzy_match,
    apply_ship_patches,
)
from autowsgr.vision.ocr_rules import normalize_ship_name_suffix


# 仅在类型检查时导入运行逻辑不需要的类型。
if TYPE_CHECKING:
    from collections.abc import Sequence

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
            self._ocr.recognize(strip),
            key=lambda result: (
                (result.bbox[0] + result.bbox[2]) / 2 if result.bbox is not None else float('inf')
            ),
        )
        expected_slots = (
            [
                normalize_ship_name_suffix(name) if isinstance(name, str) and name.strip() else None
                for name in list(expected_names)[:6]
            ]
            if expected_names is not None
            else []
        )
        expected_slots += [None] * (6 - len(expected_slots))
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
            if expected_name is not None and matched != expected_name:
                context_match = self._match_context_ship_name(text, [expected_name])
                if context_match is not None:
                    matched = context_match
            # 完整船池和目标上下文都无法识别时跳过该文字。
            if matched is None:
                _log.debug("[准备页] OCR '{}' -> 无匹配, 跳过", raw_text)
                continue
            ships[slot] = matched
            _log.debug("[准备页] 槽位 {} OCR -> '{}'", slot, matched)

        _log.info('[准备页] 当前舰队: {}', ships)
        return ships

    @staticmethod
    def _validate_fleet(
        current: list[str | None],
        desired: list[str | None],
    ) -> bool:
        """验证当前舰队是否已满足目标，目标空槽不参与比较。"""
        return all(desired[i] is None or current[i] == desired[i] for i in range(6))
