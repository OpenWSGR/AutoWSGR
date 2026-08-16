"""解装舰船操作。

导航到建造页面（解体标签）并委托 UI 层执行。

``ship_types=None`` 表示不过滤舰种，全部解装；
传入舰种列表则只解装指定舰种。

船坞满弹窗的「解装」按钮可直达解体标签 (不绕主菜单导航),
见 :func:`destroy_ships_auto` 的 ``from_dialog`` 参数。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import DestroyShipWorkMode, PageName, ShipType
from autowsgr.ui.battle import BattlePreparationPage
from autowsgr.ui.build_page import CLICK_BACK as CLICK_BUILD_BACK
from autowsgr.ui.build_page import BuildPage, BuildTab
from autowsgr.ui.utils import NavigationError, click_and_wait_for_page


if TYPE_CHECKING:
    from autowsgr.context import GameContext

_log = get_logger('ops')

CLICK_DOCK_DIALOG_DESTROY: tuple[float, float] = (0.38, 0.565)
"""船坞满弹窗「解装」按钮 (底栏「解装|强化|扩充」三钮最左)。

弹窗模板 365x145 居中于 960x540 时, 左钮中心 ≈ (0.374, 0.567);
沿用 classic 实测坐标。点击后游戏直达建造页解体标签。"""


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
    _log.info('[OPS] 开始解装')
    goto_page(ctx, PageName.BUILD)

    page = BuildPage(ctx)
    page.switch_tab(BuildTab.DESTROY)
    page.destroy_ships(ship_types, remove_equipment=remove_equipment)

    goto_page(ctx, PageName.MAIN)
    _log.info('[OPS] 解装完成')


def destroy_ships_auto(ctx: GameContext, *, from_dialog: bool = False) -> bool:
    """按 ``ctx.config`` 的解装设置自动解装。

    供 normal_fight / event_fight / decisive 船坞满时调用, 统一读取配置。
    是否调用本函数由调用方的 ``dock_full_destroy`` / ``full_destroy`` 开关决定;
    此处只关心「怎么拆」::

    - ``destroy_ship_work_mode == disable``: 不启用舰种分类, 走快速拆解路线
      (``ship_types=None`` → 不打开过滤器, 快速全选解装全部)。
    - ``include`` (黑名单): 解装 ``destroy_ship_types`` 指定舰种。
    - ``exclude`` (白名单): 解装除 ``destroy_ship_types`` 外的所有舰种。

    ``remove_equipment`` 取自 ``remove_equipment_mode``。

    Parameters
    ----------
    from_dialog:
        ``True`` 时要求当前停在船坞满弹窗 (战斗准备页点出征后弹出):
        点弹窗「解装」按钮直达解体标签执行解装, 解装完成后停在战斗准备页
        — 不绕主菜单/侧边栏导航, 也不退出地图重选节点。
        ``False`` (默认) 走全局导航: 任意页面 → 建造页 (解体), 结束回主页面。

    Returns
    -------
    bool
        ``True`` 已执行解装; ``False`` 仅在白名单覆盖全部舰种、无可解装对象时返回
        (此时船坞仍满, 调用方据此保持 DOCK_FULL)。
    """
    cfg = ctx.config
    mode = cfg.destroy_ship_work_mode

    if mode == DestroyShipWorkMode.disable:
        # 不启用舰种分类: 不过滤, 直接走快速全选拆解路线
        ship_types = None
    elif mode == DestroyShipWorkMode.include:
        ship_types = cfg.destroy_ship_types or None
    else:  # exclude (白名单): 解装除指定舰种外的所有
        protected = set(cfg.destroy_ship_types)
        ship_types = [t for t in ShipType if t is not ShipType.Other and t not in protected]
        if not ship_types:
            _log.warning('[OPS] 白名单包含全部舰种, 无可解装对象, 跳过')
            return False

    if from_dialog:
        destroy_ships_from_dialog(
            ctx,
            ship_types,
            remove_equipment=cfg.remove_equipment_mode,
        )
    else:
        destroy_ships(
            ctx,
            ship_types=ship_types,
            remove_equipment=cfg.remove_equipment_mode,
        )
    return True


def destroy_ships_from_dialog(
    ctx: GameContext,
    ship_types: list[ShipType] | None,
    *,
    remove_equipment: bool,
) -> None:
    """船坞满弹窗直达解装: 弹窗「解装」→ 解体标签 → 解装 → 回战斗准备页。

    游戏行为 (实机 UI 流): 战斗准备页点出征弹出船坞满弹窗, 其「解装」
    按钮直达建造页解体标签; 解装完成后返回战斗准备页 (出征上下文仍在,
    可直接重新点出征, 无需重新导航进图选节点)。

    Raises
    ------
    NavigationError
        点弹窗按钮后未到达建造页, 或解装后未返回战斗准备页。
    """
    _log.info('[OPS] 船坞满弹窗 → 直达解装')
    click_and_wait_for_page(
        ctx.ctrl,
        click_coord=CLICK_DOCK_DIALOG_DESTROY,
        checker=BuildPage.is_current_page,
        source='船坞满弹窗',
        target=PageName.BUILD,
    )
    page = BuildPage(ctx)
    page.switch_tab(BuildTab.DESTROY)
    page.destroy_ships(ship_types, remove_equipment=remove_equipment)
    _wait_battle_prep_return(ctx)
    _log.info('[OPS] 解装完成, 已返回战斗准备页')


def _wait_battle_prep_return(ctx: GameContext) -> None:
    """等待返回战斗准备页: 先等游戏自动返回, 超时点建造页返回键兜底。

    解装完成后游戏通常自动弹回战斗准备页; 若停在解体标签, 点返回键
    沿进入链路 (弹窗直达) 回到战斗准备页。

    Raises
    ------
    NavigationError
        两轮等待后仍未到达战斗准备页。
    """

    def _poll(timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if BattlePreparationPage.is_current_page(ctx.ctrl.screenshot()):
                return True
            time.sleep(0.5)
        return False

    if _poll(6.0):
        return
    _log.info('[OPS] 解装后未自动返回战斗准备页, 点击建造页返回键')
    ctx.ctrl.click(*CLICK_BUILD_BACK)
    if _poll(5.0):
        return
    raise NavigationError('解装后未返回战斗准备页', screen=ctx.ctrl.screenshot())
