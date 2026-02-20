"""图像模板资源注册中心。

集中管理所有业务操作所需的图像模板。

所有模板使用 :class:`~autowsgr.vision.image_template.ImageTemplate` 封装，
通过 :class:`ImageChecker` 进行匹配检测。

资源路径指向 ``autowsgr/data/images/`` 下的 PNG 文件。
与战斗系统共享的模板（如夜战、战果）直接复用
:class:`~autowsgr.combat.image_resources.CombatTemplates`，避免重复加载。

Usage::

    from autowsgr.ops.image_resources import Templates

    screen = ctrl.screenshot()
    if ImageChecker.template_exists(screen, Templates.Cook.COOK_BUTTON):
        ...
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from autowsgr.vision.image_template import ImageTemplate

# ═══════════════════════════════════════════════════════════════════════════════
# 资源根目录
# ═══════════════════════════════════════════════════════════════════════════════

_IMG_ROOT = Path(__file__).resolve().parent.parent / "data" / "images"


def _load(relative_path: str, *, name: str | None = None) -> ImageTemplate:
    """从 autowsgr/data/images/ 加载图像模板。

    Parameters
    ----------
    relative_path:
        相对于 ``autowsgr/data/images/`` 的路径。
    name:
        模板名称。默认使用文件名 (不含扩展名)。
    """
    return ImageTemplate.from_file(_IMG_ROOT / relative_path, name=name)


# ═══════════════════════════════════════════════════════════════════════════════
# 延迟加载装饰器
# ═══════════════════════════════════════════════════════════════════════════════


class _LazyTemplate:
    """延迟加载的图像模板描述符。

    首次访问时加载图像文件，之后缓存结果。
    """

    def __init__(self, relative_path: str, name: str | None = None) -> None:
        self._path = relative_path
        self._name = name
        self._template: ImageTemplate | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr_name = name
        if self._name is None:
            self._name = name

    def __get__(self, obj: object, objtype: type | None = None) -> ImageTemplate:
        if self._template is None:
            self._template = _load(self._path, name=self._name)
        return self._template


# ═══════════════════════════════════════════════════════════════════════════════
# 模板分类
# ═══════════════════════════════════════════════════════════════════════════════


class Cook:
    """食堂 (做菜) 相关模板。"""

    COOK_BUTTON = _LazyTemplate("cook/cook_button.png", "cook_button")
    """做菜按钮。"""

    HAVE_COOK = _LazyTemplate("cook/have_cook.png", "have_cook")
    """「效果正在生效」弹窗。"""

    NO_TIMES = _LazyTemplate("cook/no_times.png", "no_times")
    """「今日用餐次数已用尽」弹窗。"""


class GameUI:
    """通用游戏 UI 模板。"""

    REWARD_COLLECT_ALL = _LazyTemplate("reward/collect_all.png", "reward_collect_all")
    """任务一键领取按钮。"""

    REWARD_COLLECT = _LazyTemplate("reward/collect.png", "reward_collect")
    """任务单个领取按钮。"""


class Confirm:
    """确认弹窗模板。"""

    CONFIRM_1 = _LazyTemplate("common/confirm_1.png", "confirm_1")
    CONFIRM_2 = _LazyTemplate("common/confirm_2.png", "confirm_2")
    CONFIRM_3 = _LazyTemplate("common/confirm_3.png", "confirm_3")
    CONFIRM_4 = _LazyTemplate("common/confirm_4.png", "confirm_4")
    CONFIRM_5 = _LazyTemplate("common/confirm_5.png", "confirm_5")
    CONFIRM_6 = _LazyTemplate("common/confirm_6.png", "confirm_6")

    @classmethod
    def all(cls) -> list[ImageTemplate]:
        """所有确认弹窗模板列表。"""
        return [
            cls.CONFIRM_1,
            cls.CONFIRM_2,
            cls.CONFIRM_3,
            cls.CONFIRM_4,
            cls.CONFIRM_5,
            cls.CONFIRM_6,
        ]


class Build:
    """建造相关模板。"""

    # ── 舰船建造 ──
    SHIP_START = _LazyTemplate("build/ship_start.png", "ship_build_start")
    """开始建造按钮 (舰船)。"""

    SHIP_COMPLETE = _LazyTemplate("build/ship_complete.png", "ship_build_complete")
    """建造完成标志 (舰船)。"""

    SHIP_FAST = _LazyTemplate("build/ship_fast.png", "ship_build_fast")
    """快速建造按钮 (舰船)。"""

    SHIP_FULL_DEPOT = _LazyTemplate("build/ship_full_depot.png", "ship_full_depot")
    """船坞已满提示 (舰船)。"""

    # ── 装备开发 ──
    EQUIP_START = _LazyTemplate("build/equip_start.png", "equip_build_start")
    """开始开发按钮 (装备)。"""

    EQUIP_COMPLETE = _LazyTemplate("build/equip_complete.png", "equip_build_complete")
    """开发完成标志 (装备)。"""

    EQUIP_FAST = _LazyTemplate("build/equip_fast.png", "equip_build_fast")
    """快速开发按钮 (装备)。"""

    EQUIP_FULL_DEPOT = _LazyTemplate("build/equip_full_depot.png", "equip_full_depot")
    """仓库已满提示 (装备)。"""

    # ── 资源页面 ──
    RESOURCE = _LazyTemplate("build/resource.png", "build_resource")
    """资源选择页面标志。"""


class Fight:
    """战斗相关模板。"""

    NIGHT_BATTLE = _LazyTemplate("combat/night_battle.png", "night_battle")
    """夜战确认按钮。"""

    RESULT_PAGE = _LazyTemplate("combat/result_page.png", "result_page")
    """战果页面标志。"""

    @staticmethod
    @lru_cache(maxsize=1)
    def result_pages() -> list[ImageTemplate]:
        """战果页面模板列表。"""
        return [_load("combat/result_page.png", name="result_page")]


class FightResult:
    """战斗结果评级模板。"""

    SS = _LazyTemplate("combat/result/ss.png", "result_SS")
    S = _LazyTemplate("combat/result/s.png", "result_S")
    A = _LazyTemplate("combat/result/a.png", "result_A")
    B = _LazyTemplate("combat/result/b.png", "result_B")
    C = _LazyTemplate("combat/result/c.png", "result_C")
    D = _LazyTemplate("combat/result/d.png", "result_D")
    LOOT = _LazyTemplate("combat/result/loot.png", "result_LOOT")

    @classmethod
    def all_grades(cls) -> list[ImageTemplate]:
        """所有评级模板列表（SS→D，不含 LOOT）。"""
        return [cls.SS, cls.S, cls.A, cls.B, cls.C, cls.D]


class ChooseShip:
    """选船页面模板。"""

    PAGE_1 = _LazyTemplate("choose_ship/tab_1.png", "choose_ship_1")
    PAGE_2 = _LazyTemplate("choose_ship/tab_2.png", "choose_ship_2")
    PAGE_3 = _LazyTemplate("choose_ship/tab_3.png", "choose_ship_3")
    PAGE_4 = _LazyTemplate("choose_ship/tab_4.png", "choose_ship_4")


class Symbol:
    """符号/标志模板。"""

    GET_SHIP = _LazyTemplate("combat/get_ship.png", "symbol_get_ship")
    """获取舰船标志。"""

    GET_ITEM = _LazyTemplate("combat/get_item.png", "symbol_get_item")
    """获取物品标志。"""


class BackButton:
    """回退按钮模板。"""

    @staticmethod
    @lru_cache(maxsize=1)
    def all() -> list[ImageTemplate]:
        """所有回退按钮模板。"""
        return [_load(f"common/back_{i}.png", name=f"back_{i}") for i in range(1, 9)]


class Error:
    """错误/网络问题模板。"""

    BAD_NETWORK_1 = _LazyTemplate("error/bad_network_1.png", "bad_network_1")
    BAD_NETWORK_2 = _LazyTemplate("error/bad_network_2.png", "bad_network_2")
    NETWORK_RETRY = _LazyTemplate("error/network_retry.png", "network_retry")
    REMOTE_LOGIN = _LazyTemplate("error/remote_login.png", "remote_login")
    REMOTE_LOGIN_CONFIRM = _LazyTemplate(
        "error/remote_login_confirm.png", "remote_login_confirm"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 顶层容器 — 统一入口
# ═══════════════════════════════════════════════════════════════════════════════


class Templates:
    """图像模板统一入口。

    Usage::

        from autowsgr.ops.image_resources import Templates

        Templates.Cook.COOK_BUTTON    # 食堂做菜按钮
        Templates.Build.SHIP_COMPLETE # 舰船建造完成
        Templates.GameUI.REWARD_COLLECT_ALL  # 一键领取
        Templates.Confirm.all()       # 所有确认弹窗

    所有模板均为延迟加载，首次访问时才读取图像文件。
    """

    Cook = Cook
    GameUI = GameUI
    Confirm = Confirm
    Build = Build
    Fight = Fight
    FightResult = FightResult
    ChooseShip = ChooseShip
    Symbol = Symbol
    BackButton = BackButton
    Error = Error
