"""战斗引擎 — 状态机主循环。

``CombatEngine`` 是战斗系统的核心，驱动以下完整流程::

    状态识别 → 决策 → 操作 → 状态转移 → 重复

它将旧代码中 ``FightPlan.fight()`` + ``FightPlan._make_decision()`` +
``FightInfo.update_state()`` + ``DecisionBlock.make_decision()`` 的逻辑
统一到一个清晰的状态机循环中。

设计要点:
  1. **分离关注点**: 识别 (recognizer)、决策 (handlers)、操作 (actions) 各司其职
  2. **数据驱动**: 节点决策全部来自 ``CombatPlan`` (YAML 配置)
  3. **安全规则**: 使用 ``RuleEngine`` 替代 ``eval()``
  4. **完整历史**: 所有事件通过 ``CombatHistory`` 记录

模块拆分::

    callbacks.py  — 回调类型签名与 CombatResult
    handlers.py   — 各状态处理器 (PhaseHandlersMixin)
    engine.py     — 主循环与状态识别 (本文件)

使用方式::

    engine = CombatEngine(device, plan, image_matcher)
    result = engine.fight()
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

from loguru import logger

from autowsgr.combat.actions import click_speed_up, click_start_march
from autowsgr.combat.callbacks import (
    ClickImageFunc,
    CombatResult,
    DetectResultGradeFunc,
    DetectShipStatsFunc,
    GetEnemyFormationFunc,
    GetEnemyInfoFunc,
    GetShipDropFunc,
    ImageExistFunc,
)
from autowsgr.combat.handlers import PhaseHandlersMixin
from autowsgr.combat.history import CombatEvent, CombatHistory, EventType, FightResult
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.combat.recognizer import CombatRecognitionTimeout, CombatRecognizer, ImageMatcherFunc
from autowsgr.combat.state import CombatPhase, resolve_successors
from autowsgr.types import ConditionFlag, Formation

if TYPE_CHECKING:
    from autowsgr.emulator.controller import AndroidController


# ═══════════════════════════════════════════════════════════════════════════════
# 战斗引擎
# ═══════════════════════════════════════════════════════════════════════════════


class CombatEngine(PhaseHandlersMixin):
    """战斗状态机引擎。

    驱动一次完整的战斗流程，从出征准备页面开始，
    经过多个节点的 索敌→阵型→战斗→夜战→结算 循环，
    直到回港或 SL。

    Parameters
    ----------
    device:
        设备控制器。
    plan:
        作战计划。
    image_matcher:
        图像匹配函数。
    get_enemy_info:
        获取敌方编成的回调。
    get_enemy_formation:
        获取敌方阵型的回调。
    detect_ship_stats:
        检测血量的回调。
    detect_result_grade:
        检测战果等级的回调。
    get_ship_drop:
        获取掉落的回调。
    image_exist:
        检查图像是否存在的回调。
    click_image:
        点击图像的回调。
    """

    def __init__(
        self,
        device: AndroidController,
        plan: CombatPlan,
        image_matcher: ImageMatcherFunc,
        *,
        get_enemy_info: GetEnemyInfoFunc | None = None,
        get_enemy_formation: GetEnemyFormationFunc | None = None,
        detect_ship_stats: DetectShipStatsFunc | None = None,
        detect_result_grade: DetectResultGradeFunc | None = None,
        get_ship_drop: GetShipDropFunc | None = None,
        image_exist: ImageExistFunc | None = None,
        click_image: ClickImageFunc | None = None,
    ) -> None:
        self._device = device
        self._plan = plan
        self._recognizer = CombatRecognizer(device, image_matcher)

        # 回调
        self._get_enemy_info = get_enemy_info or (lambda: {})
        self._get_enemy_formation = get_enemy_formation or (lambda: "")
        self._detect_ship_stats = detect_ship_stats or (lambda mode: [0] * 7)
        self._detect_result_grade = detect_result_grade or (lambda: "")
        self._get_ship_drop = get_ship_drop or (lambda: None)
        self._image_exist = image_exist or (lambda key, conf: False)
        self._click_image = click_image or (lambda key, timeout: False)

        # 运行时状态
        self._phase = CombatPhase.PROCEED
        self._last_action = "yes"
        self._node = "0"
        self._ship_stats: list[int] = [0] * 7
        self._enemies: dict[str, int] = {}
        self._enemy_formation = ""
        self._history = CombatHistory()
        self._node_count = 0

        # 节点级临时状态
        self._formation_by_rule: Formation | None = None

    # ═══════════════════════════════════════════════════════════════════════════
    # 公共接口
    # ═══════════════════════════════════════════════════════════════════════════

    def fight(self, initial_ship_stats: list[int] | None = None) -> CombatResult:
        """执行一次完整的战斗循环。

        从当前状态开始，循环执行:
        ``update_state → make_decision`` 直到战斗结束或 SL。

        Parameters
        ----------
        initial_ship_stats:
            初始血量状态（来自出征准备页面的检测结果）。

        Returns
        -------
        CombatResult
        """
        self._reset()
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

                def _speed_up() -> None:
                    click_speed_up(self._device, battle_mode=False)

                return _speed_up

        elif self._plan.mode == CombatMode.BATTLE:
            if last_phase == CombatPhase.PROCEED:

                def _speed_up_battle() -> None:
                    click_speed_up(self._device, battle_mode=True)

                return _speed_up_battle

        return None

    def _after_match(self, phase: CombatPhase) -> None:
        """匹配到状态后的信息收集。"""
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


# ═══════════════════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════════════════


def run_combat(
    device: AndroidController,
    plan: CombatPlan,
    image_matcher: ImageMatcherFunc,
    *,
    ship_stats: list[int] | None = None,
    get_enemy_info: GetEnemyInfoFunc | None = None,
    get_enemy_formation: GetEnemyFormationFunc | None = None,
    detect_ship_stats: DetectShipStatsFunc | None = None,
    detect_result_grade: DetectResultGradeFunc | None = None,
    get_ship_drop: GetShipDropFunc | None = None,
    image_exist: ImageExistFunc | None = None,
    click_image: ClickImageFunc | None = None,
) -> CombatResult:
    """执行一次完整战斗的便捷函数。"""
    engine = CombatEngine(
        device=device,
        plan=plan,
        image_matcher=image_matcher,
        get_enemy_info=get_enemy_info,
        get_enemy_formation=get_enemy_formation,
        detect_ship_stats=detect_ship_stats,
        detect_result_grade=detect_result_grade,
        get_ship_drop=get_ship_drop,
        image_exist=image_exist,
        click_image=click_image,
    )
    return engine.fight(initial_ship_stats=ship_stats)
