"""使用不含敌情观测的历史定位核对 native 敌舰识别；不符时由会话告警请求反馈。

参照节点仍是独立证据形成的估计，并非人工真值。只比较所有合法敌情变体均一致的
字段，避免用待测识别结果选择最相似的模板，再把它当作正确答案。普通战第 3 槽
战利品补给不告警；整队 AP 过期签名的资料豁免是独立规则。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

from autowsgr_native.vessel_type import VesselType

from autowsgr.combat.node_fusion.map import SHIP_TYPES
from autowsgr.combat.plan import CombatMode


if TYPE_CHECKING:
    from autowsgr.combat.node_fusion.enemy import EnemyObservation
    from autowsgr.combat.node_fusion.map import TrackingNode
    from autowsgr.combat.node_fusion.model import FusionTracker


REFERENCE_THRESHOLD = 0.95
NATIVE_VERSION = version('autowsgr-native')
_NATIVE_SHIPS = {
    value.as_english(): value.as_chinese()
    for name in dir(VesselType)
    if isinstance(value := getattr(VesselType, name), VesselType) and value.as_english() != 'NO'
}
_AP_SHIP = VesselType.AP.as_chinese()


@dataclass(frozen=True)
class SlotMismatch:
    """确认定位遭遇中与地图签名不符的槽位；保留原始识别码便于反馈排查。"""

    node: str
    slot: int
    expected: str
    code: str
    recognized: str
    event_id: int
    encounter_id: str | None


def _is_ap_signature(variants: Any) -> bool:
    """全部变体整队为 AP；活动动态点签名可能过期，核对结果不可信。"""
    return bool(variants) and all(
        any(ship is not None for ship in item.ships)
        and all(ship in (None, _AP_SHIP) for ship in item.ships)
        for item in variants
    )


def _reference_history(
    tracker: FusionTracker,
) -> tuple[dict[int, dict[str, Any]], dict[int, int | None], set[int]]:
    """去掉全部敌情重新平滑；原始敌情读数不参与参照节点或遭遇归属。"""
    reference = tracker.clone_without_enemy()
    anchors: dict[int, int | None] = {}
    invalid = set()
    last_phase = None
    for event_id, observation in enumerate(tracker.observations):
        estimate = reference.observe(replace(observation, enemies=None, decision_node=None))
        if observation.kind != 'phase':
            continue
        if estimate.ignored == 'same phase evidence segment':
            # 被参照模型合并的同页读数仍对应原始首次截图，不能选择后来成功的读数。
            anchors[event_id] = last_phase
        elif estimate.ignored:
            invalid.add(event_id)
        else:
            last_phase = event_id if estimate.anomaly is None else None
            anchors[event_id] = last_phase
    return {row['event_id']: row for row in reference.estimate.history}, anchors, invalid


def _slot_mismatches(
    enemy: EnemyObservation | None, node: TrackingNode, combat_mode: str
) -> list[tuple[int, str, str, str]]:
    """核对一次观测；只报真识别错误，不可核对与机制性偏差静默跳过。"""
    variants = node.enemy_formations
    raw_slots = (
        enemy.raw_slots
        if enemy is not None and enemy.valid_slots and len(enemy.raw_slots) == 6
        else None
    )
    if not variants or _is_ap_signature(variants):
        return []
    found = []
    for index in range(6):
        expected = {item.ships[index] if index < len(item.ships) else None for item in variants}
        if len(expected) != 1 or expected == {None}:
            # 变体分歧或空槽没有唯一真值，不可核对。
            continue
        true_ship = next(iter(expected))
        if true_ship not in SHIP_TYPES:
            continue
        if raw_slots is None:
            continue
        code = raw_slots[index]
        # NO、未知码等无效读数没有"错成了什么"，不构成反馈内容。
        value = _NATIVE_SHIPS.get(code) if isinstance(code, str) else None
        if value is None:
            continue
        if value == true_ship:
            continue
        if value == _AP_SHIP and combat_mode == CombatMode.NORMAL and index == 2:
            # 只有普通战第 3 槽会被战利品补给替换；活动与决战没有此机制。
            continue
        found.append((index + 1, true_ship, code, value))
    return found


def recognition_mismatches(
    tracker: FusionTracker, *, combat_mode: str = CombatMode.NORMAL
) -> list[SlotMismatch]:
    """确认定位遭遇中与地图签名不符的槽位；每个独立遭遇只取最早索敌帧。"""
    mismatches: list[SlotMismatch] = []
    if not any(obs.phase == 'SPOT_ENEMY_SUCCESS' for obs in tracker.observations):
        return mismatches
    history, anchors, invalid = _reference_history(tracker)
    encounters: dict[int, int] = {}
    encounter = 0
    for event_id, row in sorted(history.items()):
        if row['transition'] in ('new_encounter', 'geometric_arrival'):
            encounter += 1
        encounters[event_id] = encounter
    seen = set()
    action_generation = 0
    for event_id, observation in enumerate(tracker.observations):
        if (
            observation.kind == 'action'
            and observation.action in ('proceed', 'detour')
            and observation.clicked is not False
        ):
            action_generation += 1
        if observation.kind != 'phase' or observation.phase != 'SPOT_ENEMY_SUCCESS':
            continue
        if event_id in invalid:
            continue
        anchor = anchors.get(event_id)
        key = (
            ('id', observation.encounter_id)
            if observation.encounter_id is not None
            else (
                ('encounter', encounters[anchor])
                if anchor in encounters
                else ('unknown', action_generation)
            )
        )
        if key in seen or (
            observation.encounter_id is None and ('unknown', action_generation) in seen
        ):
            # 同一航行段中由无法定位恢复为已定位，仍保留首次原始读数。
            seen.add(key)
            continue
        seen.add(key)
        row = history.get(anchor, {})
        weights = row.get('node_weights', {})
        best = max(weights, key=weights.get) if weights else None
        node = tracker.map_data.nodes.get(best)
        if (
            best == '0'
            or node is None
            or node.silent
            or weights[best] < REFERENCE_THRESHOLD
            or row.get('viterbi_node') != best
        ):
            continue
        for slot, expected, code, recognized in _slot_mismatches(
            observation.enemies, node, combat_mode
        ):
            mismatches.append(
                SlotMismatch(
                    node=best,
                    slot=slot,
                    expected=expected,
                    code=code,
                    recognized=recognized,
                    event_id=event_id,
                    encounter_id=observation.encounter_id,
                )
            )
    return mismatches
