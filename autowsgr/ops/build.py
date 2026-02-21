"""建造操作。

导航到建造页面并委托 UI 层执行收取/建造。
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.ops.navigate import goto_page
from autowsgr.types import PageName


@dataclass(frozen=True, slots=True)
class BuildRecipe:
    """建造配方。"""

    fuel: int
    ammo: int
    steel: int
    bauxite: int


def collect_built_ships(
    ctrl: AndroidController,
    *,
    build_type: str = "ship",
    allow_fast_build: bool = False,
) -> int:
    """收取已建造完成的舰船或装备。"""
    from autowsgr.ui.build_page import BuildPage, BuildTab

    goto_page(ctrl, PageName.BUILD)
    page = BuildPage(ctrl)

    if build_type == "equipment":
        page.switch_tab(BuildTab.DEVELOP)
    else:
        screen = ctrl.screenshot()
        tab = BuildPage.get_active_tab(screen)
        if tab != BuildTab.BUILD:
            page.switch_tab(BuildTab.BUILD)

    return page.collect_all(build_type, allow_fast_build=allow_fast_build)


def build_ship(
    ctrl: AndroidController,
    *,
    recipe: BuildRecipe | None = None,
    build_type: str = "ship",
    allow_fast_build: bool = False,
) -> None:
    """建造舰船或装备。"""
    from autowsgr.ui.build_page import BuildPage

    collect_built_ships(ctrl, build_type=build_type, allow_fast_build=allow_fast_build)

    page = BuildPage(ctrl)
    if recipe is not None:
        logger.warning("[OPS] 资源滑块操作暂未实现, 使用默认配方")
    page.start_new_build(build_type)
