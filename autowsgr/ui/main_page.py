"""主页面 UI 控制器。

覆盖游戏 **主页面** (母港界面) 的导航交互。

页面布局::

    ┌──────────────────────────────────────────────────────────────┐
    │ Lv.  提督名      🛢 油  🔩 弹  🧱 钢  🎯 铝    💎 x  ⊕  │
    │ 🏠                                                          │
    │ 🏛(home)                                   ┌────────────┐  │
    │                                             │  活动横幅  │  │
    │                                             └────────────┘  │
    │                 (秘书舰立绘)                                 │
    │                                                              │
    │                                                              │
    │                                              剩余 N 天      │
    │ ≡   ✉   ★                        任务   船坞    出征      │
    └──────────────────────────────────────────────────────────────┘

4 个导航控件:

- **出征** (右下): 进入地图选择页面 (map_page)，退出控件在左上角 ◁
- **任务** (中下): 进入任务页面 (task_page)，退出控件在左上角 ◁
- **侧边栏** (左下 ≡): 打开侧边栏 (sidebar_page)，退出控件在左下角 (同一按钮)
- **主页** (左侧 🏛): 进入主页 (home_page)，退出控件在左上角 ◁

坐标体系:
    所有坐标为相对值 (0.0–1.0)，与分辨率无关。

使用方式::

    from autowsgr.ui.main_page import MainPage, MainPageTarget

    page = MainPage(ctrl)

    # 页面识别
    screen = ctrl.screenshot()
    if MainPage.is_current_page(screen):
        page.navigate_to(MainPageTarget.SORTIE)

    # 从子页面返回
    page.return_from(MainPageTarget.SORTIE)
"""

from __future__ import annotations

import enum

import numpy as np
from loguru import logger

from autowsgr.emulator.controller import AndroidController
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


class MainPageTarget(enum.Enum):
    """主页面可导航的目标。"""

    SORTIE = "出征"
    TASK = "任务"
    SIDEBAR = "侧边栏"
    HOME = "主页"


# ═══════════════════════════════════════════════════════════════════════════════
# 页面识别签名
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_SIGNATURE = PixelSignature(
    name="main_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8896, 0.0278, (110, 193, 255), tolerance=30.0),
        PixelRule.of(0.7885, 0.0352, (252, 144, 71), tolerance=30.0),
        PixelRule.of(0.6813, 0.0333, (82, 82, 82), tolerance=30.0),
        PixelRule.of(0.5781, 0.0389, (64, 98, 63), tolerance=30.0),
        PixelRule.of(0.4750, 0.0278, (158, 198, 109), tolerance=30.0),
        PixelRule.of(0.9719, 0.9019, (136, 143, 149), tolerance=30.0),
        PixelRule.of(0.0583, 0.8833, (250, 250, 248), tolerance=30.0),
        PixelRule.of(0.9792, 0.0389, (40, 40, 50), tolerance=30.0),
    ],
)
"""主页面像素签名 — 检测资源栏 + 角落特征。"""

_STATE_TOLERANCE = 30.0
"""通用颜色容差。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 导航按钮点击坐标
# ═══════════════════════════════════════════════════════════════════════════════

CLICK_NAV: dict[MainPageTarget, tuple[float, float]] = {
    MainPageTarget.SORTIE:  (0.9375, 0.8981),
    MainPageTarget.TASK:    (0.6823, 0.9037),
    MainPageTarget.SIDEBAR: (0.0490, 0.8981),
    MainPageTarget.HOME:    (0.0531, 0.1519),
}
"""4 个导航控件的点击坐标。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 子页面退出坐标
# ═══════════════════════════════════════════════════════════════════════════════

EXIT_TOP_LEFT: tuple[float, float] = (0.022, 0.058)
"""左上角回退按钮 ◁ (出征/任务/主页 通用)。"""

EXIT_SIDEBAR: tuple[float, float] = (0.0490, 0.8981)
"""侧边栏退出 — 左下角同一按钮 (≡ 切换)。"""

CLICK_EXIT: dict[MainPageTarget, tuple[float, float]] = {
    MainPageTarget.SORTIE:  EXIT_TOP_LEFT,
    MainPageTarget.TASK:    EXIT_TOP_LEFT,
    MainPageTarget.HOME:    EXIT_TOP_LEFT,
    MainPageTarget.SIDEBAR: EXIT_SIDEBAR,
}
"""子页面退出控件的点击坐标。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 子页面识别签名 (用于冒烟测试验证)
# ═══════════════════════════════════════════════════════════════════════════════

MAP_PAGE_SIGNATURE = PixelSignature(
    name="map_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8938, 0.0602, (241, 96, 69), tolerance=30.0),
        PixelRule.of(0.9672, 0.0472, (21, 38, 66), tolerance=30.0),
        PixelRule.of(0.6297, 0.1046, (23, 42, 72), tolerance=30.0),
        PixelRule.of(0.3391, 0.1019, (28, 44, 69), tolerance=30.0),
        PixelRule.of(0.1833, 0.1083, (17, 33, 58), tolerance=30.0),
    ],
)
"""出征 (地图选择) 页面签名。"""

SIDEBAR_PAGE_SIGNATURE = PixelSignature(
    name="sidebar_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0406, 0.0787, (59, 59, 59), tolerance=30.0),
        PixelRule.of(0.0443, 0.2074, (51, 51, 51), tolerance=30.0),
        PixelRule.of(0.0417, 0.3426, (56, 56, 56), tolerance=30.0),
        PixelRule.of(0.0422, 0.4583, (60, 62, 61), tolerance=30.0),
        PixelRule.of(0.0417, 0.5935, (53, 53, 53), tolerance=30.0),
        PixelRule.of(0.0422, 0.7231, (59, 59, 59), tolerance=30.0),
    ],
)
"""侧边栏页面签名。"""

SUB_PAGE_SIGNATURES: dict[MainPageTarget, PixelSignature | None] = {
    MainPageTarget.SORTIE:  MAP_PAGE_SIGNATURE,
    MainPageTarget.TASK:    None,  # TODO: 待采集
    MainPageTarget.SIDEBAR: SIDEBAR_PAGE_SIGNATURE,
    MainPageTarget.HOME:    None,  # TODO: 待采集
}
"""子页面签名 (``None`` 表示尚未采集，仅用 "非主页面" 判定)。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class MainPage:
    """主页面 (母港界面) 控制器。

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
        """判断截图是否为主页面。

        通过 8 个特征像素点 (资源栏 + 角落) 全部匹配判定。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        """
        result = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        return result.matched

    # ── 子页面识别 ────────────────────────────────────────────────────────

    @staticmethod
    def is_sub_page(screen: np.ndarray, target: MainPageTarget) -> bool | None:
        """检测截图是否为指定子页面。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。
        target:
            目标子页面。

        Returns
        -------
        bool | None
            匹配结果。无签名时返回 ``None``。
        """
        sig = SUB_PAGE_SIGNATURES.get(target)
        if sig is None:
            return None
        result = PixelChecker.check_signature(screen, sig)
        return result.matched

    # ── 导航 ──────────────────────────────────────────────────────────────

    def navigate_to(self, target: MainPageTarget) -> None:
        """点击导航控件，进入指定子页面。

        Parameters
        ----------
        target:
            导航目标。
        """
        logger.info("[UI] 主页面 → {}", target.value)
        self._ctrl.click(*CLICK_NAV[target])

    def go_to_sortie(self) -> None:
        """点击「出征」— 进入地图选择页面。"""
        self.navigate_to(MainPageTarget.SORTIE)

    def go_to_task(self) -> None:
        """点击「任务」— 进入任务页面。"""
        self.navigate_to(MainPageTarget.TASK)

    def open_sidebar(self) -> None:
        """点击「≡」— 打开侧边栏。"""
        self.navigate_to(MainPageTarget.SIDEBAR)

    def go_home(self) -> None:
        """点击主页图标 — 进入主页页面。"""
        self.navigate_to(MainPageTarget.HOME)

    # ── 返回 ──────────────────────────────────────────────────────────────

    def return_from(self, target: MainPageTarget) -> None:
        """点击子页面退出控件，返回主页面。

        - 出征 / 任务 / 主页: 左上角 ◁ 按钮
        - 侧边栏: 左下角 ≡ 按钮 (同一切换按钮)

        Parameters
        ----------
        target:
            当前所在的子页面。
        """
        logger.info("[UI] {} → 返回主页面", target.value)
        self._ctrl.click(*CLICK_EXIT[target])
