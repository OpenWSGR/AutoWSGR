"""战斗操作函数 — 封装所有战斗中的点击与检测操作。

将旧代码中分散在各处的坐标点击、图像检测等操作集中封装，
使战斗引擎的决策逻辑与 UI 操作解耦。

所有坐标均使用 **相对值** (0.0–1.0)，由 ``AndroidController`` 自动转换。

坐标值来源 (960×540 分辨率映射):
  - ``(677, 492)`` → ``(0.705, 0.911)`` 撤退按钮
  - ``(855, 501)`` → ``(0.891, 0.928)`` 进入战斗按钮
  - ``(325, 350)`` → ``(0.339, 0.648)`` 前进 / 追击按钮
  - ``(615, 350)`` → ``(0.641, 0.648)`` 回港 / 撤退(夜战)按钮
  - ``(915, 515)`` → ``(0.953, 0.954)`` 点击战果继续
  - ``(900, 500)`` → ``(0.938, 0.926)`` 开始出征
  - ``(250, 520)`` → ``(0.260, 0.963)`` 移动加速点击
  - ``(380, 520)`` → ``(0.396, 0.963)`` 战役加速 / 跳过导弹
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from autowsgr.emulator.controller import AndroidController

from autowsgr.types import FightCondition, Formation


# ═══════════════════════════════════════════════════════════════════════════════
# 坐标常量（相对值，基于 960×540）
# ═══════════════════════════════════════════════════════════════════════════════


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

    # ── 演习阵型选择 ──
    @staticmethod
    def exercise_formation(formation: int) -> tuple[float, float]:
        """演习中阵型按钮坐标。

        旧代码: ``click(573, formation * 100 - 20)``
        """
        return 0.597, (formation * 100 - 20) / 540


# ═══════════════════════════════════════════════════════════════════════════════
# 血条检测位置
# ═══════════════════════════════════════════════════════════════════════════════


class BloodBarPositions:
    """血条检测像素位置（绝对坐标，用于像素颜色判断）。

    基于 960×540 分辨率，分两组:
      - 出征准备/结算界面（横排）
      - 战果结算/MVP界面（纵排）
    """

    # [slot_index] → (x, y) 绝对坐标, 1-based (index 0 = None)
    PREPARE_PAGE: list[tuple[int, int] | None] = [
        None,
        (56, 322),
        (168, 322),
        (280, 322),
        (392, 322),
        (504, 322),
        (616, 322),
    ]

    RESULT_PAGE: list[tuple[int, int] | None] = [
        None,
        (60, 142),
        (60, 217),
        (60, 292),
        (60, 367),
        (60, 442),
        (60, 517),
    ]


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


def click_exercise_formation(device: AndroidController, formation: Formation) -> None:
    """选择演习阵型（使用演习专用坐标）。

    Parameters
    ----------
    device:
        设备控制器。
    formation:
        目标阵型。
    """
    x, y = Coords.exercise_formation(formation.value)
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

    与旧代码 ``check_blood(blood, rule)`` 对应。

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
