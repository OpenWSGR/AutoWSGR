"""战斗状态枚举与状态转移图。
一次完整的 MAP 类战斗流程::
    PROCEED → FIGHT_CONDITION → SPOT_ENEMY_SUCCESS → FORMATION
        → FIGHT_PERIOD → NIGHT_PROMPT → RESULT → GET_SHIP → PROCEED → ...
"""

from __future__ import annotations

from enum import Enum, auto


class CombatPhase(Enum):
    """战斗阶段。

    每个枚举值代表战斗状态机中的一个离散状态。
    """

    # ── 出征过渡 ──
    START_FIGHT = auto()
    """点击出征后的短暂过渡：检测船坞已满或进入战斗。"""

    # ── 船坞已满 ──
    DOCK_FULL = auto()
    """出征时检测到船坞已满弹窗。"""

    # ── 航行 / 继续 ──
    PROCEED = auto()
    """继续前进 / 回港提示。"""

    # ── 战况选择 ──
    FIGHT_CONDITION = auto()
    """战况选择界面（稳步前进 / 火力万岁 等）。"""

    # ── 索敌 ──
    SPOT_ENEMY_SUCCESS = auto()
    """索敌成功，显示敌方编成。"""

    # ── 阵型选择 ──
    FORMATION = auto()
    """选择阵型界面。"""

    # ── 导弹支援 ──
    MISSILE_ANIMATION = auto()
    """导弹支援动画播放中。"""

    # ── 战斗进行 ──
    FIGHT_PERIOD = auto()
    """昼战 / 夜战战斗动画进行中。"""

    # ── 夜战提示 ──
    NIGHT_PROMPT = auto()
    """夜战选择提示（追击 / 撤退）。"""

    # ── 战果结算 ──
    RESULT = auto()
    """战果评价界面（S/A/B/C/D/SS）。"""

    # ── 掉落 ──
    GET_SHIP = auto()
    """获取舰船掉落。"""

    # ── 旗舰大破 ──
    FLAGSHIP_SEVERE_DAMAGE = auto()
    """旗舰大破强制回港。"""

    # ── 结束页面 ──
    MAP_PAGE = auto()
    """回到地图页面（常规战结束）。"""

    EXERCISE_PAGE = auto()
    """回到演习页面（演习结束）。"""

    EVENT_MAP_PAGE = auto()
    """回到活动地图页面（活动战斗结束）。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 模式分类与状态转移图
# ═══════════════════════════════════════════════════════════════════════════════

PhaseBranch = list[CombatPhase] | dict[str, list[CombatPhase]]
"""分支定义：无条件列表，或按动作名索引的字典。"""


class ModeCategory(Enum):
    """战斗模式大类。

    所有具体 ``CombatMode`` 归入这两类之一，转移图由大类 + ``end_page`` 唯一确定。

    MAP
        多节点地图模式。有战况选择、迂回、导弹支援、舰船掉落、旗舰大破、
        继续前进 / 回港 等完整流程。（常规战、活动战）
    SINGLE
        单点战斗模式。无多节点特性，只有核心战斗循环。
        ``end_page=None`` 时以 RESULT 为终止态。（战役、决战、演习）
    """

    MAP = auto()
    SINGLE = auto()


def build_transitions(
    category: ModeCategory,
    end_page: CombatPhase | None,
) -> dict[CombatPhase, PhaseBranch]:
    """根据模式大类和结束页面自动构建状态转移图。

    Parameters
    ----------
    category:
        ``MAP`` 或 ``SINGLE``。
    end_page:
        战斗结束游戏回到的页面状态。``None`` 表示以 ``RESULT`` 作为终止态。

    Returns
    -------
    dict[CombatPhase, PhaseBranch]
    """
    if category == ModeCategory.MAP:
        return _build_map_transitions(end_page)
    return _build_single_transitions(end_page)


def _build_map_transitions(
    end_page: CombatPhase | None,
) -> dict[CombatPhase, PhaseBranch]:
    """MAP 类：多节点地图战斗的完整转移图。"""
    ep = end_page  # 简写
    t: dict[CombatPhase, PhaseBranch] = {}

    # 地图移动后的着陆节点
    core_nav = [
        CombatPhase.FIGHT_CONDITION,
        CombatPhase.SPOT_ENEMY_SUCCESS,
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
    ]

    fight_targets = [
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
        CombatPhase.MISSILE_ANIMATION,
    ]

    # RESULT 之后
    after_result = [CombatPhase.PROCEED]
    if ep is not None:
        after_result.append(ep)
    after_result += [CombatPhase.GET_SHIP, CombatPhase.FLAGSHIP_SEVERE_DAMAGE]

    # ── 各节点 ──
    start = list(core_nav)
    if ep is not None:
        start.append(ep)
    start.append(CombatPhase.DOCK_FULL)
    t[CombatPhase.START_FIGHT] = start

    t[CombatPhase.DOCK_FULL] = []

    proceed_yes = list(core_nav)
    if ep is not None:
        proceed_yes.append(ep)
    t[CombatPhase.PROCEED] = {
        'yes': proceed_yes,
        'no': [ep] if ep is not None else [],
    }

    t[CombatPhase.FIGHT_CONDITION] = [
        CombatPhase.SPOT_ENEMY_SUCCESS,
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
    ]

    t[CombatPhase.SPOT_ENEMY_SUCCESS] = {
        'fight': list(fight_targets),
        'detour': list(core_nav),
        'retreat': [ep] if ep is not None else [],
    }

    t[CombatPhase.FORMATION] = [
        CombatPhase.FIGHT_PERIOD,
        CombatPhase.MISSILE_ANIMATION,
    ]

    t[CombatPhase.MISSILE_ANIMATION] = [
        CombatPhase.FIGHT_PERIOD,
        CombatPhase.RESULT,
    ]

    t[CombatPhase.FIGHT_PERIOD] = [CombatPhase.NIGHT_PROMPT, CombatPhase.RESULT]
    t[CombatPhase.NIGHT_PROMPT] = {
        'yes': [CombatPhase.RESULT],
        'no': [CombatPhase.RESULT],
    }

    t[CombatPhase.RESULT] = list(after_result)

    # GET_SHIP 后继 = RESULT 后继 去掉 GET_SHIP 自身
    t[CombatPhase.GET_SHIP] = [p for p in after_result if p != CombatPhase.GET_SHIP]

    if ep is not None:
        t[CombatPhase.FLAGSHIP_SEVERE_DAMAGE] = [ep]

    return t


def _build_single_transitions(
    end_page: CombatPhase | None,
) -> dict[CombatPhase, PhaseBranch]:
    """SINGLE 类：单点战斗的精简转移图。"""
    ep = end_page
    t: dict[CombatPhase, PhaseBranch] = {}

    core = [
        CombatPhase.SPOT_ENEMY_SUCCESS,
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
    ]

    t[CombatPhase.START_FIGHT] = list(core) + [
        CombatPhase.DOCK_FULL,
    ]
    t[CombatPhase.DOCK_FULL] = []

    t[CombatPhase.SPOT_ENEMY_SUCCESS] = {
        'fight': [CombatPhase.FORMATION, CombatPhase.FIGHT_PERIOD],
        'retreat': [ep] if ep is not None else [],
    }

    t[CombatPhase.FORMATION] = [CombatPhase.FIGHT_PERIOD]
    t[CombatPhase.FIGHT_PERIOD] = [CombatPhase.NIGHT_PROMPT, CombatPhase.RESULT]
    t[CombatPhase.NIGHT_PROMPT] = {
        'yes': [CombatPhase.RESULT],
        'no': [CombatPhase.RESULT],
    }

    if ep is not None:
        t[CombatPhase.RESULT] = [ep]
    # ep is None → RESULT 为终止态，无后继

    return t


def resolve_successors(
    transitions: dict[CombatPhase, PhaseBranch],
    phase: CombatPhase,
    last_action: str,
) -> list[CombatPhase]:
    """根据当前状态和上一步动作，解析出候选后继状态列表。

    Parameters
    ----------
    transitions:
        状态转移图。
    phase:
        当前状态。
    last_action:
        上一步动作名称（用于 action-dependent 分支）。

    Returns
    -------
    list[CombatPhase]

    Raises
    ------
    KeyError
        当前状态不在转移图中。
    """
    branch = transitions[phase]

    if isinstance(branch, dict):
        targets = branch.get(last_action)
        if targets is None:
            targets = next(iter(branch.values()))
    else:
        targets = branch

    return list(targets)
