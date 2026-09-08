"""决战 E2E — 复用当前配置执行指定轮数的完整决战流程。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    import argparse

DESC = '决战: 使用 usersettings.yaml 配置执行完整决战流程 (需 --with-ocr)'


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """定义决战 case 参数。"""
    parser.add_argument(
        '--times',
        type=int,
        default=None,
        help='覆盖配置中的决战轮数 (默认使用 decisive_battle.decisive_rounds)',
    )
    parser.add_argument(
        '--scenario',
        choices=('full', 'recovery-chain'),
        default='full',
        help='选择完整决战或四段恢复链路场景',
    )


def _run_recovery_chain(  # noqa: C901, PLR0911, PLR0912, PLR0915
    rt: Any,
    config: Any,
) -> bool:
    """Run the four-stage real-device recovery chain without starting combat."""
    from autowsgr.ops import DecisiveController
    from autowsgr.types import DecisivePhase
    from autowsgr.ui.battle.preparation import BattlePreparationPage
    from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage

    controller = DecisiveController(rt.ctx, config)
    controller._resume_mode = True
    controller._has_chosen_fleet = False

    def wait_for_phase(
        label: str,
        expected: set[DecisivePhase],
    ) -> DecisivePhase | None:
        def wait_until_phase() -> DecisivePhase:
            while controller.state.phase is DecisivePhase.WAITING_FOR_MAP:
                controller._handle_waiting_for_map()
            return controller.state.phase

        phase = rt.action(label, wait_until_phase)
        if phase is rt.FAILED:
            return None
        rt.note(f'{label}: {phase.name}')
        if not rt.check(
            f'{label}状态正确',
            lambda: controller.state.phase in expected,
        ):
            return None
        return phase

    def wait_for_advance_choice(label: str) -> bool:
        phase = wait_for_phase(
            label,
            {DecisivePhase.USE_LAST_FLEET, DecisivePhase.ADVANCE_CHOICE},
        )
        if phase is None:
            return False
        if phase is DecisivePhase.USE_LAST_FLEET:
            if (
                rt.action(
                    f'{label}: 识别后选择上次舰队',
                    controller._handle_use_last_fleet,
                )
                is rt.FAILED
            ):
                return False
            phase = wait_for_phase(
                f'{label}: 确认后等待前进点选择',
                {DecisivePhase.ADVANCE_CHOICE},
            )
        return phase is DecisivePhase.ADVANCE_CHOICE

    def enter_map(label: str) -> bool:
        controller._state.phase = DecisivePhase.ENTER_MAP
        return rt.action(label, controller._handle_enter_map) is not rt.FAILED

    def reset_after_retreat() -> None:
        controller._state.reset()
        controller._state.phase = DecisivePhase.ENTER_MAP

    if rt.action('定位决战总览页', controller._prepare_entry_state) is rt.FAILED:
        return False
    reset_ok = rt.action('Case 1: 重置第六章状态', controller._battle_page.reset_chapter)
    if reset_ok is rt.FAILED or not rt.check('Case 1: 第六章重置成功', lambda: bool(reset_ok)):
        return False

    # Case 1: first entry -> advance choice -> normal fleet acquisition -> retreat.
    if not enter_map('Case 1: 进入第一小关'):
        return False
    if not wait_for_advance_choice('Case 1: 等待前进点选择'):
        return False
    if rt.action('Case 1: 识别后选择前进点', controller._handle_advance_choice) is rt.FAILED:
        return False
    if not wait_for_phase(
        'Case 1: 等待后续状态',
        {DecisivePhase.CHOOSE_FLEET, DecisivePhase.PREPARE_COMBAT},
    ):
        return False
    if (
        controller.state.phase is DecisivePhase.CHOOSE_FLEET
        and rt.action('Case 1: 正常选择舰队', controller._handle_choose_fleet) is rt.FAILED
    ):
        return False
    if not rt.check(
        'Case 1: 选船后处于准备链路',
        lambda: controller.state.phase is DecisivePhase.PREPARE_COMBAT,
    ):
        return False
    if rt.action('Case 1: 不进入战斗直接撤退', controller._execute_retreat) is rt.FAILED:
        return False
    reset_after_retreat()

    # Case 2: retreat re-entry -> advance choice -> mocked insufficient fleet -> retreat.
    if not enter_map('Case 2: 撤退后重新进入'):
        return False
    if not wait_for_advance_choice('Case 2: 等待前进点选择'):
        return False
    if rt.action('Case 2: 识别后选择前进点', controller._handle_advance_choice) is rt.FAILED:
        return False

    original_best_fleet = controller._logic.get_best_fleet
    original_recognize_node = controller._map.recognize_node
    original_is_skill_used = controller._map.is_skill_used

    def mock_choose_one_fleet() -> None:
        """Click the first real card, then leave only one ship for retreat logic."""
        controller._map.buy_fleet_option((0.25, 0.5))
        controller._state.ships.add(config.level1[0])
        controller._has_chosen_fleet = True
        controller._state.phase = DecisivePhase.PREPARE_COMBAT
        if not controller._map.close_fleet_overlay():
            raise RuntimeError('mock 购买第一艘舰船后无法关闭战备选择页')

    controller._logic.get_best_fleet = lambda: ['', config.level1[0], '', '', '', '', '']
    controller._map.recognize_node = lambda: 'A'
    controller._map.is_skill_used = lambda: True
    try:
        if not wait_for_phase(
            'Case 2: 等待无船状态',
            {DecisivePhase.CHOOSE_FLEET, DecisivePhase.PREPARE_COMBAT},
        ):
            return False
        if (
            controller.state.phase is DecisivePhase.CHOOSE_FLEET
            and rt.action('Case 2: mock 跳过识别并选择第一艘', mock_choose_one_fleet) is rt.FAILED
        ):
            return False
        if not rt.check(
            'Case 2: mock 已实际选择一艘舰船',
            lambda: config.level1[0] in controller.state.ships,
        ):
            return False
        if rt.action('Case 2: mock 舰船不足判断', controller._handle_prepare_combat) is rt.FAILED:
            return False
        if not rt.check(
            'Case 2: 舰船不足触发撤退',
            lambda: controller.state.phase is DecisivePhase.RETREAT,
        ):
            return False
    finally:
        controller._logic.get_best_fleet = original_best_fleet
        controller._map.recognize_node = original_recognize_node
        controller._map.is_skill_used = original_is_skill_used

    if rt.action('Case 2: 执行撤退', controller._execute_retreat) is rt.FAILED:
        return False
    reset_after_retreat()

    # Case 3: second retreat re-entry -> advance choice -> normal formation -> leave.
    if not enter_map('Case 3: 再次重新进入'):
        return False
    if not wait_for_advance_choice('Case 3: 等待前进点选择'):
        return False
    if rt.action('Case 3: 识别后选择前进点', controller._handle_advance_choice) is rt.FAILED:
        return False
    if not wait_for_phase(
        'Case 3: 等待准备状态',
        {DecisivePhase.CHOOSE_FLEET, DecisivePhase.PREPARE_COMBAT},
    ):
        return False
    if (
        controller.state.phase is DecisivePhase.CHOOSE_FLEET
        and rt.action('Case 3: 正常选择舰队', controller._handle_choose_fleet) is rt.FAILED
    ):
        return False
    if rt.action('Case 3: 进入编队页', controller._map.enter_formation) is rt.FAILED:
        return False
    prep_page = DecisiveBattlePreparationPage(rt.ctx, config, rt.ctx.ocr)
    formation_ships = sorted(controller.state.ships)[:6]
    if not formation_ships:
        rt.note('Case 3: 本轮未记录到已购买舰船')
        return False
    if (
        rt.action(
            'Case 3: 正常完成编队',
            prep_page.change_fleet,
            None,
            formation_ships,
        )
        is rt.FAILED
    ):
        return False
    if rt.action('Case 3: 编队完成回到地图', prep_page.go_back) is rt.FAILED:
        return False
    if rt.action('Case 3: 暂离', controller._execute_leave) is rt.FAILED:
        return False

    # Case 4: leave resume -> no advance choice -> preparation page only.
    if rt.action('Case 4: 定位已选节点', controller._prepare_entry_state) is rt.FAILED:
        return False
    if not enter_map('Case 4: 恢复进入地图'):
        return False
    if not wait_for_phase(
        'Case 4: 识别恢复后的页面',
        {DecisivePhase.PREPARE_COMBAT},
    ):
        return False
    if rt.action('Case 4: 进入编队页', controller._map.enter_formation) is rt.FAILED:
        return False
    final_screen = rt.ctx.ctrl.screenshot()
    rt.check(
        'Case 4: 停在可出征准备页',
        lambda: bool(BattlePreparationPage.is_current_page(final_screen)),
    )
    rt.note('Case 4: 未调用 start_battle，验证结束')
    return rt.state.failed == 0


def run(rt: Any) -> bool:
    """执行决战并验证每轮都有明确结果。"""
    from autowsgr.ops import DecisiveController
    from autowsgr.ops.decisive.controller import DecisiveResult

    config = rt.ctx.config.decisive_battle
    if config is None:
        rt.note('usersettings.yaml 未配置 decisive_battle')
        return False
    if rt.ctx.ocr is None:
        rt.note('决战需要 OCR，请使用 --with-ocr')
        return False

    times = rt.args.times if rt.args.times is not None else config.decisive_rounds
    if times < 1:
        rt.note('times 必须大于 0')
        return False

    if rt.args.scenario == 'recovery-chain':
        return _run_recovery_chain(rt, config)

    rt.note(f'章节: {config.chapter}  轮数: {times}')
    rt.note(f'一级舰队: {config.level1}')
    rt.note(f'二级舰队: {config.level2}')

    controller = DecisiveController(rt.ctx, config)
    results = rt.action(
        f'执行决战第 {config.chapter} 章 x{times}',
        controller.run_for_times,
        times,
    )
    if results is rt.FAILED:
        return False

    rt.note(f'决战结果: {[result.value for result in results]}')
    rt.check('结果轮数一致', lambda: len(results) == times)
    rt.check(
        '没有 ERROR 结果',
        lambda: all(result is not DecisiveResult.ERROR for result in results),
    )
    return rt.state.failed == 0
