"""战斗系统图像模板资源。

集中管理战斗相关所有图像模板的加载与注册，供 ``CombatRecognizer``
和 ``PhaseHandlersMixin`` 中的 ``_image_exist`` / ``_click_image`` 回调使用。

资源路径指向 ``autowsgr/data/images/combat/`` 下的 PNG 文件。

Template key 命名规则
---------------------
``PHASE_SIGNATURES`` 和 ``_image_exist`` / ``_click_image`` 回调均使用同一套
字符串键。规则：

* 与单个阶段对应的模板 → 使用阶段语义名称，例如 ``"formation"``、``"proceed"``
* 需要任一匹配的多模板 → 以 ``_or_`` 分隔，例如 ``"get_ship_or_item"``
* 战果评级 → ``"grade_ss"``、``"grade_s"`` …

这些键通过 :data:`PHASE_TEMPLATE_MAP` 解析为
``list[ImageTemplate]``，供匹配器使用。

Usage::

    from autowsgr.combat.image_resources import CombatTemplates, PHASE_TEMPLATE_MAP

    # 直接使用模板对象
    template = CombatTemplates.FORMATION

    # 通过字符串键解析（用于动态调度）
    templates = PHASE_TEMPLATE_MAP["formation"]
"""

from __future__ import annotations

from pathlib import Path

from autowsgr.vision.image_template import ImageTemplate

# ═══════════════════════════════════════════════════════════════════════════════
# 资源根目录
# ═══════════════════════════════════════════════════════════════════════════════

_IMG_ROOT = Path(__file__).resolve().parent.parent / "data" / "images"


class _LazyTemplate:
    """延迟加载的图像模板描述符。首次访问时读取文件，之后缓存结果。"""

    def __init__(self, relative_path: str, name: str | None = None) -> None:
        self._path = relative_path
        self._name = name
        self._template: ImageTemplate | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr_name = name
        if self._name is None:
            self._name = name.lower()

    def __get__(self, obj: object, objtype: type | None = None) -> ImageTemplate:
        if self._template is None:
            self._template = ImageTemplate.from_file(
                _IMG_ROOT / self._path, name=self._name
            )
        return self._template


# ═══════════════════════════════════════════════════════════════════════════════
# 战斗阶段检测模板
# ═══════════════════════════════════════════════════════════════════════════════


class CombatTemplates:
    """战斗系统图像模板统一入口。

    所有模板均为延迟加载，首次访问时才读取 PNG 文件。

    文件位置映射（相对于 ``autowsgr/data/images/``）：

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
    +---------------------------+-----------------------------+
    """

    # ── 战斗阶段 ──────────────────────────────────────────────────────────────
    FORMATION = _LazyTemplate("combat/formation.png", "formation")
    """阵型选择界面。原 ``fight_image/1.PNG``。"""

    SPOT_ENEMY = _LazyTemplate("combat/spot_enemy.png", "spot_enemy")
    """索敌成功界面。原 ``fight_image/2.PNG``。"""

    RESULT = _LazyTemplate("combat/result.png", "result")
    """战果结算界面（等待加载）。原 ``fight_image/3.PNG``。"""

    FLAGSHIP_DAMAGE = _LazyTemplate("combat/flagship_damage.png", "flagship_damage")
    """旗舰大破撤退提示。原 ``fight_image/4.PNG``。"""

    PROCEED = _LazyTemplate("combat/proceed.png", "proceed")
    """继续前进 / 回港选择界面。原 ``fight_image/5.PNG``。"""

    NIGHT_BATTLE = _LazyTemplate("combat/night_battle.png", "night_battle")
    """夜战提示界面。原 ``fight_image/6.PNG``。"""

    FIGHT_CONDITION = _LazyTemplate("combat/fight_condition.png", "fight_condition")
    """战况分析界面。原 ``fight_image/10.PNG``。"""

    BYPASS = _LazyTemplate("combat/bypass.png", "bypass")
    """迂回战术按钮。原 ``fight_image/13.PNG``。"""

    RESULT_PAGE = _LazyTemplate("combat/result_page.png", "result_page")
    """战果页面标志（用于 ops/build 等）。原 ``fight_image/14.PNG``。"""

    MISSILE_SUPPORT = _LazyTemplate("combat/missile_support.png", "missile_support")
    """远程导弹支援按钮。原 ``fight_image/17.PNG``。"""

    MISSILE_ANIMATION = _LazyTemplate("combat/missile_animation.png", "missile_animation")
    """导弹动画帧识别。原 ``fight_image/20.png``。"""

    FIGHT_PERIOD = _LazyTemplate("combat/fight_period.png", "fight_period")
    """战斗进行中符号（帧循环检测）。原 ``symbol_image/4.png``。"""

    GET_SHIP = _LazyTemplate("combat/get_ship.png", "get_ship")
    """获取新舰船标志。原 ``symbol_image/8.PNG``。"""

    GET_ITEM = _LazyTemplate("combat/get_item.png", "get_item")
    """获取道具标志。原 ``symbol_image/13.PNG``。"""

    # ── 战斗终止态（返回页面识别）──────────────────────────────────────────────
    END_MAP_PAGE = _LazyTemplate("combat/end_map_page.png", "end_map_page")
    """战斗结束后出现的普通地图页面。原 ``identify_images/map_page.PNG``。"""

    END_BATTLE_PAGE = _LazyTemplate("combat/end_battle_page.png", "end_battle_page")
    """战役结束后出现的战役列表页面。原 ``identify_images/battle_page.PNG``。"""

    END_EXERCISE_PAGE = _LazyTemplate(
        "combat/end_exercise_page.png", "end_exercise_page"
    )
    """演习结束后出现的演习页面。原 ``identify_images/exercise_page1.png``。"""

    # ── 战果评级 ──────────────────────────────────────────────────────────────
    class Result:
        """战果评级模板。"""

        SS = _LazyTemplate("combat/result/ss.png", "grade_ss")
        """SS 评级。原 ``fight_result/SS.PNG``。"""

        S = _LazyTemplate("combat/result/s.png", "grade_s")
        """S 评级。原 ``fight_result/S.PNG``。"""

        A = _LazyTemplate("combat/result/a.png", "grade_a")
        """A 评级。原 ``fight_result/A.PNG``。"""

        B = _LazyTemplate("combat/result/b.png", "grade_b")
        """B 评级。原 ``fight_result/B.PNG``。"""

        C = _LazyTemplate("combat/result/c.png", "grade_c")
        """C 评级。原 ``fight_result/C.PNG``。"""

        D = _LazyTemplate("combat/result/d.png", "grade_d")
        """D 评级。原 ``fight_result/D.PNG``。"""

        LOOT = _LazyTemplate("combat/result/loot.png", "grade_loot")
        """掠夺/战利品标志。原 ``fight_result/LOOT.PNG``。"""

        @classmethod
        def all_grades(cls) -> list[ImageTemplate]:
            """SS→D 全部评级模板列表（不含 LOOT）。"""
            return [cls.SS, cls.S, cls.A, cls.B, cls.C, cls.D]


# ═══════════════════════════════════════════════════════════════════════════════
# 字符串键 → 模板列表映射
# ═══════════════════════════════════════════════════════════════════════════════

# 供 PhaseSignature.template_key 和 _image_exist/_click_image 回调使用。
# 所有键均为延迟求值（首次访问 CombatTemplates.* 时加载）。

def _build_map() -> dict[str, list[ImageTemplate]]:
    """构建 template_key → 模板列表的完整映射。"""
    T = CombatTemplates
    return {
        # 阶段模板
        "formation": [T.FORMATION],
        "spot_enemy": [T.SPOT_ENEMY],
        "result": [T.RESULT],
        "flagship_damage": [T.FLAGSHIP_DAMAGE],
        "proceed": [T.PROCEED],
        "night_battle": [T.NIGHT_BATTLE],
        "fight_condition": [T.FIGHT_CONDITION],
        "bypass": [T.BYPASS],
        "result_page": [T.RESULT_PAGE],
        "missile_support": [T.MISSILE_SUPPORT],
        "missile_animation": [T.MISSILE_ANIMATION],
        "fight_period": [T.FIGHT_PERIOD],
        "get_ship": [T.GET_SHIP],
        "get_item": [T.GET_ITEM],
        "get_ship_or_item": [T.GET_SHIP, T.GET_ITEM],
        # 战斗终止态
        "end_map_page": [T.END_MAP_PAGE],
        "end_battle_page": [T.END_BATTLE_PAGE],
        "end_exercise_page": [T.END_EXERCISE_PAGE],
        # 战果评级
        "grade_ss": [T.Result.SS],
        "grade_s": [T.Result.S],
        "grade_a": [T.Result.A],
        "grade_b": [T.Result.B],
        "grade_c": [T.Result.C],
        "grade_d": [T.Result.D],
        "grade_loot": [T.Result.LOOT],
    }


# 懒初始化：避免模块导入时加载所有图像文件
_PHASE_TEMPLATE_MAP: dict[str, list[ImageTemplate]] | None = None


def get_template(key: str) -> list[ImageTemplate]:
    """通过字符串键获取模板列表。

    Parameters
    ----------
    key:
        模板键，如 ``"formation"``、``"get_ship_or_item"``。

    Returns
    -------
    list[ImageTemplate]
        对应的模板列表（至少包含 1 个元素）。

    Raises
    ------
    KeyError
        当 key 在注册表中不存在时。
    """
    global _PHASE_TEMPLATE_MAP
    if _PHASE_TEMPLATE_MAP is None:
        _PHASE_TEMPLATE_MAP = _build_map()
    return _PHASE_TEMPLATE_MAP[key]


def resolve_image_matcher(
    image_checker_find_any,  # ImageChecker.find_any 或同签名函数
):
    """创建适合 CombatRecognizer 的 image_matcher 回调。

    将字符串键动态解析为对应模板列表，再调用 ``find_any`` 进行匹配。

    Parameters
    ----------
    image_checker_find_any:
        函数 ``(screen, templates, confidence) → MatchResult | None``。

    Returns
    -------
    Callable[[ndarray, str, float], bool]
        签名与 ``ImageMatcherFunc`` 兼容的匹配回调。
    """
    def _match(screen, template_key: str, confidence: float) -> bool:
        templates = get_template(template_key)
        return image_checker_find_any(screen, templates, confidence) is not None

    return _match


def resolve_image_exist(image_checker_find_any):
    """创建适合 PhaseHandlersMixin._image_exist 的回调。"""
    def _exist(template_key: str, confidence: float) -> bool:
        import autowsgr.emulator.controller as _ctrl
        # 此版本不绑定 screen，调用方须在 handlers 内部自行截图
        raise NotImplementedError(
            "resolve_image_exist 需要与截图绑定，请使用 resolve_image_matcher"
        )
    return _exist
