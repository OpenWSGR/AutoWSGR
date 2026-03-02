"""活动地图页面 UI 控制器。

活动地图页面在主页面点击活动入口后进入。
页面上显示活动地图节点，玩家选择节点后点击出击按钮进入出征准备。

已完成

使用方式::

    from autowsgr.ui.event.event_map_page import EventMapPage

    page = EventMapPage(ctrl)

    # 页面识别
    screen = ctrl.screenshot()
    if EventMapPage.is_current_page(screen):
        page.select_node(3)
        page.start_fight()
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Literal

from autowsgr.infra.logger import get_logger
from autowsgr.types import PageName
from autowsgr.ui.page import click_and_wait_for_page, wait_for_page
from autowsgr.vision import (
    Color,
    CompositePixelSignature,
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.context import GameContext

_log = get_logger('ui')


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

BASE_PAGE_SIGNATURE = PixelSignature(
    name='event_map_page',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8422, 0.0500, (209, 211, 232), tolerance=30.0),
        PixelRule.of(0.9047, 0.0528, (217, 217, 225), tolerance=30.0),
        PixelRule.of(0.9352, 0.8861, (211, 208, 225), tolerance=30.0),
    ],
)

OVERLAY_SIGNATURE = PixelSignature(
    name='overlay',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.2672, 0.0889, (34, 143, 246), tolerance=30.0),
        PixelRule.of(0.7734, 0.8514, (29, 124, 214), tolerance=30.0),
        PixelRule.of(0.7719, 0.5917, (237, 237, 237), tolerance=30.0),
        PixelRule.of(0.6133, 0.8556, (212, 212, 212), tolerance=30.0),
    ],
)

#: 组合签名：基础页面 OR 浮层 — 只要任一匹配即认定为活动地图页面。
EVENT_MAP_COMPOSITE = CompositePixelSignature.any_of(
    'event_map_page',
    BASE_PAGE_SIGNATURE,
    OVERLAY_SIGNATURE,
)

#: 组合签名：基础页面 OR 浮层 — 只要任一匹配即认定为活动地图页面。
EVENT_MAP_COMPOSITE = CompositePixelSignature.any_of(
    'event_map_page',
    BASE_PAGE_SIGNATURE,
    OVERLAY_SIGNATURE,
)

NODE_POSITIONS = {
    1: (0.1789, 0.1986),
    2: (0.3914, 0.2528),
    3: (0.9086, 0.2875),
    4: (0.2891, 0.6292),
    5: (0.5367, 0.4028),
    6: (0.6352, 0.6653),
}

DIFFICULTY_EASY_SIGNATURE = PixelSignature(
    name='difficulty_easy',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1208, 0.9093, (106, 30, 30), tolerance=30.0),
    ],
)  # 难度切换标签为红色困难，则难度为简单；
DIFFICULTY_HARD_SIGNATURE = PixelSignature(
    name='difficulty_hard',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1208, 0.9093, (44, 66, 111), tolerance=30.0),
    ],
)  # 难度切换标签为蓝色简单，则难度为困难；

"""活动地图页面像素签名。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标常量
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.0273, 0.0558)
"""返回按钮坐标 (活动地图左上角)。"""

CLICK_FIGHT_BUTTON: tuple[float, float] = (0.8276, 0.8426)
"""出击按钮坐标 (活动地图右下角，选择节点后出现)。"""

CLICK_CLOSE_OVERLAY: tuple[float, float] = (0.95, 0.1)

CLICK_DIFFICULTY: tuple[float, float] = (0.12, 0.90)
"""难度切换按钮点击坐标。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 入口选择 (alpha / beta)
# ═══════════════════════════════════════════════════════════════════════════════

ENTRANCE_ALPHA_PROBE: tuple[float, float] = (0.8271, 0.5778)
"""入口 alpha 探测点。
"""

ENTRANCE_ALPHA_COLOR = Color.of(249, 146, 37)
"""alpha 入口选中时的颜色特征。"""


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
    ) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为活动地图页面。"""
        return PixelChecker.check_signature(screen, EVENT_MAP_COMPOSITE).matched

    # —— 悬浮窗检测 ─────────────────────────────────────────────────────────
    def _detect_overlay(self, screen: np.ndarray) -> bool:
        """检测截图中是否存在可消除的浮层（地图进入页）。"""
        result = PixelChecker.check_signature(screen, OVERLAY_SIGNATURE)
        return result.matched

    def _close_overlay(self) -> None:
        """点击浮层中的关闭按钮，返回地图基础页面。"""
        _log.info('[UI] 活动地图: 关闭进入页浮层')
        self._ctrl.click(*CLICK_CLOSE_OVERLAY)
        wait_for_page(self._ctrl, self.is_current_page, timeout=5.0)
        time.sleep(0.25)  # 等待页面稳定

    def _ensure_no_overlay(self) -> None:
        if self._detect_overlay(self._ctrl.screenshot()):
            self._close_overlay()

    # ── 节点选择 ──────────────────────────────────────────────────────────
    def _enter_node(self, node_id: int) -> None:
        """点击选择地图节点。

        Parameters
        ----------
        node_id:
            节点编号，通常为 1~6。
        """
        x, y = NODE_POSITIONS[node_id]
        _log.debug('[UI] 活动地图: 选择节点 {}', node_id)
        self._ctrl.click(x, y)
        for _ in range(10):
            # 检测到节点浮层即成功
            if self._detect_overlay(self._ctrl.screenshot()):
                break
            time.sleep(0.25)
        else:
            raise Exception(f'活动地图: 选择节点 {node_id} 失败，无法进入页面')

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
            self._change_difficulty(difficulty)
            self._enter_node(node_id)
            if entrance is not None:
                self._select_entrance(entrance)

        from autowsgr.ui.battle.preparation import BattlePreparationPage

        _log.debug('[UI] 活动地图: 点击出击')
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_FIGHT_BUTTON,
            checker=BattlePreparationPage.is_current_page,
            source=PageName.EVENT_MAP,
            target=PageName.BATTLE_PREP,
        )

    # ── 难度切换 ──────────────────────────────────────────────────────────

    def _get_difficulty(self) -> str:
        """获取当前难度。

        Returns
        -------
        str
            ``"H"`` (困难) 或 ``"E"`` (简单)。
        """
        if PixelChecker.check_signature(self._ctrl.screenshot(), DIFFICULTY_HARD_SIGNATURE).matched:
            return 'H'
        elif PixelChecker.check_signature(
            self._ctrl.screenshot(), DIFFICULTY_EASY_SIGNATURE
        ).matched:
            return 'E'
        raise Exception('活动地图: 无法识别当前难度')

    def _change_difficulty(self, target: str) -> None:
        """切换难度到目标。

        Parameters
        ----------
        target:
            ``"H"`` 或 ``"E"``。
        """
        self._ensure_no_overlay()
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
        # 选择入口
        pass

    # ── 导航 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """返回主页面。"""
        from autowsgr.ui.main_page import MainPage

        _log.info('[UI] 活动地图 -> 主页面')
        self._ensure_no_overlay()
        time.sleep(0.5)
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=MainPage.is_current_page,
            source=PageName.EVENT_MAP,
            target=PageName.MAIN,
        )
