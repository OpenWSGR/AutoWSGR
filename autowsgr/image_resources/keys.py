"""模板键枚举 — 替代硬编码字符串。

每个 :class:`TemplateKey` 成员对应一组 :class:`~autowsgr.vision.ImageTemplate`，
通过 ``.templates`` 属性延迟解析。

Usage::

    from autowsgr.image_resources import TemplateKey

    # 获取模板列表
    templates = TemplateKey.FORMATION.templates

    # 在识别器签名中使用
    PhaseSignature(template_key=TemplateKey.FORMATION, ...)
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autowsgr.vision import ImageTemplate


class TemplateKey(Enum):
    """模板标识枚举。

    每个成员的 ``value`` 为人类可读的标识字符串，
    ``.templates`` 属性返回对应的 ``list[ImageTemplate]``。
    """

    # ── 战斗阶段 ──
    FORMATION = "formation"
    SPOT_ENEMY = "spot_enemy"
    RESULT = "result"
    FLAGSHIP_DAMAGE = "flagship_damage"
    PROCEED = "proceed"
    NIGHT_BATTLE = "night_battle"
    FIGHT_CONDITION = "fight_condition"
    BYPASS = "bypass"
    RESULT_PAGE = "result_page"
    MISSILE_SUPPORT = "missile_support"
    MISSILE_ANIMATION = "missile_animation"
    FIGHT_PERIOD = "fight_period"
    GET_SHIP = "get_ship"
    GET_ITEM = "get_item"
    GET_SHIP_OR_ITEM = "get_ship_or_item"

    # ── 地图追踪 ──
    SHIP_ICON = "ship_icon"
    SHIP_ICON_1 = "ship_icon_1"
    SHIP_ICON_2 = "ship_icon_2"

    # ── 战斗终止态 ──
    END_MAP_PAGE = "end_map_page"
    END_BATTLE_PAGE = "end_battle_page"
    END_EXERCISE_PAGE = "end_exercise_page"

    # ── 船坞已满 ──
    DOCK_FULL = "dock_full"

    # ── 战果评级 ──
    GRADE_SS = "grade_ss"
    GRADE_S = "grade_s"
    GRADE_A = "grade_a"
    GRADE_B = "grade_b"
    GRADE_C = "grade_c"
    GRADE_D = "grade_d"
    GRADE_LOOT = "grade_loot"

    @property
    def templates(self) -> list[ImageTemplate]:
        """返回此键关联的模板列表 (延迟加载)。"""
        return _resolve(self)


# ═══════════════════════════════════════════════════════════════════════════════
# 内部映射 (延迟初始化)
# ═══════════════════════════════════════════════════════════════════════════════

_TEMPLATE_MAP: dict[TemplateKey, list[ImageTemplate]] | None = None


def _build_map() -> dict[TemplateKey, list[ImageTemplate]]:
    from autowsgr.image_resources.combat import CombatTemplates as T

    return {
        TemplateKey.FORMATION: [T.FORMATION],
        TemplateKey.SPOT_ENEMY: [T.SPOT_ENEMY],
        TemplateKey.RESULT: [T.RESULT],
        TemplateKey.FLAGSHIP_DAMAGE: [T.FLAGSHIP_DAMAGE],
        TemplateKey.PROCEED: [T.PROCEED],
        TemplateKey.NIGHT_BATTLE: [T.NIGHT_BATTLE],
        TemplateKey.FIGHT_CONDITION: [T.FIGHT_CONDITION],
        TemplateKey.BYPASS: [T.BYPASS],
        TemplateKey.RESULT_PAGE: [T.RESULT_PAGE],
        TemplateKey.MISSILE_SUPPORT: [T.MISSILE_SUPPORT],
        TemplateKey.MISSILE_ANIMATION: [T.MISSILE_ANIMATION],
        TemplateKey.FIGHT_PERIOD: [T.FIGHT_PERIOD],
        TemplateKey.GET_SHIP: [T.GET_SHIP],
        TemplateKey.GET_ITEM: [T.GET_ITEM],
        TemplateKey.GET_SHIP_OR_ITEM: [T.GET_SHIP, T.GET_ITEM],
        # 地图追踪
        TemplateKey.SHIP_ICON: [T.SHIP_ICON_1, T.SHIP_ICON_2],
        TemplateKey.SHIP_ICON_1: [T.SHIP_ICON_1],
        TemplateKey.SHIP_ICON_2: [T.SHIP_ICON_2],
        # 战斗终止态
        TemplateKey.END_MAP_PAGE: [T.END_MAP_PAGE],
        TemplateKey.END_BATTLE_PAGE: [T.END_BATTLE_PAGE],
        TemplateKey.END_EXERCISE_PAGE: [T.END_EXERCISE_PAGE],
        # 船坞已满
        TemplateKey.DOCK_FULL: [T.DOCK_FULL],
        # 战果评级
        TemplateKey.GRADE_SS: [T.Result.SS],
        TemplateKey.GRADE_S: [T.Result.S],
        TemplateKey.GRADE_A: [T.Result.A],
        TemplateKey.GRADE_B: [T.Result.B],
        TemplateKey.GRADE_C: [T.Result.C],
        TemplateKey.GRADE_D: [T.Result.D],
        TemplateKey.GRADE_LOOT: [T.Result.LOOT],
    }


def _resolve(key: TemplateKey) -> list[ImageTemplate]:
    global _TEMPLATE_MAP
    if _TEMPLATE_MAP is None:
        _TEMPLATE_MAP = _build_map()
    return _TEMPLATE_MAP[key]


def get_templates(key: TemplateKey) -> list[ImageTemplate]:
    """通过 :class:`TemplateKey` 枚举获取模板列表。

    这是 ``key.templates`` 属性的函数式等价写法。

    Parameters
    ----------
    key:
        模板键枚举值。

    Returns
    -------
    list[ImageTemplate]
        对应的模板列表。
    """
    return _resolve(key)


# ── 战果评级映射 (供 detect_result_grade 使用) ──

RESULT_GRADE_KEYS: dict[str, TemplateKey] = {
    "SS": TemplateKey.GRADE_SS,
    "S": TemplateKey.GRADE_S,
    "A": TemplateKey.GRADE_A,
    "B": TemplateKey.GRADE_B,
    "C": TemplateKey.GRADE_C,
    "D": TemplateKey.GRADE_D,
}
