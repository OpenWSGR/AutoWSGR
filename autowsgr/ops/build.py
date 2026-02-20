"""建造操作。

涉及跨页面操作: 任意页面 → 侧边栏 → 建造页面 → 建造/收取。

旧代码参考: ``game/build.py`` (BuildManager)

- 使用图像模板检测建造完成/开始/快速建造按钮
- 收取已建造完成的舰船
- 启动新建造 (含资源滑块, 需 OCR)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ops.image_resources import Templates
from autowsgr.ops.navigate import goto_page
from autowsgr.ui.build_page import BuildPage, BuildTab
from autowsgr.vision.image_matcher import ImageChecker


# ═══════════════════════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class BuildRecipe:
    """建造配方。"""

    fuel: int
    ammo: int
    steel: int
    bauxite: int


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标常量 (参照旧代码 BuildManager)
# ═══════════════════════════════════════════════════════════════════════════════

# 建造槽位中心 (4 个), 相对坐标
BUILD_SLOT_POSITIONS: list[tuple[float, float]] = [
    (0.823, 0.312),
    (0.823, 0.508),
    (0.823, 0.701),
    (0.823, 0.898),
]
"""4 个建造槽位的中心点 (start/complete/fast 按钮位置)。"""

_CLICK_CONFIRM_BUILD: tuple[float, float] = (0.89, 0.89)
"""确认建造按钮。旧代码: timer.relative_click(0.89, 0.89)"""

_STEP_DELAY: float = 1.0
"""操作步骤间延迟。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════════════════════


def _get_ship_after_build(ctrl: AndroidController) -> None:
    """处理建造完成后获取舰船的动画/弹窗。

    参照旧代码 ``get_ship``: 反复点击直到 symbol_image 消失。
    """
    get_ship_templates = [Templates.Symbol.GET_SHIP, Templates.Symbol.GET_ITEM]
    max_clicks = 10

    for _ in range(max_clicks):
        screen = ctrl.screenshot()
        if not ImageChecker.template_exists(screen, get_ship_templates):
            break
        # 点击屏幕加速动画
        ctrl.click(0.9531, 0.9537)  # 旧代码 timer.click(915, 515)
        time.sleep(0.5)

        # 检查是否有确认弹窗
        screen = ctrl.screenshot()
        detail = ImageChecker.find_any(screen, Templates.Confirm.all())
        if detail is not None:
            ctrl.click(*detail.center)
            time.sleep(0.5)


# ═══════════════════════════════════════════════════════════════════════════════
# 公开函数
# ═══════════════════════════════════════════════════════════════════════════════


def collect_built_ships(
    ctrl: AndroidController,
    *,
    build_type: str = "ship",
    allow_fast_build: bool = False,
) -> int:
    """收取已建造完成的舰船或装备。

    流程 (参照旧代码 ``BuildManager.get_build``):

    1. 导航到建造页面 (或开发页面)
    2. 若 ``allow_fast_build``, 优先点击快速建造
    3. 检测 "完成" 按钮并逐个收取
    4. 处理获取舰船动画

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    build_type:
        ``"ship"`` 或 ``"equipment"``。
    allow_fast_build:
        是否允许使用快速建造。

    Returns
    -------
    int
        收取数量。
    """
    goto_page(ctrl, "建造页面")

    page = BuildPage(ctrl)

    if build_type == "equipment":
        page.switch_tab(BuildTab.DEVELOP)
    else:
        screen = ctrl.screenshot()
        tab = BuildPage.get_active_tab(screen)
        if tab != BuildTab.BUILD:
            page.switch_tab(BuildTab.BUILD)

    time.sleep(0.5)
    collected = 0

    # 1. 快速建造 (可选)
    if allow_fast_build:
        fast_tmpl = (
            Templates.Build.SHIP_FAST
            if build_type == "ship"
            else Templates.Build.EQUIP_FAST
        )
        for _ in range(4):  # 最多 4 个槽位
            screen = ctrl.screenshot()
            detail = ImageChecker.find_template(screen, fast_tmpl)
            if detail is None:
                break
            ctrl.click(*detail.center)
            time.sleep(0.3)
            # 确认快速建造
            screen = ctrl.screenshot()
            confirm = ImageChecker.find_any(screen, Templates.Confirm.all())
            if confirm is not None:
                ctrl.click(*confirm.center)
                time.sleep(1.0)

    # 2. 收取完成
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

    for _ in range(4):  # 最多 4 个槽位
        screen = ctrl.screenshot()
        detail = ImageChecker.find_template(screen, complete_tmpl)
        if detail is None:
            break

        # 检查船坞/仓库是否已满
        if ImageChecker.template_exists(screen, full_depot_tmpl):
            logger.warning("[OPS] {} 仓库已满", build_type)
            break

        ctrl.click(*detail.center)
        time.sleep(1.0)

        # 处理获取舰船动画
        _get_ship_after_build(ctrl)
        collected += 1

    logger.info("[OPS] 建造收取完成: {} 艘 (类型: {})", collected, build_type)
    return collected


def build_ship(
    ctrl: AndroidController,
    *,
    recipe: BuildRecipe | None = None,
    build_type: str = "ship",
    allow_fast_build: bool = False,
) -> bool:
    """建造舰船或装备。

    流程 (参照旧代码 ``BuildManager.build``):

    1. 先收取已完成的建造
    2. 点击 "开始建造" 按钮
    3. 等待资源选择页面
    4. (资源滑块操作需要 OCR，当前使用默认资源)
    5. 确认建造

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    recipe:
        建造配方。None = 使用当前默认配方。
    build_type:
        ``"ship"`` 或 ``"equipment"``。
    allow_fast_build:
        如果队列已满, 是否使用快速建造腾出空位。

    Returns
    -------
    bool
        是否成功启动建造。

    .. note::
        资源滑块操作 (设置具体配方数值) 需要 OCR 识别当前数值后
        滑动调整，复杂度较高。当前版本仅支持使用默认配方 (不调整滑块)，
        后续迭代中可添加滑块控制。
    """
    # 先收取已完成的建造
    collect_built_ships(ctrl, build_type=build_type, allow_fast_build=allow_fast_build)

    # 检查是否有空位
    start_tmpl = (
        Templates.Build.SHIP_START
        if build_type == "ship"
        else Templates.Build.EQUIP_START
    )
    screen = ctrl.screenshot()
    detail = ImageChecker.find_template(screen, start_tmpl)
    if detail is None:
        logger.warning("[OPS] {} 建造队列已满, 无法启动建造", build_type)
        return False

    # 点击开始建造
    ctrl.click(*detail.center)
    time.sleep(1.0)

    # 等待资源选择页面
    resource_tmpl = Templates.Build.RESOURCE
    deadline = time.monotonic() + 5.0
    found = False
    while time.monotonic() < deadline:
        screen = ctrl.screenshot()
        if ImageChecker.template_exists(screen, resource_tmpl):
            found = True
            break
        time.sleep(0.3)

    if not found:
        logger.warning("[OPS] 资源选择页面未出现")
        return False

    # TODO: 如果指定了 recipe, 使用 OCR + 滑块操作设置资源值
    # 当前使用默认配方
    if recipe is not None:
        logger.info(
            "[OPS] 设置建造配方: 油={} 弹={} 钢={} 铝={}",
            recipe.fuel,
            recipe.ammo,
            recipe.steel,
            recipe.bauxite,
        )
        # 资源滑块操作需要 OCR, 暂时跳过
        logger.warning("[OPS] 资源滑块操作暂未实现, 使用默认配方")

    # 确认建造
    ctrl.click(*_CLICK_CONFIRM_BUILD)
    time.sleep(1.0)

    logger.info("[OPS] 建造已启动 (类型: {})", build_type)
    return True
