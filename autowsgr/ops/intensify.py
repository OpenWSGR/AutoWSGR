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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

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
    _remaining_need,
    _sum_stats,
    plan_ordered_intensify_batches,
)
from autowsgr.ui.intensify_snapshot_scan import scan_intensify_inventory_pair
from autowsgr.ui.intensify_workflow import (
    IntensifyPolicy,
    MaterialInventoryObservation,
    MaterialOccurrence,
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
_CLICK_TARGET_CLOSE = (0.048, 0.088)
_CLICK_SELECTOR_BACK = (0.048, 0.088)

_COL_CENTERS = (182, 393, 604, 815, 1026, 1237, 1448)
_ROW_CENTERS = (360, 792)


class _UnsetPolicyOption:
    pass


_UNSET_POLICY_OPTION = _UnsetPolicyOption()
_session_target_inventory_baseline: TargetInventorySnapshot | None = None


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


def _remove_consumed_materials(
    inventory: MaterialInventoryObservation,
    batch: IntensifyPlanBatch,
) -> MaterialInventoryObservation:
    consumed_refs = {item.ref for item in batch.materials}
    inventory_refs = {item.ref for item in inventory.occurrences}
    if not consumed_refs or not consumed_refs <= inventory_refs:
        raise RuntimeError('已执行强化批次与当前素材库存 revision 不一致')
    remaining = tuple(
        replace(item, index=index)
        for index, item in enumerate(
            item for item in inventory.occurrences if item.ref not in consumed_refs
        )
    )
    return type(inventory)(
        occurrences=remaining,
        complete=inventory.complete,
        revision=inventory.revision,
    )


def _material_click_steps(
    materials: tuple[MaterialOccurrence, ...],
) -> tuple[tuple[int, int, int], ...]:
    """Return incremental scrolls plus visible row/column for ascending indices."""
    sorted_materials = tuple(sorted(materials, key=lambda item: item.index))
    indices = [item.index for item in sorted_materials]
    if len(indices) != len(set(indices)):
        raise RuntimeError('强化素材 occurrence 必须按唯一索引选择')
    top_row = 0
    steps: list[tuple[int, int, int]] = []
    for index in indices:
        absolute_row, column = divmod(index, 7)
        desired_top_row = max(0, absolute_row - 1)
        scroll_count = desired_top_row - top_row
        if scroll_count < 0:
            raise RuntimeError('强化素材选择不能反向滚动')
        top_row = desired_top_row
        steps.append((scroll_count, absolute_row - top_row, column))
    return tuple(steps)


def auto_intensify(  # noqa: C901, PLR0912, PLR0915
    ctx: GameContext,
    *,
    policy: IntensifyPolicy | None = None,
    material_ship_types: frozenset[str] | None | _UnsetPolicyOption = _UNSET_POLICY_OPTION,
    maximum_materials: int | None | _UnsetPolicyOption = _UNSET_POLICY_OPTION,
    protected_material_identities: frozenset[str] | _UnsetPolicyOption = _UNSET_POLICY_OPTION,
    reuse_target_inventory_baseline: bool = False,
    max_batches: int = 50,
    maximum_rarity: int = 6,
) -> AutoIntensifyExecutionResult:
    """执行完整的自动化强化全流程。"""
    global _session_target_inventory_baseline
    t_start = time.monotonic()
    _log.info('[OPS] 开始自动强化')

    # 1. 准备环境依赖
    serial = getattr(ctx.config.emulator, 'serial', None)
    if (not isinstance(serial, str) or not serial.strip()) and ctx.ctrl is not None:
        serial = getattr(ctx.ctrl, 'serial', None)
    if not isinstance(serial, str) or not serial.strip():
        raise RuntimeError('自动强化必须连接有效的模拟器设备')

    device = AdbLosslessMaterialDevice(serial)
    device.verify_cetus()

    strengthen_data_path = Path(os.getenv('AUTOWSGR_STRENGTHEN_DATA', r'E:\wsgrgui\resource\strengthen.json'))
    ship_library_path = Path(os.getenv('AUTOWSGR_SHIP_LIBRARY', r'E:\wsgrgui\resource\ship-library'))

    identities = load_default_ship_card_recognizer()
    max_resolver = TargetStrengthenMaxResolver.from_source(strengthen_data_path)
    strengthen_data_resolver = ShipStrengthenDataResolver.from_source(strengthen_data_path)
    rarity_resolver = ShipLibraryRarityResolver.from_manifest(ship_library_path / 'manifest.json')

    saved_policy = ctx.config.intensify
    if isinstance(material_ship_types, _UnsetPolicyOption):
        material_ship_types = (
            None
            if saved_policy.material_ship_types is None
            else frozenset(saved_policy.material_ship_types)
        )
    if isinstance(maximum_materials, _UnsetPolicyOption):
        maximum_materials = saved_policy.max_materials
    if isinstance(protected_material_identities, _UnsetPolicyOption):
        protected_material_identities = frozenset(saved_policy.protected_ships)
    if not reuse_target_inventory_baseline and getattr(saved_policy, 'reuse_target_inventory_baseline', False):
        reuse_target_inventory_baseline = True

    # 2. 导航到强化首页
    nav_controller = MaterialFirstIntensifyController(device)
    nav_controller.ensure_intensify_home(ctx=ctx)

    # 3. 扫描库存（支持复用目标库基线）
    if (
        reuse_target_inventory_baseline
        and _session_target_inventory_baseline is not None
        and _session_target_inventory_baseline.targets
    ):
        targets_snapshot = _session_target_inventory_baseline
        _log.info('[OPS] 复用目标库扫描基线 (共 {} 艘目标)，执行素材库单扫描...', targets_snapshot.total)
        from autowsgr.ui.intensify_snapshot_scan import (
            IntensifySnapshotNavigator,
            _scan_and_close_selector,
        )
        from autowsgr.ui.material_inventory_scanner import scan_material_inventory_from_selector

        nav = IntensifySnapshotNavigator(device)
        nav.open_material_selector()
        materials_snapshot = _scan_and_close_selector(
            lambda: scan_material_inventory_from_selector(device, identities),
            nav.close_material_selector,
            label='素材库存',
        )
        _log.info('[OPS] 素材库单扫描完成: 目标 {} 艘(复用), 素材 {} 艘', targets_snapshot.total, materials_snapshot.total)
    else:
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
        if reuse_target_inventory_baseline:
            _session_target_inventory_baseline = targets_snapshot

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

    exp_resolver = getattr(strengthen_data_resolver, 'experience_per_level', lambda _sid: 1)

    for idx, target in enumerate(targets_snapshot.targets):
        if target.ship_id == 0:
            continue
        if getattr(target, 'masked', False):
            _log.info('[OPS] 目标 {} 处于远征/出征/修理中（遮罩生效），跳过强化规划', target.name)
            continue
        max_stats = max_resolver(target.ship_id)
        if max_stats is None:
            continue
        exp_per_level = exp_resolver(target.ship_id) or 1
        req = ShipStats(
            firepower=max(0, max_stats.firepower - target.levels.firepower) * exp_per_level,
            torpedo=max(0, max_stats.torpedo - target.levels.torpedo) * exp_per_level,
            armor=max(0, max_stats.armor - target.levels.armor) * exp_per_level,
            anti_air=max(0, max_stats.anti_air - target.levels.anti_air) * exp_per_level,
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
        assert isinstance(protected_material_identities, frozenset)
        allowed_material_names = frozenset(
            item.identity
            for item, ship_id in zip(
                materials_obs.occurrences,
                materials_snapshot.ship_ids,
                strict=True,
            )
            if item.identity not in protected_material_identities
            and (
                material_ship_types is None
                or rarity_resolver.ship_type(ship_id) in material_ship_types
            )
        )
        if not allowed_material_names:
            _log.info('[OPS] 保护名单排除全部素材，自动强化完成')
            goto_page(ctx, PageName.MAIN)
            return AutoIntensifyExecutionResult(
                success=True,
                total_batches=0,
                total_materials_used=0,
                batches=[],
                elapsed_seconds=time.monotonic() - t_start,
                message='没有符合策略的可消耗素材',
            )
        policy = IntensifyPolicy(
            allowed_material_identities=allowed_material_names,
            maximum_materials=maximum_materials,
        )

    # 5. 批次连续执行循环 (B6 + B7)
    executed_batches: list[IntensifyBatchExecutionReport] = []
    current_materials_obs = materials_obs
    current_selected_target_index: int | None = None
    from autowsgr.ui.intensify_snapshot_scan import IntensifySnapshotNavigator

    navigator = IntensifySnapshotNavigator(device)

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

        # 5.1 选择目标（理论位置定位大致视口 + 列约束定向识别）
        if current_selected_target_index != batch.target_index:
            navigator.open_target_selector()
            time.sleep(0.5)

            target_row = batch.target_index // 7
            target_col = batch.target_index % 7
            target_col_x = _COL_CENTERS[target_col]

            # 1. 理论位置定位大致视口
            if target_row >= 2:
                scroll_count = (target_row - 1) // 2
                for _ in range(scroll_count):
                    device.shell('input swipe 500 650 500 218 1000')
                    time.sleep(0.6)

            screen = device.screenshot()
            from autowsgr.ui.target_inventory_scanner import detect_complete_target_cards

            cards = detect_complete_target_cards(screen)
            # 2. 列约束定向识别：优先在 target_col 所在的列寻找匹配卡片
            matching_card = None
            col_cards = [c for c in cards if abs(c.center[0] - target_col_x) < 50]
            if col_cards:
                col_images = [screen[c.top : c.bottom, c.left : c.right] for c in col_cards]
                col_idents = identities.recognize(col_images)
                for c, ident in zip(col_cards, col_idents, strict=True):
                    if ident and ident.name == batch.target.identity and not ident.masked:
                        matching_card = c
                        break

            # 容错兜底：若特定列因极端滑动误差未命中，在当前视口全部可见卡片中搜索
            if matching_card is None and cards:
                all_images = [screen[c.top : c.bottom, c.left : c.right] for c in cards]
                all_idents = identities.recognize(all_images)
                for c, ident in zip(cards, all_idents, strict=True):
                    if ident and ident.name == batch.target.identity and not ident.masked:
                        matching_card = c
                        break

            if matching_card is not None:
                cx, cy = matching_card.center
                device.click(cx / screen.shape[1], cy / screen.shape[0])
                time.sleep(1.2)
            else:
                # 理论位置直接点击兜底
                click_target_row = 1 if target_row >= 2 else target_row
                tx = _COL_CENTERS[target_col] / 1920
                ty = _ROW_CENTERS[click_target_row] / 1080
                device.click(tx, ty)
                time.sleep(1.2)

            if not is_intensify_home_screen(device.screenshot()):
                # 容错：如果该目标处于远征中不可选，则跳过该目标
                _log.warning('[OPS] 目标 {} 无法选中 (可能在远征中)，跳过该目标', batch.target.identity)
                planning_targets = [t for t in planning_targets if t.index != batch.target_index]
                navigator.close_target_selector()
                current_selected_target_index = None
                continue
            current_selected_target_index = batch.target_index

        # 5.2 选择素材（理论位置定位大致视口 + 列约束定向识别）
        navigator.open_material_selector()
        time.sleep(0.5)

        from autowsgr.ui.material_inventory_scanner import (
            MaterialViewportReader,
            _COLUMN_LEFTS_1920,
            _CARD_WIDTH_1920,
            _CARD_HEIGHT_1080,
        )

        reader = MaterialViewportReader(identities)
        needed_mats = list(batch.materials)
        selected_this_batch: list[MaterialOccurrence] = []
        current_viewport_row = 0

        for m in needed_mats:
            target_row = m.index // 7
            target_col = m.index % 7

            # 1. 理论位置定位大致视口
            if target_row > current_viewport_row + 1:
                scroll_count = (target_row - current_viewport_row) // 2
                for _ in range(scroll_count):
                    device.shell('input swipe 500 650 500 218 1000')
                    time.sleep(0.6)
                current_viewport_row += scroll_count * 2

            screen = device.screenshot()
            bands = reader.locate_name_bands(screen)
            left = _COLUMN_LEFTS_1920[target_col]
            right = left + _CARD_WIDTH_1920
            card_height = round(_CARD_HEIGHT_1080 * screen.shape[0] / 1080)

            # 2. 列约束定向识别（只检索对应列 target_col 上的卡片）
            clicked = False
            for _row_idx, (_top, bottom) in enumerate(bands):
                card_top = max(0, bottom - card_height)
                crop = screen[card_top:bottom, left:right]
                results = identities.recognize([crop])
                ident = results[0] if results else None
                if ident and ident.name == m.identity:
                    center_x = (left + _CARD_WIDTH_1920 / 2) / screen.shape[1]
                    center_y = (bottom - card_height / 2) / screen.shape[0]
                    device.click(center_x, center_y)
                    time.sleep(0.3)
                    selected_this_batch.append(m)
                    clicked = True
                    break

            # 容错兜底：若该列由于历史行偏移未直接命中，在当前视口局部搜索匹配
            if not clicked:
                try:
                    cap = reader.capture(screen)
                    vps = reader.recognize_captures([cap])
                    if vps and vps[0].positions:
                        vp = vps[0]
                        for pos, name, _sid in zip(vp.positions, vp.names, vp.ship_ids):
                            if name == m.identity and m not in selected_this_batch:
                                _r, _c, x, y = pos
                                device.click(x, y)
                                time.sleep(0.3)
                                selected_this_batch.append(m)
                                clicked = True
                                break
                except Exception:
                    pass

        device.click(*_CLICK_MATERIAL_CONFIRM)
        time.sleep(1.2)

        s_home = device.screenshot()
        if not is_intensify_home_screen(s_home):
            raise RuntimeError('素材确认后未正常返回强化首页')

        # 5.3 校验收益并执行强化
        obs_before = read_intensify_home_panel(s_home, ctx.ocr)
        if not obs_before.can_intensify:
            _log.warning(
                '[OPS] 目标 {} 强化按钮未亮起 (current={}, gains={})，跳过该目标',
                batch.target.identity,
                obs_before.current,
                obs_before.gains,
            )
            planning_targets = [t for t in planning_targets if t.index != batch.target_index]
            current_selected_target_index = None
            # 点击素材槽进入素材选择页清除已选素材
            navigator.open_material_selector()
            time.sleep(0.5)
            device.click(*_CLICK_TARGET_CLOSE)
            time.sleep(1.0)
            continue

        device.click(*_CLICK_INTENSIFY_BUTTON)
        time.sleep(1.5)

        s_dialog = device.screenshot()
        if is_intensify_confirmation(s_dialog):
            device.click(*_CLICK_CONFIRM_DIALOG)
            time.sleep(1.5)

        # 强化动画等待与完全消散
        time.sleep(3.5)
        device.click(*_CLICK_DISMISS_ANIMATION)
        time.sleep(1.5)

        s_final = device.screenshot()
        for _ in range(3):
            if is_intensify_home_screen(s_final):
                break
            device.click(*_CLICK_DISMISS_ANIMATION)
            time.sleep(1.0)
            s_final = device.screenshot()

        try:
            obs_after = read_intensify_home_panel(s_final, ctx.ocr)
        except Exception as ocr_err:
            _log.warning('[OPS] 强化后属性识别告警 ({}): 使用估算属性', ocr_err)
            obs_after = IntensifyHomePanelObservation(
                current=obs_before.current,
                gains=ShipStats(),
                can_intensify=False,
            )

        actual_mats = tuple(selected_this_batch) if selected_this_batch else batch.materials

        executed_batches.append(
            IntensifyBatchExecutionReport(
                target_name=batch.target.identity,
                target_index=batch.target_index,
                materials=[m.identity for m in actual_mats],
                gains=batch.contribution,
                stats_before=obs_before.current,
                stats_after=obs_after.current,
            )
        )

        # 5.4 动态快照前移维护 (B7)
        current_materials_obs = _remove_consumed_materials(
            current_materials_obs, replace(batch, materials=actual_mats)
        )

        max_stats = max_resolver(targets_snapshot.targets[batch.target_index].ship_id)
        from autowsgr.ui.live_intensify import is_home_target_fully_maxed

        fully_maxed = (
            max_stats is not None
            and is_home_target_fully_maxed(s_final, max_stats, ctx.ocr)
        )

        current_target_item = next((t for t in planning_targets if t.index == batch.target_index), None)
        if current_target_item is not None:
            actual_contribution = _sum_stats(m.contribution for m in actual_mats)
            req = _remaining_need(current_target_item.required_contribution, actual_contribution)
            if fully_maxed or req == ShipStats(0, 0, 0, 0):
                _log.info('[OPS] 目标 {} 全部属性已强化满（右侧面板全部 MAX），从目标列表中移出', batch.target.identity)
                maxed_index = batch.target_index
                planning_targets = [
                    replace(t, index=t.index - 1) if t.index > maxed_index else t
                    for t in planning_targets
                    if t.index != maxed_index
                ]
                current_selected_target_index = None
            else:
                planning_targets = [
                    replace(t, required_contribution=req) if t.index == batch.target_index else t
                    for t in planning_targets
                ]

    # 动态更新会话目标基线
    if reuse_target_inventory_baseline and planning_targets:
        active_target_refs = {t.target.ref for t in planning_targets}
        remaining_target_snapshots = tuple(
            t for t in targets_snapshot.targets if t.ref in active_target_refs
        )
        if remaining_target_snapshots:
            from autowsgr.ui.target_inventory_scanner import TargetInventorySnapshot

            _session_target_inventory_baseline = TargetInventorySnapshot(
                targets=tuple(
                    replace(t, global_index=new_idx)
                    for new_idx, t in enumerate(remaining_target_snapshots)
                ),
                total=len(remaining_target_snapshots),
                complete=True,
                revision=targets_snapshot.revision,
            )

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
