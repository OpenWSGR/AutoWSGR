"""解装舰船操作。

导航到建造页面（解体标签）并委托 UI 层执行。

``ship_types=None`` 表示不过滤舰种，全部解装；
传入舰种列表则只解装指定舰种。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import DestroyShipWorkMode, PageName, ShipType


if TYPE_CHECKING:
    from autowsgr.context import GameContext

_log = get_logger('ops')


def destroy_ships(
    ctx: GameContext,
    *,
    ship_types: list[ShipType] | None = None,
    remove_equipment: bool = True,
) -> None:
    """解装舰船。

    Parameters
    ----------
    ctx:
        游戏上下文。
    ship_types:
        要解装的舰种列表。``None`` (默认) 表示不过滤，直接快速全选解装全部。
    remove_equipment:
        是否在解装前卸下装备。默认 ``True``。
    """
    from autowsgr.ui.build_page import BuildPage, BuildTab

    _log.info('[OPS] 开始解装')
    goto_page(ctx, PageName.BUILD)

    page = BuildPage(ctx)
    page.switch_tab(BuildTab.DESTROY)
    page.destroy_ships(ship_types, remove_equipment=remove_equipment)

    goto_page(ctx, PageName.MAIN)
    _log.info('[OPS] 解装完成')


def destroy_ships_auto(ctx: GameContext) -> bool:
    """按 ``ctx.config`` 的解装设置自动解装。

    供 normal_fight / event_fight / decisive 船坞满时调用, 统一读取配置:

    - ``destroy_ship_work_mode == disable``: 不解装, 返回 ``False``
      (调用方据此停止战斗, 视为船坞满)。
    - ``include`` (黑名单): 解装 ``destroy_ship_types`` 指定舰种。
    - ``exclude`` (白名单): 解装除 ``destroy_ship_types`` 外的所有舰种。

    ``remove_equipment`` 取自 ``remove_equipment_mode``。

    Returns
    -------
    bool
        ``True`` 已执行解装; ``False`` 配置为「不启用」。
    """
    cfg = ctx.config
    mode = cfg.destroy_ship_work_mode

    if mode == DestroyShipWorkMode.disable:
        _log.info('[OPS] 解装模式为「不启用」, 跳过自动解装')
        return False

    if mode == DestroyShipWorkMode.include:
        ship_types = cfg.destroy_ship_types or None
    else:  # exclude (白名单): 解装除指定舰种外的所有
        protected = set(cfg.destroy_ship_types)
        ship_types = [t for t in ShipType if t is not ShipType.Other and t not in protected]
        if not ship_types:
            _log.warning('[OPS] 白名单包含全部舰种, 无可解装对象, 跳过')
            return False

    destroy_ships(
        ctx,
        ship_types=ship_types,
        remove_equipment=cfg.remove_equipment_mode,
    )
    return True
