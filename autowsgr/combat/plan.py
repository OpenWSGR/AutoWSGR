"""作战计划 — YAML 配置驱动的战斗决策。

每个地图节点关联一个 ``NodeDecision``，定义该节点的战术决策：
阵型、夜战、索敌规则、SL 条件等。

``CombatPlan`` 聚合多个节点的决策，并提供 YAML 加载能力。

"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autowsgr.infra import NodeConfig, load_yaml
from autowsgr.infra.logger import get_logger
from autowsgr.types import FightCondition, Formation, RepairMode

from .fleet import FleetPreset, fleet_presets_from_yaml
from .rules import RuleEngine
from .state import (
    CombatPhase,
    ModeCategory,
    PhaseBranch,
    build_transitions,
)


_log = get_logger('combat')


# ═══════════════════════════════════════════════════════════════════════════════
# 节点决策
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class NodeDecision:
    """单个地图节点的战术决策。

    与旧代码 ``DecisionBlock`` 的配置对应，但不包含运行时状态。
    运行时状态由 ``CombatEngine`` 管理。

    Attributes
    ----------
    formation:
        默认阵型。
    night:
        是否进入夜战。
    proceed:
        是否继续前进。
    proceed_stop:
        达到此破损等级时停止前进。
    enemy_rules:
        索敌规则引擎（按敌方舰种判断）。
    formation_rules:
        阵型规则引擎（按敌方阵型判断，优先级高于 enemy_rules）。
    detour:
        是否迂回。
    long_missile_support:
        是否开启远程导弹支援。
    SL_when_spot_enemy_fails:
        索敌失败时是否 SL。
    SL_when_detour_fails:
        迂回失败时是否 SL。
    SL_when_enter_fight:
        进入战斗时是否 SL（用于卡点）。
    formation_when_spot_enemy_fails:
        索敌失败时使用的替代阵型。
    """

    formation: Formation = Formation.double_column
    night: bool = False
    proceed: bool = True
    proceed_stop: RepairMode | list[RepairMode] = RepairMode.severe_damage
    enemy_rules: RuleEngine | None = None
    formation_rules: RuleEngine | None = None
    detour: bool = False
    long_missile_support: bool = False
    SL_when_spot_enemy_fails: bool = False
    SL_when_detour_fails: bool = True
    SL_when_enter_fight: bool = False
    formation_when_spot_enemy_fails: Formation | None = None

    @classmethod
    def from_node_config(cls, config: NodeConfig) -> NodeDecision:
        """从 ``NodeConfig`` (Pydantic) 构建。"""
        enemy_rules = None
        if config.enemy_rules:
            enemy_rules = RuleEngine.from_legacy_rules(
                [_parse_rule_item(r) for r in config.enemy_rules]
            )

        formation_rules = None
        if config.enemy_formation_rules:
            formation_rules = RuleEngine.from_formation_rules(
                [_parse_rule_item(r) for r in config.enemy_formation_rules]
            )

        formation_when_fail = None
        if config.formation_when_spot_enemy_fails is not None:
            formation_when_fail = Formation(config.formation_when_spot_enemy_fails)

        return cls(
            formation=Formation(config.formation),
            night=config.night,
            proceed=config.proceed,
            proceed_stop=config.proceed_stop,
            enemy_rules=enemy_rules,
            formation_rules=formation_rules,
            detour=config.detour,
            long_missile_support=config.long_missile_support,
            SL_when_spot_enemy_fails=config.SL_when_spot_enemy_fails,
            SL_when_detour_fails=config.SL_when_detour_fails,
            SL_when_enter_fight=config.SL_when_enter_fight,
            formation_when_spot_enemy_fails=formation_when_fail,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeDecision:
        """从原始字典构建节点决策。"""
        config = NodeConfig.model_validate(data)
        return cls.from_node_config(config)


def _parse_rule_item(rule: str | list) -> list:
    """解析单条规则项。

    支持两种格式:
      - 字符串: ``"(BB >= 2) and (CV > 0) => retreat"``
      - 列表: ``["(BB >= 2) and (CV > 0)", "retreat"]``
    """
    if isinstance(rule, str):
        # 尝试解析 "condition => action" 格式
        if '=>' in rule:
            parts = rule.split('=>', 1)
            return [parts[0].strip(), parts[1].strip()]
        return [rule, 'retreat']
    if isinstance(rule, list) and len(rule) >= 2:
        return rule[:2]
    raise ValueError(f'无法解析规则: {rule!r}')


# ═══════════════════════════════════════════════════════════════════════════════
# 战斗模式
# ═══════════════════════════════════════════════════════════════════════════════


class CombatMode:
    """战斗模式标识与对应的状态转移图。"""

    NORMAL = 'normal'
    """常规战（多点地图）。"""

    BATTLE = 'battle'
    """战役（单点）。"""

    EXERCISE = 'exercise'
    """演习。"""

    DECISIVE = 'decisive'
    """决战 (单点战斗，RESULT 即终止)。"""

    EVENT = 'event'
    """活动战斗 (与常规战类似，但终止态为活动地图页面)。"""


# ── 模式配置 ── 每种战斗模式只需指定大类和结束页 ──────────────

_ModeSpec = tuple[ModeCategory, CombatPhase | None]
"""模式规格: (大类, 结束页面)。``None`` 的 end_page 表示 RESULT 即终止。"""

_MODE_SPECS: dict[str, _ModeSpec] = {
    CombatMode.NORMAL: (ModeCategory.MAP, CombatPhase.MAP_PAGE),
    CombatMode.EVENT: (ModeCategory.MAP, CombatPhase.EVENT_MAP_PAGE),
    CombatMode.BATTLE: (ModeCategory.SINGLE, None),
    CombatMode.DECISIVE: (ModeCategory.SINGLE, None),
    CombatMode.EXERCISE: (ModeCategory.SINGLE, CombatPhase.EXERCISE_PAGE),
}

# ── 由规格自动派生的映射表 ──

MODE_TRANSITIONS: dict[str, dict[CombatPhase, PhaseBranch]] = {
    mode: build_transitions(cat, ep) for mode, (cat, ep) in _MODE_SPECS.items()
}

MODE_END_PHASES: dict[str, CombatPhase] = {
    mode: (ep if ep is not None else CombatPhase.RESULT) for mode, (_cat, ep) in _MODE_SPECS.items()
}

MODE_CATEGORIES: dict[str, ModeCategory] = {mode: cat for mode, (cat, _ep) in _MODE_SPECS.items()}


# ═══════════════════════════════════════════════════════════════════════════════
# 作战计划
# ═══════════════════════════════════════════════════════════════════════════════


def parse_map_value(map_value: Any) -> tuple[int, str | None]:
    """解析 plan 的 ``map`` 字段，返回 ``(map_id, entrance)``。

    纯数字 (``1`` 或 ``'1'``)  -> ``(1, None)``   # 无入口 (常规战 / 旧活动)
    ``'1a'`` / ``'1A'``       -> ``(1, 'a')``     # α 入口
    ``'3b'`` / ``'3B'``       -> ``(3, 'b')``     # β 入口

    入口绑定在活动地图文件名上 (α/β)，不再作为独立配置项。
    """
    m = re.fullmatch(r'(\d+)([abAB])?', str(map_value).strip())
    if not m:
        raise ValueError(
            f'无法解析 map 值: {map_value!r}, 应为数字或 数字+a/b (如 1、1a、3b)',
        )
    entrance = m.group(2).lower() if m.group(2) else None
    return int(m.group(1)), entrance


@dataclass
class CombatPlan:
    """完整的作战计划。

    聚合出征配置 + 每个节点的战术决策。

    Attributes
    ----------
    name:
        计划名称（日志用）。
    mode:
        战斗模式 (normal / battle / exercise / decisive / event)。
    chapter:
        章节号。
    map_id:
        地图号。
    fleet_id:
        出征舰队编号。
    fleet:
        舰队成员名单（换船用）。
    fleet_presets:
        GUI 整理后的舰队预设列表。
    repair_mode:
        修理策略。
    fight_condition:
        战况选择。
    selected_nodes:
        白名单节点列表（常规战）。
    nodes:
        每个节点的战术决策。
    default_node:
        未配置节点的默认决策。
    """

    name: str = ''
    mode: str = CombatMode.NORMAL
    chapter: int | str = 1
    map_id: int | str = 1
    entrance: str | None = None
    """活动入口: ``'a'``=α / ``'b'``=β / ``None``=无入口。

    从 yaml ``map`` 字段 (如 ``1a``) 解析，仅活动地图有 α/β 入口概念。
    """
    fleet_id: int = 1
    fleet: list[str] | None = None
    fleet_presets: tuple[FleetPreset, ...] | None = None
    repair_mode: RepairMode | list[RepairMode] = RepairMode.severe_damage
    fight_condition: FightCondition = FightCondition.aim
    selected_nodes: list[str] = field(default_factory=list)
    nodes: dict[str, NodeDecision] = field(default_factory=dict)
    default_node: NodeDecision = field(default_factory=NodeDecision)
    event_name: str | None = None
    """活动名称（如 ``"20260212"``），用于定位活动地图节点数据。
    在 YAML 中写为 ``event: "20260212"``。"""
    collect_result_info: bool = False
    """是否在战果/经验结算页停留采集信息 (评级/MVP) — 慢速通过。

    ``False`` (默认, 快速穿行): 经验结算页是过渡页, RESULT 识别后点击
    循环直接穿行到掉落/前进/终态页, 不为页面停留 (血量检测除外, 单次
    截图, 全局舰队状态同步需要)。多数刷战斗模式用此默认。

    ``True`` (慢速): 经验页入状态机逐页推进, RESULT 页完整采集评级与
    MVP (:class:`FightResult` / 战斗历史)。需要战果信息决策的调用方设
    此项 (如 normal_fight 条件战斗按评级判定是否计入次数)。"""

    def __post_init__(self) -> None:
        """\u5c06单个 repair_mode 展开为 6 个位置的列表，保证属性始终为 ``list[RepairMode]``。"""
        if not isinstance(self.repair_mode, list):
            self.repair_mode = [self.repair_mode] * 6

    @property
    def transitions(self) -> dict[CombatPhase, PhaseBranch]:
        """当前计划的状态转移图 (按模式 + ``collect_result_info`` 构建)。"""
        category, ep = _MODE_SPECS[self.mode]
        return build_transitions(
            category,
            ep,
            collect_result_info=self.collect_result_info,
        )

    @property
    def end_phase(self) -> CombatPhase:
        """获取当前模式的结束状态。"""
        return MODE_END_PHASES[self.mode]

    def get_node_decision(self, node: str) -> NodeDecision:
        """获取指定节点的决策，不存在则返回默认决策。"""
        return self.nodes.get(node, self.default_node)

    def is_selected_node(self, node: str) -> bool:
        """节点是否在白名单中。"""
        if not self.selected_nodes:
            return True  # 未配置白名单 = 全部允许
        return node in self.selected_nodes

    @classmethod
    def from_yaml(cls, path: str | Path) -> CombatPlan:
        from autowsgr.infra.config_compat import (
            LegacyConfigError,
            detect_legacy_plan,
        )

        data = load_yaml(path)
        legacy = detect_legacy_plan(data)
        if legacy:
            raise LegacyConfigError(
                f'计划文件 {path} 含 classic 老版本格式, 拒绝加载:\n  - '
                + '\n  - '.join(legacy)
                + '\n请先运行迁移工具迁移计划目录 (原文件不动):\n'
                '  python tools/migrate_config.py --planroot <计划目录>'
                '  (默认输出到 migrated_config/)',
            )
        return cls.from_dict(data, name=Path(path).stem)

    @classmethod
    def from_dict(cls, data: dict[str, Any], name: str = '') -> CombatPlan:
        # 基础配置
        mode = data.get('mode', CombatMode.NORMAL)
        chapter = data.get('chapter', 1)
        map_id, entrance = parse_map_value(data.get('map', 1))
        fleet_id = data.get('fleet_id', 1)
        fleet = data.get('fleet')
        fleet_presets = fleet_presets_from_yaml(data.get('fleet_presets'))
        fight_condition = FightCondition(data.get('fight_condition', 4))
        selected_nodes = data.get('selected_nodes', [])

        # 修理模式
        repair_mode_raw = data.get('repair_mode', 2)
        if isinstance(repair_mode_raw, list):
            repair_mode = [RepairMode(x) for x in repair_mode_raw]
        else:
            repair_mode = RepairMode(repair_mode_raw)

        # 默认节点配置
        node_defaults = data.get('node_defaults', {})
        default_node = NodeDecision.from_dict(node_defaults)

        # 各节点配置
        nodes: dict[str, NodeDecision] = {}
        node_args_data = data.get('node_args', {})
        if node_args_data:
            for node_name, node_data in node_args_data.items():
                # 合并默认配置和节点特有配置
                merged = copy.deepcopy(node_defaults)
                if node_data:
                    merged.update(node_data)
                nodes[node_name] = NodeDecision.from_dict(merged)

        # 未在 node_args 中出现但在 selected_nodes 中的节点，使用默认配置
        for node_name in selected_nodes:
            if node_name not in nodes:
                nodes[node_name] = copy.deepcopy(default_node)

        event_name: str | None = data.get('event') or None

        plan = cls(
            name=name or data.get('name', ''),
            mode=mode,
            chapter=chapter,
            map_id=map_id,
            entrance=entrance,
            fleet_id=fleet_id,
            fleet=fleet,
            fleet_presets=fleet_presets,
            repair_mode=repair_mode,
            fight_condition=fight_condition,
            selected_nodes=selected_nodes,
            nodes=nodes,
            default_node=default_node,
            event_name=event_name,
        )

        _log.info(
            '[Combat] 加载作战计划: {} ({}), 章节 {}-{}, 节点: {}',
            plan.name,
            plan.mode,
            plan.chapter,
            plan.map_id,
            list(plan.nodes.keys()) or '全部',
        )

        return plan
