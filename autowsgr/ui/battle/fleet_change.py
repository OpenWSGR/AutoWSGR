"""出征准备 — 舰队编成更换。

提供按舰船名称更换编队的组合动作。

TODO: 优化为使用快速编队逻辑
TODO: 对 choose_ship_page 建模
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.types import ShipDamageState

from .base import BaseBattlePreparation


if TYPE_CHECKING:
    from collections.abc import Sequence


_log = get_logger('ui.preparation')


class FleetChangeMixin(BaseBattlePreparation):
    """舰队编成更换 Mixin。

    依赖 :class:`~autowsgr.ui.battle.base.BaseBattlePreparation` 提供的
    ``_ctx``, ``_ctrl``, ``_ocr``, ``click_ship_slot``，以及
    :class:`~autowsgr.ui.battle.detection.DetectionMixin` 提供的
    ``detect_ship_damage``。
    """

    def change_fleet(
        self,
        fleet_id: int | None,
        ship_names: Sequence[str | None],
    ) -> bool:
        """更换编队全部舰船。

        TODO: 需测试

        Parameters
        ----------
        fleet_id:
            舰队编号 (2–4)。1 队不支持更换。
            ``None`` 代表不指定舰队，仅更换舰船。
        ship_names:
            舰船名列表 (按槽位 0–5)。``None`` 或 ``""`` 表示该位留空。

        Returns
        -------
        bool
            始终返回 ``True``（子类可覆盖以返回失败状态）。
        """
        if fleet_id == 1:
            raise ValueError('不支持更换 1 队舰船编成')

        if fleet_id and self.get_selected_fleet(self._ctrl.screenshot()) != fleet_id:
            self.select_fleet(fleet_id)
            time.sleep(0.5)

        _log.info('[UI] 更换 {} 队编成: {}', fleet_id, ship_names)

        names = list(ship_names) + [None] * 6
        names = [n or None for n in names[:6]]

        # 检测当前各槽位状态
        screen = self._ctrl.screenshot()
        damage = self.detect_ship_damage(screen)

        # 先移除所有已有舰船
        for slot in range(6):
            if damage.get(slot, ShipDamageState.NO_SHIP) != ShipDamageState.NO_SHIP:
                self._change_single_ship(0, None, slot_occupied=True)
                time.sleep(0.3)

        # 检测移除后状态
        screen = self._ctrl.screenshot()
        damage = self.detect_ship_damage(screen)

        # 逐个放入目标舰船
        for slot in range(6):
            name = names[slot]
            occupied = damage.get(slot, ShipDamageState.NO_SHIP) != ShipDamageState.NO_SHIP
            self._change_single_ship(slot, name, slot_occupied=occupied)
            time.sleep(0.3)

        _log.info('[UI] {} 队编成更换完成', fleet_id)
        return True

    def _change_single_ship(
        self,
        slot: int,
        name: str | None,
        *,
        slot_occupied: bool = True,
    ) -> None:
        """更换/移除指定位置的单艘舰船。"""
        from autowsgr.ui.choose_ship_page import ChooseShipPage

        if name is None and not slot_occupied:
            return

        self.click_ship_slot(slot)
        time.sleep(1.0)

        choose_page = ChooseShipPage(self._ctx)

        if name is None:
            choose_page.click_remove()
            time.sleep(0.8)
            return

        choose_page.click_search_box()
        time.sleep(0.5)
        choose_page.input_ship_name(name)
        time.sleep(0.3)
        choose_page.dismiss_keyboard()
        time.sleep(0.8)

        screen = self._ctrl.screenshot()
        if self._ocr is None:
            _log.warning('[UI] 未提供 OCR 引擎，无法验证舰船名称')
        else:
            ship_name = self._ocr.recognize_ship_name(screen, [name])
            if ship_name != name:
                _log.warning("[UI] 未精确匹配 '{}', OCR 识别: '{}'", name, ship_name)

        choose_page.click_first_result()
        time.sleep(1.0)
