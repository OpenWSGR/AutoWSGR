"""决战原有换船流程。

保留不带目标舰名上下文的 OCR 路径，供新换船算法关闭时使用。
共享 OCR 模块中的全局置信度配置仍然生效。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.combat.fleet import FleetSlotRule
    from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage


_log = get_logger('ui.decisive.preparation')
_MAX_SET_RETRIES = 2


def change_fleet_legacy(
    page: DecisiveBattlePreparationPage,
    fleet_id: int | None,
    ship_names: Sequence[str | None],
) -> bool:
    """使用原有的完整对齐流程更换决战舰队。"""
    names = [
        name.strip() if isinstance(name, str) and name.strip() else None
        for name in list(ship_names)[:6]
    ]
    names += [None] * (6 - len(names))
    if fleet_id == 1 and names[0] is None:
        raise ValueError('1 队槽位 0 不能为空')

    if fleet_id and page.get_selected_fleet(page._ctrl.screenshot()) != fleet_id:
        page.select_fleet(fleet_id)
        time.sleep(0.5)

    selectors: list[FleetSlotRule | None] = [None] * 6
    _log.info('[决战] 使用原有换船流程，目标编成: {}', names)

    for attempt in range(_MAX_SET_RETRIES + 1):
        # 不传 expected_names，保持原有的全船池 OCR 匹配方式。
        current = page.detect_fleet()
        if page._validate_with_selector(current, names, selectors):
            return True

        ok, matched_slots = page._match_existing_members(current, names, selectors)
        for target_slot, name in enumerate(names):
            if name is None or target_slot in matched_slots:
                continue

            slot = next((index for index in range(6) if not ok[index]), None)
            if slot is None:
                _log.warning("[决战] 无可用槽位放置 '{}'", name)
                continue

            selected = page._change_single_ship(
                slot,
                name,
                selector=None,
                slot_occupied=current[slot] is not None,
            )
            current[slot] = selected if selected is not None else name
            ok[slot] = True
            matched_slots.add(target_slot)
            time.sleep(0.3)

        for slot in range(5, -1, -1):
            if not ok[slot] and current[slot] is not None:
                page._change_single_ship(slot, None, slot_occupied=True)
                current[slot] = None
                time.sleep(0.3)

        current = page.detect_fleet()
        page._reorder(current, names)
        current = page.detect_fleet()
        if page._validate_with_selector(current, names, selectors):
            _log.info('[决战] 原有换船流程完成: {}', current)
            return True

        if attempt < _MAX_SET_RETRIES:
            _log.warning(
                '[决战] 原有换船流程第 {}/{} 次验证失败，重试',
                attempt + 1,
                _MAX_SET_RETRIES + 1,
            )
            time.sleep(0.5)

    _log.error('[决战] 原有换船流程在重试后仍然失败')
    return False
