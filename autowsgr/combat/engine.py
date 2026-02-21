"""战斗引擎 — 状态机主循环。

``CombatEngine`` 是战斗系统的核心，驱动以下完整流程::

    状态识别 → 决策 → 操作 → 状态转移 → 重复

它将旧代码中 ``FightPlan.fight()`` + ``FightPlan._make_decision()`` +
``FightInfo.update_state()`` + ``DecisionBlock.make_decision()`` 的逻辑
统一到一个清晰的状态机循环中。

设计要点:
  1. **自包含**: 图像匹配、敌方识别、战果检测等全部由引擎内部完成
  2. **数据驱动**: 节点决策全部来自 ``CombatPlan`` (YAML 配置)
  3. **安全规则**: 使用 ``RuleEngine`` 替代 ``eval()``
  4. **完整历史**: 所有事件通过 ``CombatHistory`` 记录

模块拆分::

    callbacks.py  — CombatResult 与类型签名
    handlers.py   — 各状态处理器 (PhaseHandlersMixin)
    engine.py     — 主循环与状态识别 (本文件)

使用方式::

    engine = CombatEngine(device)
    result = engine.fight(plan)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

from loguru import logger

from autowsgr.combat.actions import click_speed_up, click_start_march
from autowsgr.combat.callbacks import CombatResult
from autowsgr.combat.handlers import PhaseHandlersMixin
from autowsgr.combat.history import CombatEvent, CombatHistory, EventType, FightResult
from autowsgr.combat.image_resources import get_template
from autowsgr.combat.node_tracker import MapNodeData, NodeTracker
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.combat.recognition import recognize_enemy_ships, recognize_enemy_formation
from autowsgr.combat.recognizer import (
    CombatRecognitionTimeout,
    CombatRecognizer,
    RESULT_GRADE_TEMPLATES,
)
from autowsgr.combat.state import CombatPhase, resolve_successors
from autowsgr.types import ConditionFlag, Formation
from autowsgr.vision import ImageChecker

if TYPE_CHECKING:
    from autowsgr.emulator.controller import AndroidController
    from autowsgr.vision import OCREngine


# ═══════════════════════════════════════════════════════════════════════════════
# 战斗引擎
# ═══════════════════════════════════════════════════════════════════════════════


class CombatEngine(PhaseHandlersMixin):
    """自包含的战斗状态机引擎。

    引擎内部自行完成图像匹配、敌方编成/阵型识别、战果等级检测等，
    无需外部注入回调函数，沿袭旧代码 ``Timer`` 内置识别能力的设计。

    Parameters
    ----------
    device:
        设备控制器 (截图 + 触控)。
    ocr:
        OCR 引擎实例 (阵型识别用)。可选，为 ``None`` 则跳过阵型识别。
    """

    def __init__(
        self,
        device: AndroidController,
        ocr: OCREngine | None = None,
    ) -> None:
        self._device = device
        self._ocr = ocr

        # 运行时状态 (由 fight() 重置)
        self._plan: CombatPlan = CombatPlan(name="", mode=CombatMode.BATTLE)
        self._recognizer: CombatRecognizer = None  # type: ignore[assignment]  # set in fight()
        self._phase = CombatPhase.PROCEED
        self._last_action = "yes"
        self._node = "0"
        self._ship_stats: list[int] = [0] * 7
        self._enemies: dict[str, int] = {}
        self._enemy_formation = ""
        self._history = CombatHistory()
        self._node_count = 0

        # 节点跟踪器 (仅常规战模式有效，由 fight() 初始化)
        self._tracker: NodeTracker | None = None

        # 节点级临时状态
        self._formation_by_rule: Formation | None = None

    # ═══════════════════════════════════════════════════════════════════════════
    # 公共接口
    # ═══════════════════════════════════════════════════════════════════════════

    def fight(
        self,
        plan: CombatPlan,
        initial_ship_stats: list[int] | None = None,
    ) -> CombatResult:
        """执行一次完整的战斗循环。

        从当前状态开始，循环执行:
        ``update_state → make_decision`` 直到战斗结束或 SL。

        Parameters
        ----------
        plan:
            作战计划 (阵型、夜战、节点决策等)。
        initial_ship_stats:
            初始血量状态（来自出征准备页面的检测结果）。

        Returns
        -------
        CombatResult
        """
        self._plan = plan
        self._recognizer = CombatRecognizer(
            self._device,
            self._make_image_matcher(),
        )
        self._reset()

        # 常规战模式下加载地图节点数据并初始化节点追踪器
        if plan.mode == CombatMode.NORMAL:
            map_data = MapNodeData.load(plan.chapter, plan.map_id)
            if map_data is not None:
                self._tracker = NodeTracker(map_data)
                logger.info(
                    "节点追踪器已加载: {}-{} ({} 个节点)",
                    plan.chapter, plan.map_id, len(map_data),
                )
            else:
                self._tracker = None
                logger.warning(
                    "无法加载地图数据 {}-{}，节点追踪将不可用",
                    plan.chapter, plan.map_id,
                )
        else:
            self._tracker = None

        if initial_ship_stats is not None:
            self._ship_stats = initial_ship_stats[:]

        result = CombatResult(history=self._history)

        while True:
            try:
                decision = self._step()
            except CombatRecognitionTimeout as e:
                logger.warning("状态识别超时: {}", e)
                if self._try_recovery():
                    continue
                result.flag = ConditionFlag.SL
                break

            if decision == ConditionFlag.FIGHT_CONTINUE:
                continue
            elif decision == ConditionFlag.SL:
                result.flag = ConditionFlag.SL
                break
            elif decision == ConditionFlag.FIGHT_END:
                logger.debug("战斗已结束，日志: {}", self._history)
                result.flag = ConditionFlag.OPERATION_SUCCESS
                break

        result.ship_stats = self._ship_stats[:]
        result.node_count = self._node_count
        logger.info(
            "战斗结束: {} (节点数={})",
            result.flag.value,
            result.node_count,
        )
        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════════════════════

    def _reset(self) -> None:
        """重置运行时状态。"""
        self._history.reset()
        self._node = "0"
        self._node_count = 0
        self._enemies = {}
        self._enemy_formation = ""
        self._formation_by_rule = None

        # 重置节点追踪器
        if self._tracker is not None:
            self._tracker.reset()

        if self._plan.mode == CombatMode.NORMAL:
            self._phase = CombatPhase.PROCEED
            self._last_action = "yes"
        elif self._plan.mode == CombatMode.BATTLE:
            self._phase = CombatPhase.PROCEED
            self._last_action = ""
        elif self._plan.mode == CombatMode.EXERCISE:
            self._phase = CombatPhase.SPOT_ENEMY_SUCCESS
            self._last_action = ""

    def _step(self) -> ConditionFlag:
        """执行一步: 状态更新 + 决策。"""
        new_phase = self._update_state()
        return self._make_decision(new_phase)

    def _update_state(self) -> CombatPhase:
        """等待并识别下一个状态。"""
        last_phase = self._phase

        candidates = resolve_successors(
            self._plan.transitions,
            self._phase,
            self._last_action,
        )

        logger.debug(
            "当前: {} (action={}) → 候选: {}",
            last_phase.name,
            self._last_action,
            [(c.name, t) for c, t in candidates],
        )

        before_match = self._make_before_match_callback(last_phase)

        new_phase = self._recognizer.wait_for_phase(
            candidates,
            before_match=before_match,
        )

        self._phase = new_phase
        self._after_match(new_phase)
        return new_phase

    def _make_before_match_callback(
        self, last_phase: CombatPhase
    ) -> Callable[[], None] | None:
        """创建每轮匹配前的回调 (加速点击)。"""
        if self._plan.mode == CombatMode.NORMAL:
            if last_phase in (
                CombatPhase.PROCEED,
                CombatPhase.FIGHT_CONDITION,
            ) or self._last_action == "detour":
                tracker = self._tracker

                def _speed_up() -> None:
                    click_speed_up(self._device, battle_mode=False)
                    # 在地图移动期间追踪船位并更新节点
                    if tracker is not None:
                        screen = self._device.screenshot()
                        tracker.update_ship_position(screen)
                        new_node = tracker.update_node()
                        if new_node != self._node:
                            self._node = new_node

                return _speed_up

        elif self._plan.mode == CombatMode.BATTLE:
            if last_phase == CombatPhase.PROCEED:

                def _speed_up_battle() -> None:
                    click_speed_up(self._device, battle_mode=True)

                return _speed_up_battle

        return None

    def _after_match(self, phase: CombatPhase) -> None:
        """匹配到状态后的信息收集。"""
        # 当匹配到索敌/前进时，舰船已停在某个节点上，做最终节点校准
        if phase in (
            CombatPhase.SPOT_ENEMY_SUCCESS,
            CombatPhase.FORMATION,
            CombatPhase.FIGHT_CONDITION,
        ) and self._tracker is not None:
            screen = self._device.screenshot()
            self._tracker.update_ship_position(screen)
            new_node = self._tracker.update_node()
            if new_node != self._node:
                self._node = new_node

        if phase == CombatPhase.SPOT_ENEMY_SUCCESS:
            self._enemies = self._get_enemy_info()
            self._enemy_formation = self._get_enemy_formation()
            logger.info("敌方编成: {} 阵型: {}", self._enemies, self._enemy_formation)

        elif phase == CombatPhase.RESULT:
            grade = self._detect_result_grade()
            self._ship_stats = self._detect_ship_stats("sumup")
            fight_result = FightResult(grade=grade, ship_stats=self._ship_stats[:])
            self._history.add(CombatEvent(
                event_type=EventType.RESULT,
                node=self._node,
                result=str(fight_result),
            ))
            logger.info("战果: {} 节点: {}", fight_result, self._node)

    # ═══════════════════════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_current_decision(self) -> NodeDecision:
        """获取当前节点的决策。"""
        return self._plan.get_node_decision(self._node)

    def _try_recovery(self) -> bool:
        """尝试从错误中恢复。"""
        logger.warning("尝试错误恢复...")
        time.sleep(3.0)

        screen = self._device.screenshot()
        end_phase = self._plan.end_phase
        result = self._recognizer.identify_current(screen, [end_phase])
        if result is not None:
            self._phase = end_phase
            return True
        return False

    def set_node(self, node: str) -> None:
        """设置当前节点（外部调用，如地图追踪更新）。"""
        self._node = node

    @property
    def current_node(self) -> str:
        """当前节点。"""
        return self._node

    @property
    def history(self) -> CombatHistory:
        """战斗历史。"""
        return self._history

    # ═══════════════════════════════════════════════════════════════════════════
    # 自包含识别能力 — 参考旧代码 Timer 内置方法
    # ═══════════════════════════════════════════════════════════════════════════

    def _make_image_matcher(self):
        """构建给 CombatRecognizer 用的 image_matcher 回调。"""
        from autowsgr.combat.image_resources import resolve_image_matcher

        return resolve_image_matcher(ImageChecker.find_any)

    def _image_exist(self, template_key: str, confidence: float) -> bool:
        """检查模板是否存在于当前截图中（等价旧代码 ``timer.image_exist``）。"""
        screen = self._device.screenshot()
        templates = get_template(template_key)
        return ImageChecker.find_any(screen, templates, confidence=confidence) is not None

    def _click_image(self, template_key: str, timeout: float) -> bool:
        """等待并点击模板图像中心（等价旧代码 ``timer.click_image``）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            screen = self._device.screenshot()
            templates = get_template(template_key)
            detail = ImageChecker.find_any(screen, templates, confidence=0.8)
            if detail is not None:
                self._device.click(*detail.center)
                return True
            time.sleep(0.3)
        return False

    def _get_enemy_info(self) -> dict[str, int]:
        """识别敌方舰类编成（等价旧代码 ``get_enemy_condition``）。"""
        screen = self._device.screenshot()
        mode = "exercise" if self._plan and self._plan.mode == CombatMode.EXERCISE else "fight"
        return recognize_enemy_ships(screen, mode=mode)

    def _get_enemy_formation(self) -> str:
        """OCR 识别敌方阵型（等价旧代码 ``get_enemy_formation``）。"""
        if self._ocr is None:
            return ""
        screen = self._device.screenshot()
        return recognize_enemy_formation(screen, self._ocr)

    def _detect_result_grade(self) -> str:
        """从战果结算截图识别评级 (SS/S/A/B/C/D)。"""
        while retry := 0 < 5:
            screen = self._device.screenshot()
            for grade, key in RESULT_GRADE_TEMPLATES.items():
                templates = get_template(key)
                if ImageChecker.find_any(screen, templates, confidence=0.8) is not None:
                    return grade
            time.sleep(0.25)
            retry += 1
        raise CombatRecognitionTimeout("战果等级识别超时: 5 次尝试未识别到有效等级")

    def _detect_ship_stats(self, mode: str) -> list[int]:
        """检测我方舰队血量状态。

        Parameters
        TODO: 空位探测没做
        ----------
        mode:
            ``"prepare"`` — 出征准备页检测 (委托 BattlePreparationPage)。
            ``"sumup"`` — 战斗结算页检测 (像素颜色匹配)。

        Returns
        -------
        list[int]
            长度 7 的列表 (index 0 占位)，值含义:
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
            return self._ship_stats[:]

        screen = self._device.screenshot()
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
                result[slot] = self._ship_stats[slot] if slot < len(self._ship_stats) else 0
                logger.debug(
                    "结算页舰船 {} 血量颜色未匹配: {}, 使用战前值: {}",
                    slot, pixel, result[slot],
                )

        logger.info("结算页血量检测: {}", result[1:])
        return result

    def _get_ship_drop(self) -> str | None:
        """获取舰船掉落（当前未实现 OCR，返回 None）。"""
        # TODO: 接入 OCR 识别掉落舰船名
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 兼容函数
# ═══════════════════════════════════════════════════════════════════════════════


def run_combat(
    device: AndroidController,
    plan: CombatPlan,
    image_matcher=None,
    *,
    ship_stats: list[int] | None = None,
    **_kwargs,
) -> CombatResult:
    """执行一次完整战斗的便捷函数 (兼容旧调用方式)。

    现在 ``CombatEngine`` 已自包含所有识别能力，
    ``image_matcher`` 和其余回调参数被忽略。
    """
    engine = CombatEngine(device=device)
    return engine.fight(plan, initial_ship_stats=ship_stats)
