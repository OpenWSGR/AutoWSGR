"""战斗操作函数 — 封装所有战斗中的点击与检测操作。

包含:
  - 坐标常量 (Coords)
  - UI 点击操作 (click_*)
  - 血量检测辅助 (check_blood)
  - 图像检查与识别 (image_exist, click_image, get_ship_drop)

所有函数为无状态的纯操作，接收必要的对象参数后直接作用。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.types import FightCondition, Formation

if TYPE_CHECKING:
    from autowsgr.vision import ImageChecker



class Coords:
    """战斗中使用的所有坐标常量（相对值）。"""

    # ── 出征 ──
    START_MARCH = (0.938, 0.926)
    """开始出征按钮。"""

    # ── 索敌阶段 ──
    RETREAT = (0.705, 0.911)
    """撤退按钮（索敌成功界面）。"""

    ENTER_FIGHT = (0.891, 0.928)
    """进入战斗按钮（索敌成功界面）。"""

    # ── 前进 / 回港 ──
    PROCEED_YES = (0.339, 0.648)
    """前进按钮。"""

    PROCEED_NO = (0.641, 0.648)
    """回港按钮。"""

    # ── 夜战 ──
    NIGHT_YES = (0.339, 0.648)
    """追击（进入夜战）。"""

    NIGHT_NO = (0.641, 0.648)
    """撤退（不进入夜战）。"""

    # ── 结算 ──
    CLICK_RESULT = (0.953, 0.954)
    """点击战果页面继续。"""

    # ── 加速点击 ──
    SPEED_UP_NORMAL = (0.260, 0.963)
    """常规战移动加速点击。"""

    SPEED_UP_BATTLE = (0.396, 0.963)
    """战役加速点击 / 跳过导弹动画。"""

    # ── 旗舰大破 ──
    FLAGSHIP_CONFIRM = (0.500, 0.500)
    """旗舰大破确认（点击图片）。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 操作函数
# ═══════════════════════════════════════════════════════════════════════════════


def click_start_march(device: AndroidController) -> None:
    """点击出征按钮。"""
    device.click(*Coords.START_MARCH)


def click_retreat(device: AndroidController) -> None:
    """点击撤退按钮（索敌成功界面）。"""
    device.click(*Coords.RETREAT)
    time.sleep(0.2)


def click_enter_fight(device: AndroidController) -> None:
    """点击进入战斗（索敌成功界面）。"""
    time.sleep(0.5)
    device.click(*Coords.ENTER_FIGHT)
    time.sleep(0.2)


def click_formation(device: AndroidController, formation: Formation) -> None:
    """选择阵型。

    Parameters
    ----------
    device:
        设备控制器。
    formation:
        目标阵型。
    """
    x, y = formation.relative_position
    device.click(x, y)
    time.sleep(2.0)


def click_fight_condition(device: AndroidController, condition: FightCondition) -> None:
    """选择战况。
    Parameters
    ----------
    device:
        设备控制器。
    condition:
        目标战况。
    """
    x, y = condition.relative_click_position
    device.click(x, y)


def click_night_battle(device: AndroidController, pursue: bool) -> None:
    """夜战选择。

    Parameters
    ----------
    device:
        设备控制器。
    pursue:
        ``True`` = 追击（进入夜战），``False`` = 撤退。
    """
    if pursue:
        device.click(*Coords.NIGHT_YES)
    else:
        device.click(*Coords.NIGHT_NO)


def click_proceed(device: AndroidController, go_forward: bool) -> None:
    """继续前进 / 回港选择。

    Parameters
    ----------
    device:
        设备控制器。
    go_forward:
        ``True`` = 前进，``False`` = 回港。
    """
    if go_forward:
        device.click(*Coords.PROCEED_YES)
    else:
        device.click(*Coords.PROCEED_NO)


def click_result(device: AndroidController) -> None:
    """点击战果页面继续。"""
    device.click(*Coords.CLICK_RESULT)


def click_speed_up(device: AndroidController, *, battle_mode: bool = False) -> None:
    """点击加速（移动中或战役中）。

    Parameters
    ----------
    device:
        设备控制器。
    battle_mode:
        ``True`` 使用战役加速坐标，``False`` 使用常规战坐标。
    """
    coords = Coords.SPEED_UP_BATTLE if battle_mode else Coords.SPEED_UP_NORMAL
    device.click(*coords)


def click_skip_missile_animation(device: AndroidController) -> None:
    """跳过导弹支援动画。"""
    device.click(*Coords.SPEED_UP_BATTLE)
    time.sleep(0.2)
    device.click(*Coords.SPEED_UP_BATTLE)


# ═══════════════════════════════════════════════════════════════════════════════
# 血量检测辅助
# ═══════════════════════════════════════════════════════════════════════════════


def check_blood(ship_stats: list[int], proceed_stop: int | list[int]) -> bool:
    """检查血量是否满足继续前进条件。

    Parameters
    ----------
    ship_stats:
        我方血量状态。索引 0 未用, 1-6 对应 6 个位置。
        值含义: 0=正常, 1=中破, 2=大破, -1=无船, 3=修理中。
    proceed_stop:
        停止条件。可以是:
        - 单个整数: 所有位置一致的阈值
        - 列表(6个): 每个位置不同的阈值
        值含义: -1=忽略, 其他=达到此破损等级则停止。

    Returns
    -------
    bool
        ``True`` = 可以继续前进，``False`` = 应当回港。
    """
    if isinstance(proceed_stop, int):
        rules = [proceed_stop] * 6
    else:
        rules = proceed_stop

    for i in range(min(len(ship_stats) - 1, len(rules))):
        stat = ship_stats[i + 1]  # 1-based
        rule = rules[i]  # 0-based

        if stat == -1 or rule == -1:
            continue
        if stat >= rule:
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 图像检查与识别函数（接收 device 和 template_key，内部完成匹配）
# ═══════════════════════════════════════════════════════════════════════════════


def image_exist(device: AndroidController, template_key: str, confidence: float) -> bool:
    """检查模板是否存在于当前截图中。

    Parameters
    ----------
    device:
        设备控制器。
    template_key:
        模板标识符。
    confidence:
        匹配置信度 (0.0-1.0)。

    Returns
    -------
    bool
        ``True`` = 模板存在，``False`` = 不存在。
    """
    from autowsgr.combat.image_resources import get_template
    from autowsgr.vision import ImageChecker

    screen = device.screenshot()
    templates = get_template(template_key)
    return ImageChecker.find_any(screen, templates, confidence=confidence) is not None


def click_image(device: AndroidController, template_key: str, timeout: float) -> bool:
    """等待并点击模板图像中心。

    Parameters
    ----------
    device:
        设备控制器。
    template_key:
        模板标识符。
    timeout:
        最大等待时间（秒）。

    Returns
    -------
    bool
        ``True`` = 成功点击，``False`` = 超时未找到。
    """
    from autowsgr.combat.image_resources import get_template
    from autowsgr.vision import ImageChecker

    deadline = time.time() + timeout
    while time.time() < deadline:
        screen = device.screenshot()
        templates = get_template(template_key)
        detail = ImageChecker.find_any(screen, templates, confidence=0.8)
        if detail is not None:
            device.click(*detail.center)
            return True
        time.sleep(0.3)
    return False


def get_ship_drop(device: AndroidController) -> str | None:
    """获取掉落舰船名称。

    Parameters
    ----------
    device:
        设备控制器。

    Returns
    -------
    str | None
        掉落的舰船名称，或 ``None`` 如果未获取到。
    """
    # TODO: OCR 实现获取掉落舰船名
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 敌方识别函数
# ═══════════════════════════════════════════════════════════════════════════════


def get_enemy_info(device: AndroidController, mode: str = "fight") -> dict[str, int]:
    """识别敌方舰类编成。

    Parameters
    ----------
    device:
        设备控制器。
    mode:
        战斗模式 (``"fight"`` 或 ``"exercise"``)。

    Returns
    -------
    dict[str, int]
        敌方编成信息，如 ``{"BB": 2, "CV": 1, ...}``。
    """
    from autowsgr.combat.recognition import recognize_enemy_ships

    screen = device.screenshot()
    return recognize_enemy_ships(screen, mode=mode)


def get_enemy_formation(device: AndroidController, ocr_engine) -> str:
    """OCR 识别敌方阵型。

    Parameters
    ----------
    device:
        设备控制器。
    ocr_engine:
        OCR 引擎实例（可为 ``None``）。

    Returns
    -------
    str
        敌方阵型名称，如 ``"单纵阵"``；若无 OCR 引擎则返回空字符串。
    """
    from autowsgr.combat.recognition import recognize_enemy_formation

    if ocr_engine is None:
        return ""
    screen = device.screenshot()
    return recognize_enemy_formation(screen, ocr_engine)


def detect_result_grade(device: AndroidController) -> str:
    """从战果结算截图识别评级 (SS/S/A/B/C/D)。

    Parameters
    ----------
    device:
        设备控制器。

    Returns
    -------
    str
        战果等级。

    Raises
    ------
    CombatRecognitionTimeout
        无法识别到有效的等级。
    """
    from autowsgr.combat.image_resources import get_template
    from autowsgr.combat.recognizer import RESULT_GRADE_TEMPLATES, CombatRecognitionTimeout
    from autowsgr.vision import ImageChecker

    retry = 0
    while retry < 5:
        screen = device.screenshot()
        for grade, key in RESULT_GRADE_TEMPLATES.items():
            templates = get_template(key)
            if ImageChecker.find_any(screen, templates, confidence=0.8) is not None:
                return grade
        time.sleep(0.25)
        retry += 1
    raise CombatRecognitionTimeout("战果等级识别超时: 5 次尝试未识别到有效等级")


def detect_ship_stats(device: AndroidController, mode: str, current_stats: list[int] | None = None) -> list[int]:
    """检测我方舰队血量状态。

    Parameters
    ----------
    device:
        设备控制器。
    mode:
        检测模式：
        - ``"prepare"`` 过时（返回空列表）
        - ``"sumup"`` 战斗结算页检测（像素颜色匹配）
    current_stats:
        当前血量状态（仅在模式为 ``"prepare"`` 时使用回退）。

    Returns
    -------
    list[int]
        长度 7 的列表（索引 0 占位），值含义：
        0=绿血, 1=黄血, 2=红血, 3=维修中, -1=空位。
    """
    from autowsgr.ui.battle.constants import (
        BLOOD_TOLERANCE,
        RESULT_BLOOD_BAR_PROBE,
        RESULT_BLOOD_GREEN,
        RESULT_BLOOD_RED,
        RESULT_BLOOD_YELLOW,
    )
    from autowsgr.vision import PixelChecker

    if mode != "sumup":
        return current_stats[:] if current_stats else [0] * 7

    screen = device.screenshot()
    result = [0] * 7  # index 0 占位

    for slot, (x, y) in RESULT_BLOOD_BAR_PROBE.items():
        pixel = PixelChecker.get_pixel(screen, x, y)

        # 结算页只有绿/黄/红三种状态 (无空位/维修中)
        if pixel.near(RESULT_BLOOD_GREEN, BLOOD_TOLERANCE):
            result[slot] = 0
        elif pixel.near(RESULT_BLOOD_YELLOW, BLOOD_TOLERANCE):
            result[slot] = 1
        elif pixel.near(RESULT_BLOOD_RED, BLOOD_TOLERANCE):
            result[slot] = 2
        else:
            # 未匹配时使用战前状态回退
            if current_stats and slot < len(current_stats):
                result[slot] = current_stats[slot]
            else:
                result[slot] = 0
            logger.debug(
                "结算页舰船 {} 血量颜色未匹配，使用战前值: {}",
                slot, result[slot],
            )

    logger.info("结算页血量检测: {}", result[1:])
    return result
