"""决战章节管理操作。

提供章节重置、入口状态准备、船坞满处理等辅助操作。
继承 :class:`~autowsgr.ops.decisive.base.DecisiveBase`。
"""

from __future__ import annotations

from autowsgr.infra import DockFullError
from autowsgr.infra.logger import get_logger
from autowsgr.ops.decisive.base import DecisiveBase
from autowsgr.types import PageName


_log = get_logger('ops.decisive')


class DecisiveChapterOps(DecisiveBase):
    """章节管理操作子类。

    提供章节生命周期管理:
    - :meth:`_prepare_entry_state` — 推断入口状态并导航到正确位置
    - :meth:`_do_dock_full_destroy` — 船坞满处理
    """

    def _prepare_entry_state(self) -> None:
        """进入决战总览并推断入口状态。"""
        from autowsgr.ops.navigate import goto_page

        goto_page(self._ctx, PageName.DECISIVE_BATTLE)
        self._battle_page.navigate_to_chapter(self._config.chapter)

    def _do_dock_full_destroy(self) -> None:
        """船坞满处理：按配置自动解装或抛错。"""
        if self._config.full_destroy:
            from autowsgr.ops.destroy import destroy_ships

            _log.warning('[决战] 船坞已满，执行自动解装')
            self._ctrl.click(0.38, 0.565)
            destroy_ships(
                self._ctx,
                ship_types=self._ctx.config.destroy_ship_types or None,
            )
            return
        raise DockFullError('决战中检测到船坞已满，且未开启 full_destroy')
