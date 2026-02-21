"""建造页面 UI 控制器。

已完成，需测试

覆盖游戏 **建造** 页面及其标签组 (建造/解体/开发/废弃) 的交互。

页面入口:
    主页面 → 侧边栏 → 建造

标签组:
    建造/解体/开发/废弃 四个标签共享相同的顶部导航栏。
    切换标签不会离开此页面组，只是改变内容区域。

坐标体系:
    所有坐标为相对值 (0.0–1.0)。

使用方式::

    from autowsgr.ui.build_page import BuildPage, BuildTab

    page = BuildPage(ctrl)
    page.switch_tab(BuildTab.DEVELOP)
    page.go_back()
"""

from __future__ import annotations

import enum
import time

import numpy as np
from loguru import logger

from autowsgr.emulator import AndroidController
from autowsgr.types import PageName
from autowsgr.image_resources import Templates
from .page import click_and_wait_for_page
from .tabbed_page import (
    TabbedPageType,
    get_active_tab_index,
    identify_page_type,
    make_tab_checker,
)
from autowsgr.vision import ImageChecker


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class BuildTab(enum.Enum):
    """建造页面标签组。"""

    BUILD = "建造"
    DESTROY = "解体"
    DEVELOP = "开发"
    DISCARD = "废弃"


# ═══════════════════════════════════════════════════════════════════════════════
# 标签索引映射
# ═══════════════════════════════════════════════════════════════════════════════

_TAB_LIST: list[BuildTab] = list(BuildTab)
"""标签枚举值列表 — 索引与标签栏探测位置一一对应。"""

_TAB_TO_INDEX: dict[BuildTab, int] = {
    tab: i for i, tab in enumerate(_TAB_LIST)
}
"""标签 → 标签索引映射。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_BACK: tuple[float, float] = (0.022, 0.058)
"""回退按钮 (◁)。"""

CLICK_TAB: dict[BuildTab, tuple[float, float]] = {
    BuildTab.BUILD:   (0.1875, 0.0463),
    BuildTab.DESTROY: (0.3125, 0.0463),
    BuildTab.DEVELOP: (0.4375, 0.0463),
    BuildTab.DISCARD: (0.5625, 0.0463),
}
"""标签切换点击坐标。

.. note::
    坐标为估计值 (TODO: 待实际截图确认)。
"""

# ── 建造槽位 ──

BUILD_SLOT_POSITIONS: list[tuple[float, float]] = [
    (0.823, 0.312),
    (0.823, 0.508),
    (0.823, 0.701),
    (0.823, 0.898),
]
"""4 个建造槽位的中心点 (start/complete/fast 按钮位置)。"""

CLICK_CONFIRM_BUILD: tuple[float, float] = (0.89, 0.89)
"""确认建造按钮。"""

# ── 解体标签操作 ──

CLICK_DESTROY_ADD: tuple[float, float] = (0.0938, 0.3815)
"""解体 — 点击「添加」按钮。旧代码: timer.click(90, 206)"""

CLICK_DESTROY_QUICK_SELECT: tuple[float, float] = (0.91, 0.3)
"""解体 — 快速选择按钮。"""

CLICK_DESTROY_CONFIRM_SELECT: tuple[float, float] = (0.915, 0.906)
"""解体 — 确认选择。"""

CLICK_DESTROY_REMOVE_EQUIP: tuple[float, float] = (0.837, 0.646)
"""解体 — 卸下装备复选框。"""

CLICK_DESTROY_CONFIRM: tuple[float, float] = (0.9, 0.9)
"""解体 — 解装确认按钮。"""

CLICK_DESTROY_FOUR_STAR_CONFIRM: tuple[float, float] = (0.38, 0.567)
"""解体 — 四星确认弹窗。"""

CLICK_DESTROY_TYPE_FILTER: tuple[float, float] = (0.912, 0.681)
"""解体 — 打开舰船类型过滤器。"""

CLICK_DESTROY_CONFIRM_FILTER: tuple[float, float] = (0.9, 0.85)
"""解体 — 确认舰船类型过滤。"""

# ── 建造获取动画 ──

CLICK_DISMISS_ANIMATION: tuple[float, float] = (0.9531, 0.9537)
"""点击跳过建造获取动画。旧代码: timer.click(915, 515)"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class BuildPage:
    """建造页面控制器 (含 解体/开发/废弃 标签组)。

    Parameters
    ----------
    ctrl:
        Android 设备控制器实例。
    """

    def __init__(self, ctrl: AndroidController) -> None:
        self._ctrl = ctrl

    # ── 页面识别 ──────────────────────────────────────────────────────────

    @staticmethod
    def is_current_page(screen: np.ndarray) -> bool:
        """判断截图是否为建造页面组 (含全部 4 个标签)。

        通过统一标签页检测层识别。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        return identify_page_type(screen) == TabbedPageType.BUILD

    @staticmethod
    def get_active_tab(screen: np.ndarray) -> BuildTab | None:
        """获取当前激活的标签。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。

        Returns
        -------
        BuildTab | None
            当前标签，索引越界或无法确定时返回 ``None``。
        """
        idx = get_active_tab_index(screen)
        if idx is None or idx >= len(_TAB_LIST):
            return None
        return _TAB_LIST[idx]

    # ── 标签切换 ──────────────────────────────────────────────────────────

    def switch_tab(self, tab: BuildTab) -> None:
        """切换到指定标签并验证到达。

        会先截图判断当前标签状态并记录日志，然后点击目标标签，
        最后验证目标标签签名匹配。

        Parameters
        ----------
        tab:
            目标标签。

        Raises
        ------
        NavigationError
            超时未到达目标标签。
        """
        current = self.get_active_tab(self._ctrl.screenshot())
        logger.info(
            "[UI] 建造页面: {} → {}",
            current.value if current else "未知",
            tab.value,
        )
        target_idx = _TAB_TO_INDEX[tab]
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_TAB[tab],
            checker=make_tab_checker(TabbedPageType.BUILD, target_idx),
            source=f"建造-{current.value if current else '?'}",
            target=f"建造-{tab.value}",
        )

    # ── 回退 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回侧边栏。

        Raises
        ------
        NavigationError
            超时仍在建造页面。
        """
        from autowsgr.ui.sidebar_page import SidebarPage

        logger.info("[UI] 建造页面 → 返回侧边栏")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=SidebarPage.is_current_page,
            source=PageName.BUILD,
            target=PageName.SIDEBAR,
        )

    # ── 建造操作 ──────────────────────────────────────────────────────────

    def click_slot(self, slot: int) -> None:
        """点击建造槽位 (1–4)。

        Parameters
        ----------
        slot:
            槽位编号 (1–4)。
        """
        if not 1 <= slot <= 4:
            raise ValueError(f"建造槽位必须为 1–4，收到: {slot}")
        logger.info("[UI] 建造页面 → 点击槽位 {}", slot)
        self._ctrl.click(*BUILD_SLOT_POSITIONS[slot - 1])
        time.sleep(0.5)

    def collect_slot(self, slot: int) -> None:
        """收取指定槽位的已完成建造。

        点击槽位后等待弹出获取动画。

        Parameters
        ----------
        slot:
            槽位编号 (1–4)。
        """
        logger.info("[UI] 建造页面 → 收取槽位 {}", slot)
        self.click_slot(slot)
        time.sleep(1.0)

    def fast_build_slot(self, slot: int) -> None:
        """对指定槽位使用快速建造。

        点击快速建造按钮后等待确认弹窗。

        Parameters
        ----------
        slot:
            槽位编号 (1–4)。
        """
        logger.info("[UI] 建造页面 → 快速建造槽位 {}", slot)
        self.click_slot(slot)
        time.sleep(0.5)

    def start_build(self) -> None:
        """在当前标签下启动建造。

        点击一个空闲槽位的「开始建造」按钮后，
        等待资源选择页面，然后点击确认。

        .. note::
            资源配方调整（滑块操作）需要 ops 层配合 OCR 实现。
            此方法仅执行确认点击。
        """
        logger.info("[UI] 建造页面 → 确认建造")
        self._ctrl.click(*CLICK_CONFIRM_BUILD)
        time.sleep(1.0)

    def dismiss_animation(self) -> None:
        """点击跳过建造获取动画。"""
        self._ctrl.click(*CLICK_DISMISS_ANIMATION)

    # ── 解体操作 ──────────────────────────────────────────────────────────

    def destroy_click_add(self) -> None:
        """解体标签 → 点击「添加」按钮。"""
        logger.info("[UI] 建造页面 (解体) → 添加")
        self._ctrl.click(*CLICK_DESTROY_ADD)

    def destroy_quick_select(self) -> None:
        """解体标签 → 点击「快速选择」按钮。"""
        logger.info("[UI] 建造页面 (解体) → 快速选择")
        self._ctrl.click(*CLICK_DESTROY_QUICK_SELECT)

    def destroy_confirm_select(self) -> None:
        """解体标签 → 点击「确认选择」。"""
        logger.info("[UI] 建造页面 (解体) → 确认选择")
        self._ctrl.click(*CLICK_DESTROY_CONFIRM_SELECT)

    def destroy_toggle_remove_equip(self) -> None:
        """解体标签 → 点击「卸下装备」复选框。"""
        logger.info("[UI] 建造页面 (解体) → 卸下装备")
        self._ctrl.click(*CLICK_DESTROY_REMOVE_EQUIP)

    def destroy_confirm(self) -> None:
        """解体标签 → 点击「解装确认」。"""
        logger.info("[UI] 建造页面 (解体) → 解装确认")
        self._ctrl.click(*CLICK_DESTROY_CONFIRM)

    def destroy_four_star_confirm(self) -> None:
        """解体标签 → 四星确认弹窗点击确认。"""
        logger.info("[UI] 建造页面 (解体) → 四星确认")
        self._ctrl.click(*CLICK_DESTROY_FOUR_STAR_CONFIRM)

    def destroy_open_type_filter(self) -> None:
        """解体标签 → 打开舰船类型过滤器。"""
        logger.info("[UI] 建造页面 (解体) → 打开类型过滤")
        self._ctrl.click(*CLICK_DESTROY_TYPE_FILTER)

    def destroy_confirm_filter(self) -> None:
        """解体标签 → 确认舰船类型过滤。"""
        logger.info("[UI] 建造页面 (解体) → 确认过滤")
        self._ctrl.click(*CLICK_DESTROY_CONFIRM_FILTER)

    # ── 组合动作 — 建造收取 ──

    def dismiss_build_result(self) -> None:
        """处理建造完成后获取舰船的动画/弹窗。"""
        get_ship_templates = [Templates.Symbol.GET_SHIP, Templates.Symbol.GET_ITEM]
        for _ in range(10):
            screen = self._ctrl.screenshot()
            if not ImageChecker.template_exists(screen, get_ship_templates):
                break
            self.dismiss_animation()
            time.sleep(0.5)
            screen = self._ctrl.screenshot()
            detail = ImageChecker.find_any(screen, Templates.Confirm.all())
            if detail is not None:
                self._ctrl.click(*detail.center)
                time.sleep(0.5)

    def collect_all(
        self,
        build_type: str = "ship",
        *,
        allow_fast_build: bool = False,
    ) -> int:
        """收取已建造完成的舰船或装备。

        必须已在建造页面对应标签上。

        Returns
        -------
        int
            收取数量。

        Raises
        ------
        RuntimeError
            仓库已满。
        """
        collected = 0

        if allow_fast_build:
            fast_tmpl = (
                Templates.Build.SHIP_FAST
                if build_type == "ship"
                else Templates.Build.EQUIP_FAST
            )
            for _ in range(4):
                screen = self._ctrl.screenshot()
                detail = ImageChecker.find_template(screen, fast_tmpl)
                if detail is None:
                    break
                self._ctrl.click(*detail.center)
                time.sleep(0.3)
                screen = self._ctrl.screenshot()
                confirm = ImageChecker.find_any(screen, Templates.Confirm.all())
                if confirm is not None:
                    self._ctrl.click(*confirm.center)
                    time.sleep(1.0)

        complete_tmpl = (
            Templates.Build.SHIP_COMPLETE
            if build_type == "ship"
            else Templates.Build.EQUIP_COMPLETE
        )
        full_depot_tmpl = (
            Templates.Build.SHIP_FULL_DEPOT
            if build_type == "ship"
            else Templates.Build.EQUIP_FULL_DEPOT
        )

        for _ in range(4):
            screen = self._ctrl.screenshot()
            detail = ImageChecker.find_template(screen, complete_tmpl)
            if detail is None:
                break
            if ImageChecker.template_exists(screen, full_depot_tmpl):
                raise RuntimeError(f"{build_type} 仓库已满")
            self._ctrl.click(*detail.center)
            time.sleep(1.0)
            self.dismiss_build_result()
            collected += 1

        logger.info("[UI] 建造收取: {} 艘 ({})", collected, build_type)
        return collected

    def start_new_build(self, build_type: str = "ship") -> None:
        """在当前标签启动一次新建造。

        Raises
        ------
        RuntimeError
            队列已满或资源选择页面未出现。
        """
        start_tmpl = (
            Templates.Build.SHIP_START
            if build_type == "ship"
            else Templates.Build.EQUIP_START
        )
        screen = self._ctrl.screenshot()
        detail = ImageChecker.find_template(screen, start_tmpl)
        if detail is None:
            raise RuntimeError(f"{build_type} 建造队列已满")

        self._ctrl.click(*detail.center)
        time.sleep(1.0)

        resource_tmpl = Templates.Build.RESOURCE
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            screen = self._ctrl.screenshot()
            if ImageChecker.template_exists(screen, resource_tmpl):
                break
            time.sleep(0.3)
        else:
            raise RuntimeError("资源选择页面未出现")

        self._ctrl.click(*CLICK_CONFIRM_BUILD)
        time.sleep(1.0)
        logger.info("[UI] 建造已启动 ({})", build_type)

    def destroy_all(self, *, remove_equipment: bool = True) -> None:
        """完整的解体流程 (在解体标签上执行)。

        Parameters
        ----------
        remove_equipment:
            是否卸下装备。
        """
        _STEP_DELAY = 1.5

        self.destroy_click_add()
        time.sleep(_STEP_DELAY)
        self.destroy_quick_select()
        time.sleep(_STEP_DELAY)
        self.destroy_confirm_select()
        time.sleep(_STEP_DELAY)
        if remove_equipment:
            self.destroy_toggle_remove_equip()
            time.sleep(_STEP_DELAY)
        self.destroy_confirm()
        time.sleep(_STEP_DELAY)
        self.destroy_four_star_confirm()
        time.sleep(_STEP_DELAY)

        logger.info("[UI] 解装操作完成 (卸下装备={})", remove_equipment)
