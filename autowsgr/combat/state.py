"""战斗状态枚举与状态转移图。

战斗过程独立于正常 UI 页面框架，使用自有的状态机驱动。
状态转移图 ``PHASE_TRANSITIONS`` 定义了每个状态的合法后继，
并可根据上一步的 *动作* 进一步分支 (action-dependent transitions)。

一次完整的常规战斗流程::

    PROCEED → FIGHT_CONDITION → SPOT_ENEMY_SUCCESS → FORMATION
        → FIGHT_PERIOD → NIGHT_PROMPT → RESULT → GET_SHIP → PROCEED → ...
"""

from __future__ import annotations

from enum import Enum, auto


class CombatPhase(Enum):
    """战斗阶段。

    每个枚举值代表战斗状态机中的一个离散状态。
    """

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

    BATTLE_PAGE = auto()
    """回到战役页面（战役结束）。"""

    EXERCISE_PAGE = auto()
    """回到演习页面（演习结束）。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 状态转移图
# ═══════════════════════════════════════════════════════════════════════════════

# 转移值类型说明:
#   list[CombatPhase]  — 无条件后继
#   dict[str, list]    — 依赖上一步动作 (action) 的分支后继
#   元素为 tuple(CombatPhase, float) 时，float 为该状态的超时覆盖值

PhaseTarget = CombatPhase | tuple[CombatPhase, float]
"""后继目标：可以是纯状态，或 (状态, 超时覆盖) 二元组。"""

PhaseBranch = list[PhaseTarget] | dict[str, list[PhaseTarget]]
"""分支定义：无条件列表，或按动作名索引的字典。"""


# ── 常规战 ──

NORMAL_FIGHT_TRANSITIONS: dict[CombatPhase, PhaseBranch] = {
    CombatPhase.PROCEED: {
        "yes": [
            CombatPhase.FIGHT_CONDITION,
            CombatPhase.SPOT_ENEMY_SUCCESS,
            CombatPhase.FORMATION,
            CombatPhase.FIGHT_PERIOD,
            CombatPhase.MAP_PAGE,
        ],
        "no": [CombatPhase.MAP_PAGE],
    },
    CombatPhase.FIGHT_CONDITION: [
        CombatPhase.SPOT_ENEMY_SUCCESS,
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
    ],
    CombatPhase.SPOT_ENEMY_SUCCESS: {
        "detour": [
            CombatPhase.FIGHT_CONDITION,
            CombatPhase.SPOT_ENEMY_SUCCESS,
            CombatPhase.FORMATION,
            CombatPhase.FIGHT_PERIOD,
        ],
        "retreat": [CombatPhase.MAP_PAGE],
        "fight": [
            CombatPhase.FORMATION,
            CombatPhase.FIGHT_PERIOD,
            CombatPhase.MISSILE_ANIMATION,
        ],
    },
    CombatPhase.FORMATION: [
        CombatPhase.FIGHT_PERIOD,
        CombatPhase.MISSILE_ANIMATION,
    ],
    CombatPhase.MISSILE_ANIMATION: [
        CombatPhase.FIGHT_PERIOD,
        CombatPhase.RESULT,
    ],
    CombatPhase.FIGHT_PERIOD: [
        CombatPhase.NIGHT_PROMPT,
        CombatPhase.RESULT,
    ],
    CombatPhase.NIGHT_PROMPT: {
        "yes": [CombatPhase.RESULT],
        "no": [(CombatPhase.RESULT, 10.0)],
    },
    CombatPhase.RESULT: [
        CombatPhase.PROCEED,
        CombatPhase.MAP_PAGE,
        CombatPhase.GET_SHIP,
        CombatPhase.FLAGSHIP_SEVERE_DAMAGE,
    ],
    CombatPhase.GET_SHIP: [
        CombatPhase.PROCEED,
        CombatPhase.MAP_PAGE,
        CombatPhase.FLAGSHIP_SEVERE_DAMAGE,
    ],
    CombatPhase.FLAGSHIP_SEVERE_DAMAGE: [CombatPhase.MAP_PAGE],
}


# ── 战役 ──

BATTLE_TRANSITIONS: dict[CombatPhase, PhaseBranch] = {
    CombatPhase.PROCEED: [
        CombatPhase.SPOT_ENEMY_SUCCESS,
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
    ],
    CombatPhase.SPOT_ENEMY_SUCCESS: {
        "retreat": [CombatPhase.BATTLE_PAGE],
        "fight": [CombatPhase.FORMATION, CombatPhase.FIGHT_PERIOD],
    },
    CombatPhase.FORMATION: [CombatPhase.FIGHT_PERIOD],
    CombatPhase.FIGHT_PERIOD: [
        CombatPhase.NIGHT_PROMPT,
        CombatPhase.RESULT,
    ],
    CombatPhase.NIGHT_PROMPT: {
        "yes": [CombatPhase.RESULT],
        "no": [(CombatPhase.RESULT, 7.0)],
    },
    CombatPhase.RESULT: [CombatPhase.BATTLE_PAGE],
}


# ── 演习 ──

EXERCISE_TRANSITIONS: dict[CombatPhase, PhaseBranch] = {
    CombatPhase.PROCEED: [
        CombatPhase.SPOT_ENEMY_SUCCESS,
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
    ],
    CombatPhase.SPOT_ENEMY_SUCCESS: [
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
    ],
    CombatPhase.FORMATION: [CombatPhase.FIGHT_PERIOD],
    CombatPhase.FIGHT_PERIOD: [
        CombatPhase.NIGHT_PROMPT,
        CombatPhase.RESULT,
    ],
    CombatPhase.NIGHT_PROMPT: {
        "yes": [CombatPhase.RESULT],
        "no": [(CombatPhase.RESULT, 7.0)],
    },
    CombatPhase.RESULT: [CombatPhase.EXERCISE_PAGE],
}


def resolve_successors(
    transitions: dict[CombatPhase, PhaseBranch],
    phase: CombatPhase,
    last_action: str,
) -> list[tuple[CombatPhase, float | None]]:
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
    list[tuple[CombatPhase, float | None]]
        ``(后继状态, 超时覆盖)`` 列表。超时为 ``None`` 表示使用默认值。

    Raises
    ------
    KeyError
        当前状态不在转移图中。
    """
    branch = transitions[phase]

    if isinstance(branch, dict):
        targets = branch.get(last_action)
        if targets is None:
            # 回退到第一个分支
            targets = next(iter(branch.values()))
    else:
        targets = branch

    result: list[tuple[CombatPhase, float | None]] = []
    for t in targets:
        if isinstance(t, tuple):
            result.append((t[0], t[1]))
        else:
            result.append((t, None))
    return result
