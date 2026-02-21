"""战斗操作函数 — 封装所有战斗中的点击与检测操作。

note. 该模块应该在测试 handlers.py 被测试

包含:
  - 坐标常量 (Coords)
  - UI 点击操作 (click_*)
  - 血量检测辅助 (check_blood)
  - 图像检查与识别 (image_exist, click_image, get_ship_drop)

所有函数为无状态的纯操作，接收必要的对象参数后直接作用。
"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.image_resources import TemplateKey
from autowsgr.types import FightCondition, Formation, RepairMode, ShipDamageState



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


def check_blood(
    ship_stats: list[ShipDamageState],
    proceed_stop: RepairMode | list[RepairMode],
) -> bool:
    """检查血量是否满足继续前进条件。

    Parameters
    ----------
    ship_stats:
        我方血量状态（0-indexed，长度 6）。
    proceed_stop:
        停止条件。可以是:
        - 单个 RepairMode: 所有位置一致的阈值
        - 列表(6个): 每个位置不同的阈值

        ``RepairMode.moderate_damage`` (1) 表示中破及以上停止,
        ``RepairMode.severe_damage`` (2) 表示大破及以上停止。

    Returns
    -------
    bool
        ``True`` = 可以继续前进，``False`` = 应当回港。
    """
    if isinstance(proceed_stop, RepairMode):
        rules = [proceed_stop] * 6
    else:
        rules = proceed_stop

    for i in range(min(len(ship_stats), len(rules))):
        stat = ship_stats[i]
        rule = rules[i]

        if stat == ShipDamageState.NO_SHIP:
            continue
        if stat >= rule:
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 图像检查与识别函数（接收 device 和 template_key，内部完成匹配）
# ═══════════════════════════════════════════════════════════════════════════════


def image_exist(device: AndroidController, template_key: TemplateKey, confidence: float) -> bool:
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
    from autowsgr.image_resources import TemplateKey as _TK
    from autowsgr.vision import ImageChecker

    screen = device.screenshot()
    if isinstance(template_key, str):
        template_key = _TK(template_key)
    templates = template_key.templates
    return ImageChecker.find_any(screen, templates, confidence=confidence) is not None


def click_image(device: AndroidController, template_key: TemplateKey, timeout: float) -> bool:
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
    from autowsgr.image_resources import TemplateKey as _TK
    from autowsgr.vision import ImageChecker

    if isinstance(template_key, str):
        template_key = _TK(template_key)
    deadline = time.time() + timeout
    while time.time() < deadline:
        screen = device.screenshot()
        templates = template_key.templates
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
    from autowsgr.combat.recognizer import CombatRecognitionTimeout
    from autowsgr.image_resources.keys import RESULT_GRADE_KEYS
    from autowsgr.vision import ImageChecker

    retry = 0
    while retry < 5:
        screen = device.screenshot()
        for grade, key in RESULT_GRADE_KEYS.items():
            templates = key.templates
            if ImageChecker.find_any(screen, templates, confidence=0.8) is not None:
                return grade
        time.sleep(0.25)
        retry += 1
    raise CombatRecognitionTimeout("战果等级识别超时: 5 次尝试未识别到有效等级")


def detect_ship_stats(
    device: AndroidController,
    pre_battle_stats: list[ShipDamageState],
) -> list[ShipDamageState]:
    """战斗结算页检测我方舰队血量状态。
    note. 已通过测试
    Parameters
    ----------
    device:
        设备控制器。
    pre_battle_stats:
        战斗开始前的血量状态（0-indexed，长度 6）。
        若对应位置为 :attr:`ShipDamageState.NO_SHIP`，则无论检测结果如何
        都保持无舰船状态。

    Returns
    -------
    list[ShipDamageState]
        长度 6 的列表（0-indexed）。
    """
    from autowsgr.combat.recognition import RESULT_BLOOD_BAR_PROBE
    from autowsgr.ui.battle.blood import classify_blood
    from autowsgr.vision import PixelChecker

    screen = device.screenshot()
    result: list[ShipDamageState] = [ShipDamageState.NORMAL] * 6

    for slot, (x, y) in RESULT_BLOOD_BAR_PROBE.items():
        if pre_battle_stats[slot] == ShipDamageState.NO_SHIP:
            result[slot] = ShipDamageState.NO_SHIP
            continue
        pixel = PixelChecker.get_pixel(screen, x, y)
        result[slot] = classify_blood(pixel)

    logger.info("结算页血量检测: {}", [s.name for s in result])
    return result
