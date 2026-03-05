"""战斗系统图像模板。

所有模板对应 ``autowsgr/data/images/combat/`` 下的 PNG 文件。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.image_resources._lazy import LazyTemplate


if TYPE_CHECKING:
    from autowsgr.vision import ImageTemplate


class _ResultGrade:
    """战果评级模板。"""

    SS = LazyTemplate('combat/result/ss_540p.png', 'grade_ss')
    S = LazyTemplate('combat/result/s_540p.png', 'grade_s')
    A = LazyTemplate('combat/result/a_540p.png', 'grade_a')
    B = LazyTemplate('combat/result/b_540p.png', 'grade_b')
    C = LazyTemplate('combat/result/c_540p.png', 'grade_c')
    D = LazyTemplate('combat/result/d_540p.png', 'grade_d')
    LOOT = LazyTemplate('combat/result/loot_540p.png', 'grade_loot')

    @classmethod
    def all_grades(cls) -> list[ImageTemplate]:
        """SS→D 全部评级模板列表(不含 LOOT)。"""
        return [cls.SS, cls.S, cls.A, cls.B, cls.C, cls.D]


class CombatTemplates:
    """战斗系统图像模板统一入口。

    所有模板均为延迟加载，首次访问时才读取 PNG 文件。

    +---------------------------+--------------------------------------+
    | 属性                      | 文件                                 |
    +===========================+======================================+
    | FORMATION                 | combat/formation_540p.png            |
    | SPOT_ENEMY                | combat/spot_enemy_540p.png           |
    | RESULT                    | combat/result_540p.png               |
    | FLAGSHIP_DAMAGE           | combat/flagship_damage_540p.png      |
    | PROCEED                   | combat/proceed_540p.png              |
    | NIGHT_BATTLE              | combat/night_battle_540p.png         |
    | FIGHT_CONDITION           | combat/fight_condition_540p.png      |
    | BYPASS                    | combat/bypass_540p.png               |
    | RESULT_PAGE               | combat/result_page_540p.png          |
    | MISSILE_SUPPORT           | combat/missile_support_540p.png      |
    | MISSILE_ANIMATION         | combat/missile_animation_540p.png    |
    | FIGHT_PERIOD              | combat/fight_period_540p.png         |
    | GET_SHIP                  | combat/get_ship_540p.png             |
    | GET_ITEM                  | combat/get_item_540p.png             |
    | END_MAP_PAGE              | combat/end_map_page_540p.png         |
    | END_BATTLE_PAGE           | combat/end_battle_page_540p.png      |
    | END_EXERCISE_PAGE         | combat/end_exercise_page_540p.png    |
    +---------------------------+--------------------------------------+
    """

    # ── 战斗阶段 ──
    FORMATION = LazyTemplate('combat/formation_540p.png', 'formation')
    SPOT_ENEMY = LazyTemplate('combat/spot_enemy_540p.png', 'spot_enemy')
    RESULT = LazyTemplate('combat/result_540p.png', 'result')
    FLAGSHIP_DAMAGE = LazyTemplate('combat/flagship_damage_540p.png', 'flagship_damage')
    PROCEED = LazyTemplate('combat/proceed_540p.png', 'proceed')
    NIGHT_BATTLE = LazyTemplate('combat/night_battle_540p.png', 'night_battle')
    FIGHT_CONDITION = LazyTemplate('combat/fight_condition_540p.png', 'fight_condition')
    BYPASS = LazyTemplate('combat/bypass_540p.png', 'bypass')
    RESULT_PAGE = LazyTemplate('combat/result_page_540p.png', 'result_page')
    MISSILE_SUPPORT = LazyTemplate('combat/missile_support_540p.png', 'missile_support')
    MISSILE_ANIMATION = LazyTemplate('combat/missile_animation_540p.png', 'missile_animation')
    FIGHT_PERIOD = LazyTemplate('combat/fight_period_540p.png', 'fight_period')
    GET_SHIP = LazyTemplate('combat/get_ship_540p.png', 'get_ship')
    GET_ITEM = LazyTemplate('combat/get_item_540p.png', 'get_item')

    # ── 战斗终止态 ──
    END_MAP_PAGE = LazyTemplate('combat/end_map_page_540p.png', 'end_map_page')
    END_BATTLE_PAGE = LazyTemplate('combat/end_battle_page_540p.png', 'end_battle_page')
    END_EXERCISE_PAGE = LazyTemplate('combat/end_exercise_page_540p.png', 'end_exercise_page')

    # ── 船坞已满 ──
    DOCK_FULL = LazyTemplate('build/ship_full_depot_540p.png', 'dock_full')

    # ── 战役次数耗尽 ──
    BATTLE_TIMES_EXCEED = LazyTemplate('combat/battle_times_exceed_540p.png', 'battle_times_exceed')

    # ── 战果评级 ──
    Result = _ResultGrade
