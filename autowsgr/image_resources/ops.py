"""业务操作图像模板。

食堂、建造、确认弹窗、错误提示等模板。
所有模板对应 ``autowsgr/data/images/`` 下的 PNG 文件。
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from autowsgr.image_resources._lazy import LazyTemplate, load_template
from autowsgr.image_resources.pages import Bath, CommonPage, Decisive, MainPage


if TYPE_CHECKING:
    from autowsgr.vision import ImageTemplate


# ═══════════════════════════════════════════════════════════════════════════════
# 分类模板
# ═══════════════════════════════════════════════════════════════════════════════


class Cook:
    """食堂 (做菜) 相关模板。"""

    COOK_BUTTON = LazyTemplate('cook/cook_button_540p.png', 'cook_button')
    HAVE_COOK = LazyTemplate('cook/have_cook_540p.png', 'have_cook')
    NO_TIMES = LazyTemplate('cook/no_times_540p.png', 'no_times')


class GameUI:
    """通用游戏 UI 模板。"""

    REWARD_COLLECT_ALL = LazyTemplate('reward/collect_all_540p.png', 'reward_collect_all')
    REWARD_COLLECT = LazyTemplate('reward/collect_540p.png', 'reward_collect')


class Confirm:
    """确认弹窗模板。"""

    CONFIRM_1 = LazyTemplate('common/confirm_1_540p.png', 'confirm_1')
    CONFIRM_2 = LazyTemplate('common/confirm_2_540p.png', 'confirm_2')
    CONFIRM_3 = LazyTemplate('common/confirm_3_540p.png', 'confirm_3')
    CONFIRM_4 = LazyTemplate('common/confirm_4_540p.png', 'confirm_4')
    CONFIRM_5 = LazyTemplate('common/confirm_5_540p.png', 'confirm_5')

    @classmethod
    def all(cls) -> list[ImageTemplate]:
        """所有确认弹窗模板列表。"""
        return [cls.CONFIRM_1, cls.CONFIRM_2, cls.CONFIRM_3, cls.CONFIRM_4, cls.CONFIRM_5]


class Build:
    """建造相关模板。"""

    # ── 舰船建造 ──
    SHIP_START = LazyTemplate('build/ship_start_540p.png', 'ship_build_start')
    SHIP_COMPLETE = LazyTemplate('build/ship_complete_540p.png', 'ship_build_complete')
    SHIP_FAST = LazyTemplate('build/ship_fast_540p.png', 'ship_build_fast')
    SHIP_FULL_DEPOT = LazyTemplate('build/ship_full_depot_540p.png', 'ship_full_depot')

    # ── 装备开发 ──
    EQUIP_START = LazyTemplate('build/equip_start_540p.png', 'equip_build_start')
    EQUIP_COMPLETE = LazyTemplate('build/equip_complete_540p.png', 'equip_build_complete')
    EQUIP_FAST = LazyTemplate('build/equip_fast_540p.png', 'equip_build_fast')
    EQUIP_FULL_DEPOT = LazyTemplate('build/equip_full_depot_540p.png', 'equip_full_depot')

    # ── 资源页面 ──
    RESOURCE = LazyTemplate('build/resource_540p.png', 'build_resource')


class Fight:
    """战斗相关模板 (ops 侧复用)。"""

    NIGHT_BATTLE = LazyTemplate('combat/night_battle_540p.png', 'night_battle')


class FightResult:
    """战斗结果评级模板。"""

    SS = LazyTemplate('combat/result/ss_540p.png', 'result_SS')
    S = LazyTemplate('combat/result/s_540p.png', 'result_S')
    A = LazyTemplate('combat/result/a_540p.png', 'result_A')
    B = LazyTemplate('combat/result/b_540p.png', 'result_B')
    C = LazyTemplate('combat/result/c_540p.png', 'result_C')
    D = LazyTemplate('combat/result/d_540p.png', 'result_D')
    LOOT = LazyTemplate('combat/result/loot_540p.png', 'result_LOOT')

    @classmethod
    def all_grades(cls) -> list[ImageTemplate]:
        return [cls.SS, cls.S, cls.A, cls.B, cls.C, cls.D]


class ChooseShip:
    """选船页面模板。"""

    PAGE_1 = LazyTemplate('choose_ship/tab_1_540p.png', 'choose_ship_1')
    PAGE_2 = LazyTemplate('choose_ship/tab_2_540p.png', 'choose_ship_2')
    PAGE_3 = LazyTemplate('choose_ship/tab_3_540p.png', 'choose_ship_3')
    PAGE_4 = LazyTemplate('choose_ship/tab_4_540p.png', 'choose_ship_4')


class Symbol:
    """符号/标志模板。"""

    GET_SHIP = LazyTemplate('combat/get_ship_540p.png', 'symbol_get_ship')
    GET_ITEM = LazyTemplate('combat/get_item_540p.png', 'symbol_get_item')
    # MVP 徽章 (result_page_540p): 战果/经验结算页必有且不被遮挡, 比
    # "点击继续" 文字 (result_540p, 被舰船立绘遮挡致分数波动) 稳定
    CLICK_TO_CONTINUE = LazyTemplate('combat/result_page_540p.png', 'click_to_continue')


class BackButton:
    """回退按钮模板。"""

    @staticmethod
    @lru_cache(maxsize=1)
    def all() -> list[ImageTemplate]:
        return [load_template(f'common/back_{i}_540p.png', name=f'back_{i}') for i in range(1, 9)]


class Error:
    """错误/网络问题模板。"""

    BAD_NETWORK_1 = LazyTemplate('error/bad_network_1_540p.png', 'bad_network_1')
    BAD_NETWORK_2 = LazyTemplate('error/bad_network_2_540p.png', 'bad_network_2')
    NETWORK_RETRY = LazyTemplate('error/network_retry_540p.png', 'network_retry')
    REMOTE_LOGIN = LazyTemplate('error/remote_login_540p.png', 'remote_login')
    REMOTE_LOGIN_CONFIRM = LazyTemplate(
        'error/remote_login_confirm_540p.png', 'remote_login_confirm'
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 顶层容器
# ═══════════════════════════════════════════════════════════════════════════════


# 页面/浮层识别模板已迁入 pages/ 子包 (CommonPage / MainPage / Decisive / Bath)。
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
    Page = CommonPage
    MainPage = MainPage
    Bath = Bath
