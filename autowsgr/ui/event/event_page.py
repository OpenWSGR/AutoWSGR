"""活动地图页面 UI 控制器。

活动地图页面在主页面点击活动入口后进入。
页面上显示活动地图节点，玩家选择节点后点击出击按钮进入出征准备。

使用方式::

    from autowsgr.ui.event.event_page import BaseEventPage

    page = BaseEventPage(ctx)

    # 页面识别
    screen = ctrl.screenshot()
    if BaseEventPage.is_current_page(screen):
        page.start_fight('E1')
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

from autowsgr.infra.exceptions import ActionFailedError
from autowsgr.infra.logger import get_logger
from autowsgr.types import PageName
from autowsgr.ui.utils import click_and_wait_for_page
from autowsgr.vision import (
    Color,
    ImageChecker,
    ImageMatchDetail,
    OverlayChecker,
    PageMatch,
    PixelChecker,
)


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.context import GameContext
    from autowsgr.vision import ImageTemplate

_log = get_logger('ui')


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别模板 (活动标题图)
# ═══════════════════════════════════════════════════════════════════════════════


@lru_cache(maxsize=1)
def _get_fight_button_templates() -> list[ImageTemplate]:
    """关卡详情浮层的"出击"按钮模板。

    活动浮层 (点击地图节点后弹出的关卡详情) 右下角的出击按钮。该浮层是模态,
    浮层在 = 按钮必在, 故**按钮可见即浮层态**的充分判据 (战斗回港后活动页
    常直接落在此浮层态)。按钮是流程必按控件, 逐活动截一张 (与浮层整体外观
    相比, 按钮样式跨活动差异小), 且匹配位置 ``center`` 可直接用作点击坐标,
    布局微调也无需改坐标常量。
    """
    from autowsgr.image_resources._lazy import load_template

    return [
        load_template('event/fight_button_20260730_540p.png', name='fight_button'),
    ]


@lru_cache(maxsize=1)
def _get_event_title_templates() -> list[ImageTemplate]:
    """活动地图页面标题图模板。

    每个活动地图选择页顶部都有活动名标题(如"激斗漩涡"), 仅在该页面显示。
    标题图易获取 (从活动页截图裁标题即可), 且对不同活动深/浅色主题均鲁棒。
    匹配引擎按 ``source_resolution`` 自动缩放, 540p/720p 模板可共存;
    页面识别时 ``find_any`` 命中任一即认定为活动地图页面。
    """
    from autowsgr.image_resources._lazy import load_template

    return [
        load_template(
            'event/event_title_20260730_540p.png',
            name='event_title_20260730',
            source_resolution=(960, 540),
        ),
    ]


# ── 难度切换按钮图标模板 (延迟加载) ──────────────────────────────────────
# 跨活动通用, 迁移自 classic event/common (easy1/2, hard1/2)。classic 把所有
# 截图 cv2.resize 到 960x540 后匹配, 故这些 540p 模板的 source_resolution 用
# 默认 (960,540), 引擎自动缩放到实际屏幕分辨率 (如 1280x720)。
# 语义: 看到"困难模式"按钮 → 当前简单; 看到"简单模式"按钮 → 当前困难;
#       都没看到 (且在活动页) → 简单未通关/未解锁困难 → 一定是简单。


@lru_cache(maxsize=1)
def _get_difficulty_hard_templates() -> list[ImageTemplate]:
    """ "困难模式" 难度切换按钮图标。

    活动地图选择页左下角, 当前为**简单**难度时显示 (点击可切到困难)。
    命中 → 当前简单。
    """
    from autowsgr.image_resources._lazy import load_template

    return [
        load_template('event/difficulty_hard_540p_1.png', name='diff_hard1'),
        load_template('event/difficulty_hard_540p_2.png', name='diff_hard2'),
    ]


@lru_cache(maxsize=1)
def _get_difficulty_easy_templates() -> list[ImageTemplate]:
    """ "简单模式" 难度切换按钮图标。

    当前为**困难**难度时显示 (点击可切回简单)。命中 → 当前困难。
    """
    from autowsgr.image_resources._lazy import load_template

    return [
        load_template('event/difficulty_easy_540p_1.png', name='diff_easy1'),
        load_template('event/difficulty_easy_540p_2.png', name='diff_easy2'),
    ]


# ── 节点详情浮层检测 ─────────────────────────────────────────────────────
# 点击地图节点后弹出关卡详情浮层 (均匀蒙版压暗整页)。其检测用 OverlayChecker
# 双帧浮层检测 (见 BaseEventPage._enter_node), 不再用"出击准备"按钮模板——
# 浮层外观随活动主题变, 按钮模板需逐活动重截, 浮层检测则与新活动无关。


NODE_POSITIONS = {
    1: (0.1789, 0.1986),
    2: (0.3914, 0.2528),
    3: (0.9086, 0.2875),
    4: (0.2891, 0.6292),
    5: (0.5367, 0.4028),
    6: (0.6352, 0.6653),
}
"""活动地图选择界面的地图入口坐标 (选 E1~E6 / H1~H6 中的哪张地图)。

缺省布局适用于多数活动; 布局不同的活动在 :data:`NODE_POSITIONS_BY_EVENT` 覆盖。
"""

# 各活动专属地图入口坐标 (照搬 classic 各活动子类的 NODE_POSITION)
# 激斗漩涡 (20260730): 3 行 2 列布局
NODE_POSITIONS_BY_EVENT: dict[str, dict[int, tuple[float, float]]] = {
    '20260730': {
        1: (0.1771, 0.3148),
        2: (0.1740, 0.7259),
        3: (0.5010, 0.2981),
        4: (0.4906, 0.7463),
        5: (0.8135, 0.2944),
        6: (0.8125, 0.7463),
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# 坐标常量
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.0273, 0.0558)
"""返回按钮坐标 (活动地图左上角)。"""

CLICK_FIGHT_BUTTON: tuple[float, float] = (0.8276, 0.8426)
"""出击按钮坐标 (活动地图右下角，选择节点后出现)。"""

CLICK_CLOSE_NODE_OVERLAY: tuple[float, float] = (0.95, 0.14)
"""关卡详情浮层的红色 X 关闭按钮坐标 (浮层右上角)。

点击地图节点后弹出关卡详情浮层, 其右上角有红色 X 关闭按钮。该浮层为模态,
会拦截屏幕其他点击 (含左上返回箭头), 故 :meth:`go_back` 返回主页前需先点此 X
关闭浮层, 再点返回箭头逐层退出 (照搬 classic ``go_main_page`` 循环点返回键)。
坐标按活动地图布局校准: 浮层右下角出击按钮约在 (0.83, 0.84), 红色 X 在浮层
右上角 (屏幕右上, y 略低于顶部)。
"""

CLICK_DIFFICULTY: tuple[float, float] = (0.12, 0.90)
"""难度切换按钮点击坐标。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 入口选择 (alpha / beta)
# ═══════════════════════════════════════════════════════════════════════════════

ENTRANCE_ALPHA_PROBE: tuple[float, float] = (0.8271, 0.5778)
"""入口 alpha 探测点。"""

ENTRANCE_ALPHA_COLOR = Color.of(249, 146, 37)
"""alpha 入口选中时的颜色特征。"""

# 入口切换点击坐标 (照搬 classic even20260730 已验证值: 绝对坐标
# [(797,369), (795,317)] @960x540 → 相对坐标)
CLICK_ENTRANCE_ALPHA: tuple[float, float] = (0.8302, 0.6833)
"""α 入口点击坐标。"""
CLICK_ENTRANCE_BETA: tuple[float, float] = (0.8281, 0.5870)
"""β 入口点击坐标。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class BaseEventPage:
    """活动地图页面控制器。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。
    node_positions:
        节点坐标映射 ``{map_id: (x, y)}``，
        坐标为相对坐标 (0.0~1.0)。
    """

    def __init__(
        self,
        ctx: GameContext,
        event_name: str | None = None,
    ) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._event_name = event_name

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> PageMatch:
        """判断截图是否为活动地图页面 (含浮层态)。

        三层锚点, 按优先级:
        1. **出击按钮**可见 → 浮层态 (关卡详情浮层是模态, 浮层在按钮必在)。
           战斗回港后活动页常直接落在浮层态, 必须算"在活动页", 否则战后
           goto_page(EVENT_MAP) 会导航失败。
        2. **难度切换图标**可见 → 干净活动页。
        3. **活动标题**命中 → 兜底 (仅证明"在活动域", 不区分浮层与否)。

        出击按钮/难度图标是流程必交互控件, 按钮样式跨活动差异小; 标题图
        逐活动重截但仅作兜底, 缺失时新活动仍可识别 (前两层已覆盖)。
        返回带置信度的 PageMatch, 供候选集排序。
        """
        name = str(PageName.EVENT_MAP)
        button = BaseEventPage._fight_button_detail(screen)
        if button is not None:
            return PageMatch(name=name, matched=True, score=button.confidence)
        icon_state = BaseEventPage._difficulty_icon_state(screen)
        if icon_state is not None:
            return PageMatch(name=name, matched=True, score=0.9)
        title = ImageChecker.find_any(screen, _get_event_title_templates(), confidence=0.8)
        if title is not None:
            return PageMatch(name=name, matched=True, score=title.confidence * 0.95)
        return PageMatch(name=name, matched=False, score=0.0)

    @staticmethod
    def _fight_button_detail(screen: np.ndarray) -> ImageMatchDetail | None:
        """查找出击按钮 (浮层态锚点), 返回匹配详情 (``None`` = 浮层未开)。"""
        return ImageChecker.find_any(screen, _get_fight_button_templates(), confidence=0.8)

    # ── 节点选择 ──────────────────────────────────────────────────────────
    def _enter_node(self, node_id: int) -> None:
        """点击选择地图节点, 等待节点详情浮层弹出。

        通过**出击按钮出现**确认节点选择成功: 关卡详情浮层是模态, 浮层在 =
        其右下角的出击按钮必在 (见 :func:`_get_fight_button_templates`)。
        单帧模板匹配即可判定, 不依赖点击前后的时序 (此前用双帧浮层检测,
        需要点击前截干净参照帧, 时序不好会误判)。

        Parameters
        ----------
        node_id:
            节点编号, 通常为 1~6。
        """
        positions = NODE_POSITIONS_BY_EVENT.get(self._event_name, NODE_POSITIONS)
        x, y = positions[node_id]
        _log.debug('[UI] 活动地图: 选择节点 {}', node_id)
        self._ctrl.click(x, y)
        for _ in range(10):
            after = self._ctrl.screenshot()
            if self._fight_button_detail(after) is not None:
                break  # 出击按钮出现 = 节点详情浮层弹出 = 选择成功
            time.sleep(0.25)
        else:
            raise ActionFailedError(f'活动地图: 选择节点 {node_id} 失败，未出现节点详情浮层')

    # ── 出击 ──────────────────────────────────────────────────────────────

    def start_fight(
        self, map: str, entrance: Literal['alpha', 'beta'] | None = None, skip_check: bool = False
    ) -> None:
        """点击出击按钮，等待进入出征准备页面。"""
        # map 为 H1, E1 等
        if not skip_check:
            if (
                len(map) != 2
                or map[0] not in ('H', 'E')
                or not map[1].isdigit()
                or int(map[1]) not in NODE_POSITIONS
            ):
                raise ValueError(f'无效的地图标识: {map}')
            if entrance not in ('alpha', 'beta', None):
                raise ValueError(f'无效的入口标识: {entrance}')
            difficulty, node_id = map[0], int(map[1])
            self.ensure_no_overlay()
            self._change_difficulty(difficulty)
            self._enter_node(node_id)
            if entrance is not None:
                self._select_entrance(entrance)

        from autowsgr.ui.battle.preparation import BattlePreparationPage

        # 优先点击模板匹配位置 (跨活动布局变化免疫), 匹配失败回退固定坐标
        screen = self._ctrl.screenshot()
        detail = self._fight_button_detail(screen)
        if detail is not None:
            coord = detail.center
        else:
            coord = CLICK_FIGHT_BUTTON
            _log.warning('[UI] 活动地图: 未匹配到出击按钮, 回退固定坐标点击')
        _log.debug('[UI] 活动地图: 点击出击')
        click_and_wait_for_page(
            self._ctrl,
            click_coord=coord,
            checker=BattlePreparationPage.is_current_page,
            source=PageName.EVENT_MAP,
            target=PageName.BATTLE_PREP,
        )

    # ── 难度切换 ──────────────────────────────────────────────────────────

    def _get_difficulty(self) -> str:
        """获取当前难度。

        用难度切换按钮图标识别 (跨活动通用, 迁移自 classic event/common):

        - 看到 "困难模式" 切换按钮 → 当前为简单 (``"E"``)
        - 看到 "简单模式" 切换按钮 → 当前为困难 (``"H"``)
        - 都没检测到且仍在活动页面 → 简单未通关/未解锁困难, 当前一定是简单
          (``"E"``)

        Returns
        -------
        str
            ``"H"`` (困难) 或 ``"E"`` (简单)。
        """
        screen = self._ctrl.screenshot()
        icon_state = self._difficulty_icon_state(screen)
        if icon_state is not None:
            return icon_state
        if self.is_current_page(screen):
            _log.info('[UI] 活动地图: 未检测到难度切换图标, 判定为简单 (可能简单未通关/未解锁困难)')
            return 'E'
        raise ActionFailedError('活动地图: 无法识别当前难度且不在活动页面')

    @staticmethod
    def _difficulty_icon_state(screen: np.ndarray) -> str | None:
        """从截图判定难度切换图标状态。

        Returns
        -------
        str | None
            ``"E"`` (看到"切困难"按钮, 当前简单) / ``"H"`` (看到"切简单"按钮,
            当前困难) / ``None`` (图标不可见 — 被浮层遮挡或不在活动页)。
        """
        if (
            ImageChecker.find_any(screen, _get_difficulty_hard_templates(), confidence=0.8)
            is not None
        ):
            return 'E'
        if (
            ImageChecker.find_any(screen, _get_difficulty_easy_templates(), confidence=0.8)
            is not None
        ):
            return 'H'
        return None

    def ensure_no_overlay(self) -> None:
        """确保活动地图页处于干净态 (无关卡详情浮层)。

        战斗回港后, 活动页常直接落在关卡详情浮层态 (战后 UI 流转跳过出征
        准备页直接回浮层)。浮层是模态, 会拦截难度切换/节点选择的点击, 需先
        关闭才能继续选关。

        判定与清理: **出击按钮可见 = 浮层在** (模态浮层在按钮必在) → 点红色
        X 关闭, 以按钮消失确认; 按钮不可见 → 已是干净态, 直接返回。
        """
        screen = self._ctrl.screenshot()
        if self._fight_button_detail(screen) is None:
            return
        for _ in range(3):
            self._ctrl.click(*CLICK_CLOSE_NODE_OVERLAY)
            time.sleep(0.6)
            screen = self._ctrl.screenshot()
            if self._fight_button_detail(screen) is None:
                _log.info('[UI] 活动地图: 已关闭残留关卡浮层')
                return
        _log.warning('[UI] 活动地图: 关卡浮层点击 3 次未关闭')

    def _change_difficulty(self, target: str) -> None:
        """切换难度到目标。

        Parameters
        ----------
        target:
            ``"H"`` 或 ``"E"``。
        """
        current = self._get_difficulty()
        if current == target:
            _log.debug('[UI] 活动地图: 当前已是 {} 难度', target)
            return

        _log.info('[UI] 活动地图: 切换难度 {} -> {}', current, target)
        self._ctrl.click(*CLICK_DIFFICULTY)
        time.sleep(1.0)

        # 验证切换成功
        new_diff = self._get_difficulty()
        if new_diff != target:
            _log.warning(
                '[UI] 活动地图: 难度切换验证失败 (期望 {}, 实际 {}), 重试',
                target,
                new_diff,
            )
            self._ctrl.click(*CLICK_DIFFICULTY)
            time.sleep(1.0)

    # ── 入口选择 (alpha/beta) ─────────────────────────────────────────────

    def _is_alpha_entrance(self) -> bool:
        """检测当前是否为 alpha 入口。"""
        screen = self._ctrl.screenshot()
        x, y = ENTRANCE_ALPHA_PROBE
        pixel = PixelChecker.get_pixel(screen, x, y)
        return pixel.near(ENTRANCE_ALPHA_COLOR, 40.0)

    def _select_entrance(self, entrance: Literal['alpha', 'beta']) -> None:
        """切换到目标 α/β 入口; 与当前一致则跳过。

        入口切换坐标照搬 classic even20260730 (已实机验证)。
        """
        want_alpha = entrance == 'alpha'
        if self._is_alpha_entrance() == want_alpha:
            _log.debug('[UI] 活动地图: 入口已为 {}, 无需切换', entrance)
            return
        coord = CLICK_ENTRANCE_ALPHA if want_alpha else CLICK_ENTRANCE_BETA
        _log.info('[UI] 活动地图: 切换入口 -> {}', entrance)
        self._ctrl.click(*coord)
        time.sleep(0.3)

    # ── 导航 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """返回主页面。

        循环点击返回箭头逐层退出直到主页面 (照搬 classic ``go_main_page`` 的"不断
        点返回键")。战斗结束回港后, 活动地图页上常浮着关卡详情浮层 (红色 X 关闭),
        该浮层为模态, 会拦截左上返回箭头的点击——直接点一次 ``CLICK_BACK`` 会被
        浮层吸收而无效。

        用**变化检测**判断返回是否被浮层吸收: 点返回后截图对比, 若前后几乎无变化
        (:meth:`OverlayChecker.page_changed` 返回 False) → 点击被模态浮层吸收 →
        点红色 X 关闭浮层, 下轮再试。这是静态/反向场景 (进入时可能已是浮层态,
        无干净 before 供双帧浮层检测), 变化检测比浮层检测更直接。

        **防连点过冲**: 点一次返回后用一个轮询窗口 (~3s) 等主页出现, 期间**不重复
        点返回**。画面切换有滞后, 若点完立即下一轮再点, 第二次返回会落到已切到的
        主页左上角, 误开"提督信息"浮层 (该浮层不遮主页识别元素 → 识别仍判主页 →
        后续点击错乱)。只有"点了返回但画面完全静止"(浮层吸收) 才点 X 关浮层。
        """
        from autowsgr.ui.main_page import MainPage
        from autowsgr.ui.utils import NavigationError

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            before = self._ctrl.screenshot()
            if MainPage.is_current_page(before):
                _log.info('[UI] 活动地图 -> 已到达主页面')
                return
            self._ctrl.click(*CLICK_BACK)
            # 点一次返回后轮询等主页——期间不重复点返回, 防滞后连点过冲 (见 docstring)
            absorbed = False
            wait_until = time.monotonic() + 3.0
            while time.monotonic() < wait_until:
                time.sleep(0.3)
                after = self._ctrl.screenshot()
                if MainPage.is_current_page(after):
                    _log.info('[UI] 活动地图 -> 已到达主页面')
                    return
                if not OverlayChecker.page_changed(before, after):
                    absorbed = True  # 画面静止 = 点返回被模态浮层吸收
                    break
            if absorbed:
                _log.info('[UI] 活动地图: 返回被关卡浮层吸收, 点击红色 X 关闭')
                self._ctrl.click(*CLICK_CLOSE_NODE_OVERLAY)
                time.sleep(0.5)
            # 否则 (画面在变但 3s 内未到主页) → 外层循环重新评估
        raise NavigationError(
            '活动地图: 返回主页面超时 (浮层/返回点击未能逐层退出)',
            screen=self._ctrl.screenshot(),
        )
