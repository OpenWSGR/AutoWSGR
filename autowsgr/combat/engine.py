"""战斗引擎 — 状态机主循环。
"""

from __future__ import annotations

import time

from loguru import logger

from .actions import (
    click_speed_up,
    detect_result_grade,
    detect_ship_stats,
    get_enemy_formation,
    get_enemy_info,
)
from .callbacks import CombatResult
from .handlers import PhaseHandlersMixin
from .history import CombatEvent, CombatHistory, EventType, FightResult
from .node_tracker import MapNodeData, NodeTracker
from .plan import CombatMode, CombatPlan, NodeDecision
from .recognizer import (
    CombatRecognitionTimeout,
    CombatRecognizer,
)
from .state import CombatPhase, resolve_successors
from autowsgr.types import ConditionFlag, Formation, ShipDamageState


from autowsgr.emulator import AndroidController
from autowsgr.vision import ImageChecker, OCREngine


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════════════════════


def _dismiss_resource_confirm(device: AndroidController) -> None:
    """检测并关闭地图移动中弹出的资源获取/失去确认弹窗。

    Legacy ``_before_match`` 在每轮轮询中用 ``confirm_image[3]`` 快速探测，
    命中后调用 ``confirm_operation()`` 点掉。此处等价实现：仅对当前帧做
    一次快速检测（不阻塞等待），找到任意确认按钮模板就点击。
    """
    from autowsgr.image_resources import Templates

    screen = device.screenshot()
    detail = ImageChecker.find_any(
        screen, Templates.Confirm.all(), confidence=0.8,
    )
    if detail is not None:
        device.click(*detail.center)
        logger.info(
            "[Combat] 点掉资源确认弹窗: '{}' ({:.4f}, {:.4f})",
            detail.template_name, *detail.center,
        )
        time.sleep(0.25)


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
        self._ship_stats: list[ShipDamageState] = [ShipDamageState.NORMAL] * 6
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
        initial_ship_stats: list[ShipDamageState] | None = None,
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
            elif decision == ConditionFlag.DOCK_FULL:
                logger.warning("战斗进入失败：船坞已满")
                result.flag = ConditionFlag.DOCK_FULL
                break
            elif decision == ConditionFlag.SL:
                # TODO: 这里出现了轻微的抽象泄露，因为 SL 需要调用 restart_game
                result.flag = ConditionFlag.SL
                from autowsgr.ops import restart_game
                restart_game(self._device)
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
            self._phase = CombatPhase.START_FIGHT
            self._last_action = "yes"
        elif self._plan.mode in [CombatMode.BATTLE, CombatMode.EXERCISE]:
            self._phase = CombatPhase.START_FIGHT
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

        # 构建轮询间动作（加速点击 + 节点追踪）
        poll_action = self._get_poll_action(last_phase)

        new_phase = self._recognizer.wait_for_phase(
            candidates,
            poll_action=poll_action,
        )

        self._phase = new_phase
        self._after_match(new_phase)
        return new_phase

    def _get_poll_action(self, last_phase: CombatPhase):
        """根据当前状态和模式，返回每轮匹配前执行的动作。

        NORMAL 模式下，在地图移动期间（``PROCEED`` / ``FIGHT_CONDITION`` /
        迂回后）除了加速点击和节点追踪外，还会检测因获取/失去资源而
        弹出的确认弹窗并点掉，与 Legacy ``_before_match`` 行为一致。
        """
        if self._plan.mode == CombatMode.NORMAL:
            if last_phase in (
                CombatPhase.PROCEED,
                CombatPhase.FIGHT_CONDITION,
            ) or self._last_action == "detour":
                tracker = self._tracker
                device = self._device

                def _speed_up() -> None:
                    click_speed_up(device, battle_mode=False)
                    # 在地图移动期间追踪船位并更新节点
                    if tracker is not None:
                        screen = device.screenshot()
                        tracker.update_ship_position(screen)
                        new_node = tracker.update_node()
                        if new_node != self._node:
                            self._node = new_node

                    # 检测地图移动中弹出的资源确认弹窗并点掉
                    _dismiss_resource_confirm(device)

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
            self._enemies = get_enemy_info(self._device, mode="exercise" if self._plan.mode == CombatMode.EXERCISE else "fight")
            self._enemy_formation = get_enemy_formation(self._device, self._ocr)
            logger.info("敌方编成: {} 阵型: {}", self._enemies, self._enemy_formation)

        elif phase == CombatPhase.RESULT:
            grade = detect_result_grade(self._device)
            self._ship_stats = detect_ship_stats(self._device, self._ship_stats)
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
    *,
    ship_stats: list[ShipDamageState] | None = None,
) -> CombatResult:
    """执行一次完整战斗的便捷函数。"""
    engine = CombatEngine(device=device)
    return engine.fight(plan, initial_ship_stats=ship_stats)
