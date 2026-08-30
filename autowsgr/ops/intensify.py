"""自动强化操作用例。

实现完整的自动强化全流程：
1. 从当前页面 (主页面或强化首页) 进入强化首页
2. 全量扫描素材库存与 43 行目标库存
3. 纯规划器计算最优强化批次列表
4. 连续执行强化批次，动态维护素材快照与目标属性，直至素材耗尽或达到上限
5. 安全返回主页面
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from autowsgr.infra.logger import get_logger
from autowsgr.ops.navigate import goto_page
from autowsgr.types import PageName
from autowsgr.ui.intensify_inventory_semantics import (
    ShipLibraryRarityResolver,
    material_inventory_observation,
)
from autowsgr.ui.intensify_planner import (
    IntensifyPlanBatch,
    IntensifyPlanningTarget,
    plan_ordered_intensify_batches,
)
from autowsgr.ui.intensify_snapshot_scan import scan_intensify_inventory_pair
from autowsgr.ui.intensify_workflow import (
    IntensifyPolicy,
    ShipStats,
    TargetObservation,
)
from autowsgr.ui.live_intensify import (
    is_intensify_confirmation,
    read_intensify_home_panel,
)
from autowsgr.ui.material_first_intensify import (
    MaterialFirstIntensifyController,
    is_intensify_home_screen,
    is_main_screen,
)
from autowsgr.ui.material_inventory_scanner import AdbLosslessMaterialDevice
from autowsgr.ui.target_strengthen_max import (
    ShipStrengthenDataResolver,
    TargetStrengthenMaxResolver,
)
from autowsgr.vision.ship_card_recognizer import load_default_ship_card_recognizer

if TYPE_CHECKING:
    from autowsgr.context import GameContext

_log = get_logger('ops.intensify')

_CLICK_INTENSIFY_BUTTON = (0.8715, 0.8220)
_CLICK_CONFIRM_DIALOG = (0.380, 0.568)
_CLICK_DISMISS_ANIMATION = (0.5, 0.5)
_CLICK_MATERIAL_CONFIRM = (0.915, 0.906)

_COL_CENTERS = (182, 393, 604, 815, 1026, 1237, 1448)
_ROW_CENTERS = (360, 792)


@dataclass(frozen=True, slots=True)
class IntensifyBatchExecutionReport:
    target_name: str
    target_index: int
    materials: list[str]
    gains: ShipStats
    stats_before: ShipStats
    stats_after: ShipStats


@dataclass(frozen=True, slots=True)
class AutoIntensifyExecutionResult:
    success: bool
    total_batches: int
    total_materials_used: int
    batches: list[IntensifyBatchExecutionReport]
    elapsed_seconds: float
    message: str


def auto_intensify(
    ctx: GameContext,
    *,
    policy: IntensifyPolicy | None = None,
    max_batches: int = 50,
    maximum_rarity: int = 6,
) -> AutoIntensifyExecutionResult:
    """执行完整的自动化强化全流程。"""
    t_start = time.monotonic()
    _log.info('[OPS] 开始自动强化')

    # 1. 准备环境依赖
    serial = getattr(ctx.config.emulator, 'serial', None)
    if not serial:
        raise RuntimeError('自动强化必须配置明确的 emulator.serial')

    device = AdbLosslessMaterialDevice(serial)
    device.verify_cetus()

    strengthen_data_path = Path(os.getenv('AUTOWSGR_STRENGTHEN_DATA', r'E:\wsgrgui\resource\strengthen.json'))
    ship_library_path = Path(os.getenv('AUTOWSGR_SHIP_LIBRARY', r'E:\wsgrgui\resource\ship-library'))

    identities = load_default_ship_card_recognizer()
    max_resolver = TargetStrengthenMaxResolver.from_source(strengthen_data_path)
    strengthen_data_resolver = ShipStrengthenDataResolver.from_source(strengthen_data_path)
    rarity_resolver = ShipLibraryRarityResolver.from_manifest(ship_library_path / 'manifest.json')

    # 2. 导航到强化首页
    nav_controller = MaterialFirstIntensifyController(device)
    nav_controller.ensure_intensify_home()

    # 3. 全量双库存扫描
    _log.info('[OPS] 执行双库存全量扫描...')
    targets_snapshot, materials_snapshot = scan_intensify_inventory_pair(
        device,
        identities,
        scroll_input=ctx.ctrl,
        ocr=ctx.ocr,
        max_resolver=max_resolver,
    )
    _log.info(
        '[OPS] 双库存扫描完成: 目标 {} 艘, 素材 {} 艘',
        targets_snapshot.total,
        materials_snapshot.total,
    )

    if materials_snapshot.total == 0:
        _log.info('[OPS] 素材库为空，自动强化完成')
        goto_page(ctx, PageName.MAIN)
        return AutoIntensifyExecutionResult(
            success=True,
            total_batches=0,
            total_materials_used=0,
            batches=[],
            elapsed_seconds=time.monotonic() - t_start,
            message='素材库为空，无可消耗素材',
        )

    # 4. 构建规划模型
    materials_obs = material_inventory_observation(
        materials_snapshot,
        strengthen_data_resolver,
        rarity_resolver,
    )

    planning_targets: list[IntensifyPlanningTarget] = []

    for idx, target in enumerate(targets_snapshot.targets):
        if target.ship_id == 0:
            continue
        max_stats = max_resolver(target.ship_id)
        if max_stats is None:
            continue
        req = ShipStats(
            firepower=max(0, max_stats.firepower - target.levels.firepower),
            torpedo=max(0, max_stats.torpedo - target.levels.torpedo),
            armor=max(0, max_stats.armor - target.levels.armor),
            anti_air=max(0, max_stats.anti_air - target.levels.anti_air),
        )
        if req == ShipStats(0, 0, 0, 0):
            continue
        target_obs = TargetObservation(
            ref=target.ref,
            identity=target.name,
            level=None,
            stats=target.levels,
        )
        planning_targets.append(
            IntensifyPlanningTarget(
                target=target_obs,
                index=idx,
                required_contribution=req,
            )
        )

    if policy is None:
        all_material_names = frozenset(item.identity for item in materials_obs.occurrences)
        policy = IntensifyPolicy(
            allowed_material_identities=all_material_names,
            maximum_materials=6,
        )

    # 5. 批次连续执行循环 (B6 + B7)
    executed_batches: list[IntensifyBatchExecutionReport] = []
    current_materials_obs = materials_obs

    while len(executed_batches) < max_batches and current_materials_obs.occurrences:
        plan_result = plan_ordered_intensify_batches(
            tuple(planning_targets),
            current_materials_obs,
            policy,
            maximum_rarity=maximum_rarity,
        )

        if not plan_result.batches:
            _log.info('[OPS] 剩余素材无法进一步匹配任何目标，规划循环结束')
            break

        batch = plan_result.batches[0]
        _log.info(
            '[OPS] 执行批次 {}/{}: 目标={}, 素材={}',
            len(executed_batches) + 1,
            max_batches,
            batch.target.identity,
            [m.identity for m in batch.materials],
        )

        # 5.1 选择目标
        from autowsgr.ui.intensify_snapshot_scan import IntensifySnapshotNavigator

        navigator = IntensifySnapshotNavigator(device)
        navigator.open_target_selector()
        time.sleep(0.5)

        for _ in range(8):
            device.shell('input swipe 500 200 500 900 250')
            time.sleep(0.2)
        time.sleep(0.5)

        target_row = batch.target_index // 7
        target_col = batch.target_index % 7
        if target_row >= 2:
            for _ in range(target_row - 1):
                device.shell('input swipe 500 650 500 218 400')
                time.sleep(0.5)
            click_target_row = 1
        else:
            click_target_row = target_row

        tx = _COL_CENTERS[target_col] / 1920
        ty = _ROW_CENTERS[click_target_row] / 1080
        device.click(tx, ty)
        time.sleep(1.2)

        if not is_intensify_home_screen(device.screenshot()):
            # 容错：如果该目标处于远征中不可选，则跳过该目标
            _log.warning('[OPS] 目标 {} 无法选中 (可能在远征中)，跳过该目标', batch.target.identity)
            planning_targets = [t for t in planning_targets if t.index != batch.target_index]
            navigator.close_target_selector()
            continue

        # 5.2 选择素材
        navigator.open_material_selector()
        time.sleep(0.5)
        for _ in range(8):
            device.shell('input swipe 500 200 500 900 250')
            time.sleep(0.2)
        time.sleep(0.5)

        for mat in batch.materials:
            mat_row = mat.index // 7
            mat_col = mat.index % 7
            if mat_row >= 2:
                for _ in range(mat_row - 1):
                    device.shell('input swipe 500 650 500 218 400')
                    time.sleep(0.5)
                click_mat_row = 1
            else:
                click_mat_row = mat_row
            mx = _COL_CENTERS[mat_col] / 1920
            my = _ROW_CENTERS[click_mat_row] / 1080
            device.click(mx, my)
            time.sleep(0.3)

        device.click(*_CLICK_MATERIAL_CONFIRM)
        time.sleep(1.2)

        s_home = device.screenshot()
        if not is_intensify_home_screen(s_home):
            raise RuntimeError('素材确认后未正常返回强化首页')

        # 5.3 校验收益并执行强化
        obs_before = read_intensify_home_panel(s_home, ctx.ocr)
        if not obs_before.can_intensify:
            raise RuntimeError('强化首页未亮起强化按钮，无法执行强化')

        device.click(*_CLICK_INTENSIFY_BUTTON)
        time.sleep(1.5)

        s_dialog = device.screenshot()
        if is_intensify_confirmation(s_dialog):
            device.click(*_CLICK_CONFIRM_DIALOG)
            time.sleep(1.5)

        time.sleep(3.0)
        device.click(*_CLICK_DISMISS_ANIMATION)
        time.sleep(1.5)

        s_final = device.screenshot()
        if not is_intensify_home_screen(s_final):
            device.click(*_CLICK_DISMISS_ANIMATION)
            time.sleep(1.0)
            s_final = device.screenshot()

        obs_after = read_intensify_home_panel(s_final, ctx.ocr)

        executed_batches.append(
            IntensifyBatchExecutionReport(
                target_name=batch.target.identity,
                target_index=batch.target_index,
                materials=[m.identity for m in batch.materials],
                gains=batch.contribution,
                stats_before=obs_before.current,
                stats_after=obs_after.current,
            )
        )

        # 5.4 动态快照前移维护 (B7)
        current_materials_obs = type(current_materials_obs)(
            occurrences=plan_result.remaining_materials,
            complete=True,
            revision=current_materials_obs.revision,
        )

        new_stats = obs_after.current
        max_stats = max_resolver(targets_snapshot.targets[batch.target_index].ship_id)
        if max_stats:
            req = ShipStats(
                firepower=max(0, max_stats.firepower - new_stats.firepower),
                torpedo=max(0, max_stats.torpedo - new_stats.torpedo),
                armor=max(0, max_stats.armor - new_stats.armor),
                anti_air=max(0, max_stats.anti_air - new_stats.anti_air),
            )
            planning_targets = [
                IntensifyPlanningTarget(
                    target=TargetObservation(
                        ref=t.target.ref,
                        identity=t.target.identity,
                        level=t.target.level,
                        stats=new_stats if t.index == batch.target_index else t.target.stats,
                    ),
                    index=t.index,
                    required_contribution=req if t.index == batch.target_index else t.required_contribution,
                )
                for t in planning_targets
                if (req != ShipStats(0, 0, 0, 0) if t.index == batch.target_index else True)
            ]

    # 6. 安全返回主页面
    _log.info('[OPS] 自动强化完成，返回主页面')
    goto_page(ctx, PageName.MAIN)

    total_mats = sum(len(b.materials) for b in executed_batches)
    elapsed = time.monotonic() - t_start
    _log.info(
        '[OPS] 自动强化全部完成: 成功执行 {} 个批次, 消耗 {} 艘素材, 总耗时 {:.1f}s',
        len(executed_batches),
        total_mats,
        elapsed,
    )

    return AutoIntensifyExecutionResult(
        success=True,
        total_batches=len(executed_batches),
        total_materials_used=total_mats,
        batches=executed_batches,
        elapsed_seconds=elapsed,
        message=f'自动强化完成: 执行 {len(executed_batches)} 个批次，消耗 {total_mats} 艘素材',
    )
