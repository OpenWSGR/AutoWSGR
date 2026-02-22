"""业务操作图像模板。

食堂、建造、确认弹窗、错误提示等模板。
所有模板对应 ``autowsgr/data/images/`` 下的 PNG 文件。
"""

from __future__ import annotations

from functools import lru_cache

from autowsgr.image_resources._lazy import LazyTemplate, load_template
from autowsgr.vision import ImageTemplate


# ═══════════════════════════════════════════════════════════════════════════════
# 分类模板
# ═══════════════════════════════════════════════════════════════════════════════


class Cook:
    """食堂 (做菜) 相关模板。"""

    COOK_BUTTON = LazyTemplate("cook/cook_button.png", "cook_button")
    HAVE_COOK = LazyTemplate("cook/have_cook.png", "have_cook")
    NO_TIMES = LazyTemplate("cook/no_times.png", "no_times")


class GameUI:
    """通用游戏 UI 模板。"""

    REWARD_COLLECT_ALL = LazyTemplate("reward/collect_all.png", "reward_collect_all")
    REWARD_COLLECT = LazyTemplate("reward/collect.png", "reward_collect")


class Confirm:
    """确认弹窗模板。"""

    CONFIRM_1 = LazyTemplate("common/confirm_1.png", "confirm_1")
    CONFIRM_2 = LazyTemplate("common/confirm_2.png", "confirm_2")
    CONFIRM_3 = LazyTemplate("common/confirm_3.png", "confirm_3")
    CONFIRM_4 = LazyTemplate("common/confirm_4.png", "confirm_4")
    CONFIRM_5 = LazyTemplate("common/confirm_5.png", "confirm_5")
    CONFIRM_6 = LazyTemplate("common/confirm_6.png", "confirm_6")

    @classmethod
    def all(cls) -> list[ImageTemplate]:
        """所有确认弹窗模板列表。"""
        return [
            cls.CONFIRM_1, cls.CONFIRM_2, cls.CONFIRM_3,
            cls.CONFIRM_4, cls.CONFIRM_5, cls.CONFIRM_6,
        ]


class Build:
    """建造相关模板。"""

    # ── 舰船建造 ──
    SHIP_START = LazyTemplate("build/ship_start.png", "ship_build_start")
    SHIP_COMPLETE = LazyTemplate("build/ship_complete.png", "ship_build_complete")
    SHIP_FAST = LazyTemplate("build/ship_fast.png", "ship_build_fast")
    SHIP_FULL_DEPOT = LazyTemplate("build/ship_full_depot.png", "ship_full_depot")

    # ── 装备开发 ──
    EQUIP_START = LazyTemplate("build/equip_start.png", "equip_build_start")
    EQUIP_COMPLETE = LazyTemplate("build/equip_complete.png", "equip_build_complete")
    EQUIP_FAST = LazyTemplate("build/equip_fast.png", "equip_build_fast")
    EQUIP_FULL_DEPOT = LazyTemplate("build/equip_full_depot.png", "equip_full_depot")

    # ── 资源页面 ──
    RESOURCE = LazyTemplate("build/resource.png", "build_resource")


class Fight:
    """战斗相关模板 (ops 侧复用)。"""

    NIGHT_BATTLE = LazyTemplate("combat/night_battle.png", "night_battle")
    RESULT_PAGE = LazyTemplate("combat/result_page.png", "result_page")

    @staticmethod
    @lru_cache(maxsize=1)
    def result_pages() -> list[ImageTemplate]:
        return [load_template("combat/result_page.png", name="result_page")]


class FightResult:
    """战斗结果评级模板。"""

    SS = LazyTemplate("combat/result/ss.png", "result_SS")
    S = LazyTemplate("combat/result/s.png", "result_S")
    A = LazyTemplate("combat/result/a.png", "result_A")
    B = LazyTemplate("combat/result/b.png", "result_B")
    C = LazyTemplate("combat/result/c.png", "result_C")
    D = LazyTemplate("combat/result/d.png", "result_D")
    LOOT = LazyTemplate("combat/result/loot.png", "result_LOOT")

    @classmethod
    def all_grades(cls) -> list[ImageTemplate]:
        return [cls.SS, cls.S, cls.A, cls.B, cls.C, cls.D]


class ChooseShip:
    """选船页面模板。"""

    PAGE_1 = LazyTemplate("choose_ship/tab_1.png", "choose_ship_1")
    PAGE_2 = LazyTemplate("choose_ship/tab_2.png", "choose_ship_2")
    PAGE_3 = LazyTemplate("choose_ship/tab_3.png", "choose_ship_3")
    PAGE_4 = LazyTemplate("choose_ship/tab_4.png", "choose_ship_4")


class Symbol:
    """符号/标志模板。"""

    GET_SHIP = LazyTemplate("combat/get_ship.png", "symbol_get_ship")
    GET_ITEM = LazyTemplate("combat/get_item.png", "symbol_get_item")
    CLICK_TO_CONTINUE = LazyTemplate("combat/result.png", "click_to_continue")


class BackButton:
    """回退按钮模板。"""

    @staticmethod
    @lru_cache(maxsize=1)
    def all() -> list[ImageTemplate]:
        return [load_template(f"common/back_{i}.png", name=f"back_{i}") for i in range(1, 9)]


class Error:
    """错误/网络问题模板。"""

    BAD_NETWORK_1 = LazyTemplate("error/bad_network_1.png", "bad_network_1")
    BAD_NETWORK_2 = LazyTemplate("error/bad_network_2.png", "bad_network_2")
    NETWORK_RETRY = LazyTemplate("error/network_retry.png", "network_retry")
    REMOTE_LOGIN = LazyTemplate("error/remote_login.png", "remote_login")
    REMOTE_LOGIN_CONFIRM = LazyTemplate("error/remote_login_confirm.png", "remote_login_confirm")


# ═══════════════════════════════════════════════════════════════════════════════
# 顶层容器
# ═══════════════════════════════════════════════════════════════════════════════


class Decisive:
    """决战相关模板。"""

    USE_LAST_FLEET = LazyTemplate("decisive/use_last_fleet.png", "decisive_use_last_fleet")
    """"使用上次舰队" 确认按钮 — 进入已有进度的章节时弹出。"""


class Templates:
    """图像模板统一入口。

    Usage::

        from autowsgr.image_resources import Templates

        Templates.Cook.COOK_BUTTON
        Templates.Build.SHIP_COMPLETE
        Templates.Confirm.all()
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
    Decisive = Decisive
