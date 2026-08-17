"""出征准备页换船 e2e 测试 — 主页 → 出征 → 编队 → 换船 → 主页。

调试 OCR 专用工具 (本周 OCR 调优主用)，需连接真实模拟器。

运行::

    pytest tools/ocr_change_fleet_e2e/test_change_fleet_e2e.py
    pytest tools/ocr_change_fleet_e2e/test_change_fleet_e2e.py \\
        --config configs/emulator_a.yaml --fleet 2 --ships "U-47,U-96"

每次运行可通过 ``--config`` 加载不同的 yaml 配置 (模拟器 / OCR / 舰船别名等)。

前置条件:
    - 本机 adb 可用
    - 至少一台模拟器在线
    - 目标舰船存在于玩家船坞

设备未就绪时由 ``game_ctx`` fixture 以 ``pytest.skip`` 跳过，不误报失败。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.ops import goto_page
from autowsgr.types import PageName
from autowsgr.ui.battle.preparation import BattlePreparationPage
from autowsgr.ui.main_page import MainPage
from autowsgr.ui.page import get_current_page

if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.context import GameContext


def _current_page(ctx: GameContext) -> str:
    """返回当前页面名，用于断言失败时的诊断信息。"""
    return get_current_page(ctx.ctrl.screenshot())


def test_main_prep_change_fleet_back_main(
    game_ctx: GameContext,
    fleet_id: int,
    ships: Sequence[str | None],
) -> None:
    """主页 → 出征 → 编队 → 换船 → 主页 的完整往返。"""
    ctx = game_ctx

    # 1. 主页 (launch 后应已就位)
    assert MainPage.is_current_page(ctx.ctrl.screenshot()), (
        f'启动后应位于主页面，实际: {_current_page(ctx)}'
    )

    # 2. 出征 → 编队 (出征准备页)
    goto_page(ctx, PageName.BATTLE_PREP)
    assert BattlePreparationPage.is_current_page(ctx.ctrl.screenshot()), (
        f'应位于出征准备页，实际: {_current_page(ctx)}'
    )

    # 3. 换船 (按槽位放入目标舰船)
    page = BattlePreparationPage(ctx)
    assert page.change_fleet(fleet_id, ships), '换船流程应成功'

    # 4. 返回主页
    goto_page(ctx, PageName.MAIN)
    assert MainPage.is_current_page(ctx.ctrl.screenshot()), (
        f'应返回主页面，实际: {_current_page(ctx)}'
    )
