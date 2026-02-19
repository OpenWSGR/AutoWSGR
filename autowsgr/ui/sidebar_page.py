"""侧边栏页面 UI 控制器。

覆盖游戏 **侧边栏** (左下角 ≡ 菜单) 的导航交互。

页面布局::

    ┌───────────┬────────────────────────────────────────────────┐
    │  司令室    │                                                │
    │  好 友     │           (主界面内容，被侧边栏遮挡部分)         │
    │  建 造     │                                                │
    │  强 化     │                                                │
    │  战 况     │                                                │
    │  任 务     │                                                │
    │  ≡        │                                                │
    └───────────┴────────────────────────────────────────────────┘

导航目标:

- **建造** (第3项): 进入建造页面 (含 解体/开发/废弃 标签)
- **强化** (第4项): 进入强化页面 (含 改修/技能 标签)
- **好友** (第2项): 进入好友页面

坐标体系:
    所有坐标为相对值 (0.0–1.0)，由 960×540 绝对坐标换算。
    侧边栏像素签名来自 sig.py 采样数据。

使用方式::

    from autowsgr.ui.sidebar_page import SidebarPage, SidebarTarget

    page = SidebarPage(ctrl)

    # 页面识别
    screen = ctrl.screenshot()
    if SidebarPage.is_current_page(screen):
        page.navigate_to(SidebarTarget.BUILD)

    # 关闭侧边栏
    page.close()
"""

from __future__ import annotations

import enum
import time

import numpy as np
from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ui.page import NavConfig, click_and_wait_for_page, wait_for_page
from autowsgr.vision.matcher import (
    Color,
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════════


class SidebarTarget(enum.Enum):
    """侧边栏可导航的目标。"""

    BUILD = "建造"
    INTENSIFY = "强化"
    FRIEND = "好友"


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_SIGNATURE = PixelSignature(
    name="sidebar_page",
    strategy=MatchStrategy.ALL,
    rules=[
        # 右侧特征 (侧边栏打开时画面右半部分稳定特征)
        PixelRule.of(0.7667, 0.0454, (27, 134, 228), tolerance=30.0),
        PixelRule.of(0.8734, 0.1611, (29, 119, 205), tolerance=30.0),
        PixelRule.of(0.8745, 0.2750, (29, 115, 198), tolerance=30.0),
        PixelRule.of(0.8734, 0.3806, (27, 116, 198), tolerance=30.0),
        PixelRule.of(0.7734, 0.0602, (254, 255, 255), tolerance=30.0),
        # 左侧菜单 — 仅使用不可选中项 (选中时颜色不会变)
        PixelRule.of(0.0417, 0.0806, (55, 55, 55), tolerance=30.0),   # 商城
        PixelRule.of(0.0422, 0.2102, (58, 58, 58), tolerance=30.0),   # 活动
        PixelRule.of(0.0396, 0.6028, (56, 56, 56), tolerance=30.0),   # 图鉴
    ],
)
"""侧边栏像素签名 (来自 sig.py 重新采集)。

右侧 5 点为画面右半部分稳定特征，左侧 3 点选取不可导航项
(商城/活动/图鉴) 以避免选中态蓝色引发误判。
"""

# 左侧菜单项颜色参考
_MENU_GRAY = Color.of(57, 57, 57)
"""菜单项未选中颜色 (深灰)。"""
_MENU_SELECTED = Color.of(0, 160, 232)
"""菜单项选中颜色 (亮蓝)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 导航按钮点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_NAV: dict[SidebarTarget, tuple[float, float]] = {
    SidebarTarget.BUILD:     (0.1563, 0.3704),
    SidebarTarget.INTENSIFY: (0.1563, 0.5000),
    SidebarTarget.FRIEND:    (0.1563, 0.7593),
}
"""侧边栏菜单项点击坐标。

坐标换算: 旧代码 (150, 200) / (150, 270) / (150, 410) ÷ (960, 540)。
"""

CLICK_CLOSE: tuple[float, float] = (0.0438, 0.8963)
"""关闭侧边栏 (左下角 ≡ 同一切换按钮)。"""

CLICK_SUBMENU: dict[SidebarTarget, tuple[float, float]] = {
    SidebarTarget.BUILD:     (0.375, 0.3704),
    SidebarTarget.INTENSIFY: (0.375, 0.5000),
}
"""二级弹出菜单点击坐标。

建造 和 强化 点击后会弹出子选项菜单 (如 建造/特别船坞)，
需要二次点击选中第一个选项。坐标来自旧代码 (360, 200)/(360, 270) ÷ (960, 540)。
"""

_SUBMENU_TARGETS: frozenset[SidebarTarget] = frozenset({
    SidebarTarget.BUILD,
    SidebarTarget.INTENSIFY,
})
"""需要二级菜单点击的导航目标。"""

SUBMENU_DELAY: float = 1.25
"""点击菜单项后等待二级菜单弹出的延迟 (秒)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class SidebarPage:
    """侧边栏页面控制器。

    **状态查询** 为 ``staticmethod``，只需截图即可调用。
    **操作动作** 为实例方法，通过注入的控制器执行。

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
        """判断截图是否为侧边栏页面。

        通过 6 个深色菜单栏采样点全部匹配判定。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    # ── 导航 ──────────────────────────────────────────────────────────────

    def navigate_to(self, target: SidebarTarget) -> None:
        """点击菜单项，进入指定子页面。

        建造 / 强化 需要二级菜单选择 (点击侧边栏项 → 等待弹出 → 点击子选项)。
        好友 直接单次点击。

        Parameters
        ----------
        target:
            导航目标。

        Raises
        ------
        NavigationError
            超时未到达目标页面。
        """
        from autowsgr.ui.build_page import BuildPage
        from autowsgr.ui.friend_page import FriendPage
        from autowsgr.ui.intensify_page import IntensifyPage

        target_checker = {
            SidebarTarget.BUILD: BuildPage.is_current_page,
            SidebarTarget.INTENSIFY: IntensifyPage.is_current_page,
            SidebarTarget.FRIEND: FriendPage.is_current_page,
        }
        logger.info("[UI] 侧边栏 → {}", target.value)

        if target in _SUBMENU_TARGETS:
            # 二级菜单: 点击侧边栏项 → 等弹出 → 点击子选项 → 验证
            self._navigate_with_submenu(
                target, target_checker[target],
            )
        else:
            # 单次点击 (好友)
            click_and_wait_for_page(
                self._ctrl,
                click_coord=CLICK_NAV[target],
                checker=target_checker[target],
                source="侧边栏",
                target=target.value,
            )

    def _navigate_with_submenu(
        self,
        target: SidebarTarget,
        checker,
    ) -> None:
        """带二级弹出菜单的导航 (建造 / 强化)。

        流程: 点击侧边栏项 → 等待弹出 → 点击子选项 → 验证到达目标页面。
        整个流程带重试。
        """
        from autowsgr.ui.page import DEFAULT_NAV_CONFIG, NavigationError

        config = DEFAULT_NAV_CONFIG
        last_err: NavigationError | None = None

        for attempt in range(1, config.max_retries + 1):
            if attempt > 1:
                logger.warning(
                    "[UI] 二级菜单重试 {}/{}: 侧边栏 → {} (等 {:.1f}s)",
                    attempt, config.max_retries, target.value, config.retry_delay,
                )
                time.sleep(config.retry_delay)

            # Step 1: 点击侧边栏菜单项
            self._ctrl.click(*CLICK_NAV[target])
            # Step 2: 等待二级弹出菜单出现
            time.sleep(SUBMENU_DELAY)
            # Step 3: 点击子选项
            self._ctrl.click(*CLICK_SUBMENU[target])

            try:
                wait_for_page(
                    self._ctrl,
                    checker,
                    timeout=config.timeout,
                    interval=config.interval,
                    handle_overlays=config.handle_overlays,
                    source="侧边栏",
                    target=target.value,
                )
                return
            except NavigationError as e:
                last_err = e
                logger.warning(
                    "[UI] 二级菜单后超时 ({}/{}): 侧边栏 → {}",
                    attempt, config.max_retries, target.value,
                )

        raise NavigationError(
            f"导航失败 (已重试 {config.max_retries} 次): 侧边栏 → {target.value}"
        ) from last_err

    def go_to_build(self) -> None:
        """点击「建造」— 进入建造页面。"""
        self.navigate_to(SidebarTarget.BUILD)

    def go_to_intensify(self) -> None:
        """点击「强化」— 进入强化页面。"""
        self.navigate_to(SidebarTarget.INTENSIFY)

    def go_to_friend(self) -> None:
        """点击「好友」— 进入好友页面。"""
        self.navigate_to(SidebarTarget.FRIEND)

    # ── 关闭 ──────────────────────────────────────────────────────────────

    def close(self) -> None:
        """关闭侧边栏，返回主页面。

        点击后反复截图验证，确认已到达主页面。

        Raises
        ------
        NavigationError
            超时未关闭侧边栏。
        """
        from autowsgr.ui.main_page import MainPage

        logger.info("[UI] 侧边栏 → 关闭 (返回主页面)")
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_CLOSE,
            checker=MainPage.is_current_page,
            source="侧边栏",
            target="主页面",
        )
