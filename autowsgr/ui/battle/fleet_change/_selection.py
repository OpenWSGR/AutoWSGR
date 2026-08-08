"""船池选择页面操作。

本模块只负责打开、取消和操作选船页面，不决定目标舰船、备选降级
或舰队调整顺序。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from autowsgr.combat.fleet import ShipSelector
from autowsgr.infra.logger import get_logger
from autowsgr.ui.battle.constants import CLICK_BACK
from autowsgr.vision.ocr_rules import get_user_ship_name_aliases

from ._planning import FleetPlanningMixin


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.ui.choose_ship_page import ChooseShipPage


_log = get_logger('ui.preparation')

# 等待选船页面出现的超时 (秒)
_CHOOSE_PAGE_TIMEOUT: float = 5.0


@dataclass(frozen=True, slots=True)
class _ShipSelection:
    """选船页实际命中的舰名和精确规则。"""

    name: str | None
    option: ShipSelector | None


class FleetSelectionMixin(FleetPlanningMixin):
    """提供船池页面的进入、退出、选择和移除操作。"""

    def _search_options(self, option: ShipSelector) -> tuple[ShipSelector, ...]:
        """按固定顺序生成自定义舰名和标准舰名搜索规则。"""
        if not self._use_search or option.search_name is not None:
            return (option,)

        aliases = get_user_ship_name_aliases(option.name)
        search_names = aliases if option.name in aliases else (*aliases, option.name)
        return tuple(replace(option, search_name=name) for name in search_names)

    def _open_choose_page(self, slot: int) -> ChooseShipPage:
        """打开指定物理槽位的选船页面。"""
        from autowsgr.ui.choose_ship_page import ChooseShipPage
        from autowsgr.ui.utils import wait_for_page

        self.click_ship_slot(slot)
        wait_for_page(
            self._ctrl,
            ChooseShipPage.is_current_page,
            timeout=_CHOOSE_PAGE_TIMEOUT,
            source='编队',
            target='编队选船',
        )
        return ChooseShipPage(self._ctx)

    def _cancel_choose_page(self) -> None:
        """规则未命中时退出选船页，恢复到编队准备页。"""
        from autowsgr.ui.utils import wait_for_page

        self._ctrl.click(*CLICK_BACK)
        wait_for_page(
            self._ctrl,
            self.is_current_page,
            timeout=_CHOOSE_PAGE_TIMEOUT,
            source='编队选船',
            target='编队',
        )

    def _try_select_option(
        self,
        slot: int,
        option: ShipSelector,
    ) -> _ShipSelection:
        """尝试一条精确规则；未命中返回 None，技术异常直接上抛。"""
        if self._ctx.ocr is None:
            raise RuntimeError('智能换船需要 OCR 引擎')

        for search_option in self._search_options(option):
            choose_page = self._open_choose_page(slot)
            selected = choose_page.change_single_ship(
                search_option,
                use_search=self._use_search,
            )
            if selected is not None:
                return _ShipSelection(name=selected, option=option)
            self._cancel_choose_page()
        return _ShipSelection(name=None, option=option)

    # 打开指定槽位的选船页面，完成单艘舰船的选择或移除。
    def _change_single_ship(
        self,
        slot: int,
        name: str | None,
        *,
        selector: Sequence[ShipSelector] | None = None,
        slot_occupied: bool = True,
    ) -> str | None:
        """返回选船页面实际选中的舰名。"""
        # 目标为空且当前槽位也为空时，不需要打开选船页面。
        if name is None and not slot_occupied:
            return None

        # FleetChange 决定候选顺序，页面每次只执行一条明确规则。
        choose_page = self._open_choose_page(slot)
        if name is None:
            return choose_page.change_single_ship(None, use_search=self._use_search)

        options = tuple(selector) if selector is not None else (ShipSelector(name=name),)
        for option in options:
            selected = choose_page.change_single_ship(
                option,
                use_search=self._use_search,
            )
            if selected is not None:
                return selected

        candidates = [option.name for option in options]
        self._cancel_choose_page()
        _log.error('[准备页] 未在选船列表中找到满足规则的候选: {}', candidates)
        raise RuntimeError(f'未找到满足条件的目标舰船: {candidates}')
