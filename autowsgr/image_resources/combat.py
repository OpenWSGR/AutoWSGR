"""战斗系统图像模板。

所有模板对应 ``autowsgr/data/images/combat/`` 下的 PNG 文件。
"""

from __future__ import annotations

from autowsgr.image_resources._lazy import LazyTemplate
from autowsgr.vision import ImageTemplate


class _ResultGrade:
    """战果评级模板。"""

    SS = LazyTemplate("combat/result/ss.png", "grade_ss")
    S = LazyTemplate("combat/result/s.png", "grade_s")
    A = LazyTemplate("combat/result/a.png", "grade_a")
    B = LazyTemplate("combat/result/b.png", "grade_b")
    C = LazyTemplate("combat/result/c.png", "grade_c")
    D = LazyTemplate("combat/result/d.png", "grade_d")
    LOOT = LazyTemplate("combat/result/loot.png", "grade_loot")

    @classmethod
    def all_grades(cls) -> list[ImageTemplate]:
        """SS→D 全部评级模板列表(不含 LOOT)。"""
        return [cls.SS, cls.S, cls.A, cls.B, cls.C, cls.D]


class CombatTemplates:
    """战斗系统图像模板统一入口。

    所有模板均为延迟加载，首次访问时才读取 PNG 文件。

    +---------------------------+-----------------------------+
    | 属性                      | 文件                        |
    +===========================+=============================+
    | FORMATION                 | combat/formation.png        |
    | SPOT_ENEMY                | combat/spot_enemy.png       |
    | RESULT                    | combat/result.png           |
    | FLAGSHIP_DAMAGE           | combat/flagship_damage.png  |
    | PROCEED                   | combat/proceed.png          |
    | NIGHT_BATTLE              | combat/night_battle.png     |
    | FIGHT_CONDITION           | combat/fight_condition.png  |
    | BYPASS                    | combat/bypass.png           |
    | RESULT_PAGE               | combat/result_page.png      |
    | MISSILE_SUPPORT           | combat/missile_support.png  |
    | MISSILE_ANIMATION         | combat/missile_animation.png|
    | FIGHT_PERIOD              | combat/fight_period.png     |
    | GET_SHIP                  | combat/get_ship.png         |
    | GET_ITEM                  | combat/get_item.png         |
    | END_MAP_PAGE              | combat/end_map_page.png     |
    | END_BATTLE_PAGE           | combat/end_battle_page.png  |
    | END_EXERCISE_PAGE         | combat/end_exercise_page.png|
    | SHIP_ICON_1               | combat/ship_icon_1.png      |
    | SHIP_ICON_2               | combat/ship_icon_2.png      |
    +---------------------------+-----------------------------+
    """

    # ── 战斗阶段 ──
    FORMATION = LazyTemplate("combat/formation.png", "formation")
    SPOT_ENEMY = LazyTemplate("combat/spot_enemy.png", "spot_enemy")
    RESULT = LazyTemplate("combat/result.png", "result")
    FLAGSHIP_DAMAGE = LazyTemplate("combat/flagship_damage.png", "flagship_damage")
    PROCEED = LazyTemplate("combat/proceed.png", "proceed")
    NIGHT_BATTLE = LazyTemplate("combat/night_battle.png", "night_battle")
    FIGHT_CONDITION = LazyTemplate("combat/fight_condition.png", "fight_condition")
    BYPASS = LazyTemplate("combat/bypass.png", "bypass")
    RESULT_PAGE = LazyTemplate("combat/result_page.png", "result_page")
    MISSILE_SUPPORT = LazyTemplate("combat/missile_support.png", "missile_support")
    MISSILE_ANIMATION = LazyTemplate("combat/missile_animation.png", "missile_animation")
    FIGHT_PERIOD = LazyTemplate("combat/fight_period.png", "fight_period")
    GET_SHIP = LazyTemplate("combat/get_ship.png", "get_ship")
    GET_ITEM = LazyTemplate("combat/get_item.png", "get_item")

    # ── 战斗终止态 ──
    END_MAP_PAGE = LazyTemplate("combat/end_map_page.png", "end_map_page")
    END_BATTLE_PAGE = LazyTemplate("combat/end_battle_page.png", "end_battle_page")
    END_EXERCISE_PAGE = LazyTemplate("combat/end_exercise_page.png", "end_exercise_page")

    # ── 地图追踪 ──
    SHIP_ICON_1 = LazyTemplate("combat/ship_icon_1.png", "ship_icon_1", source_resolution=(1280, 720))
    SHIP_ICON_2 = LazyTemplate("combat/ship_icon_2.png", "ship_icon_2", source_resolution=(1280, 720))

    # ── 战果评级 ──
    Result = _ResultGrade
