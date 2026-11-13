"""战斗引擎 — 状态机主循环。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.combat.actions import click_speed_up, dismiss_resource_confirm
from autowsgr.combat.handlers import PhaseHandlersMixin
from autowsgr.combat.history import CombatHistory, CombatResult
from autowsgr.combat.plan import MODE_CATEGORIES, CombatMode, CombatPlan, NodeDecision
from autowsgr.combat.recognizer import (
    CombatRecognitionTimeoutError,
    CombatRecognizer,
    CombatStopRequestedError,
)
from autowsgr.combat.state import CombatPhase, ModeCategory, resolve_successors
from autowsgr.emulator.frame import CapturedFrame
from autowsgr.infra.logger import get_logger
from autowsgr.types import ConditionFlag, Formation, ShipDamageState


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np

    from autowsgr.combat.node_fusion.enemy import EnemyObservation
    from autowsgr.combat.node_fusion.integration import TrackingSession
    from autowsgr.context import GameContext


_log = get_logger('combat')
_log_sm = get_logger('combat.engine')  # 状态机转移专用，可单独静默


# ═══════════════════════════════════════════════════════════════════════════════
# 战斗引擎
# ═══════════════════════════════════════════════════════════════════════════════


class CombatEngine(PhaseHandlersMixin):
    """自包含的战斗状态机引擎。

    引擎内部自行完成图像匹配、敌方编成/阵型识别、战果等级检测等，
    无需外部注入回调函数，沿袭旧代码 ``Timer`` 内置识别能力的设计。

    参数
    ----------
    device:
        设备控制器 (截图 + 触控)。
    ocr:
        OCR 引擎实例 (阵型识别用)。可选，为 ``None`` 则跳过阵型识别。
    """

    def __init__(
        self,
        ctx: GameContext,
    ) -> None:
        self._ctx = ctx
        self._device = ctx.ctrl
        self._ocr = ctx.ocr

        # 运行时状态 (由 fight() 重置)
        self._plan: CombatPlan = CombatPlan(name='', mode=CombatMode.BATTLE)
        self._recognizer: CombatRecognizer = None  # type: ignore[assignment]  # 在 fight() 中初始化
        self._phase = CombatPhase.PROCEED
        self._last_action = 'yes'
        self._node = '0'
        self._ship_stats: list[ShipDamageState] = [ShipDamageState.NORMAL] * 6
        self._history = CombatHistory()
        self._node_count = 0

        # 节点级临时状态
        self._formation_by_rule: Formation | None = None
        self._tracking: TrackingSession | None = None

    # ═══════════════════════════════════════════════════════════════════════════
    # 公共接口
    # ═══════════════════════════════════════════════════════════════════════════

    def fight(
        self,
        plan: CombatPlan,
        initial_ship_stats: list[ShipDamageState],
        *,
        tracking_session: TrackingSession | None = None,
    ) -> CombatResult:
        """执行一次完整的战斗循环。

        从当前状态开始，循环执行:
        ``update_state → make_decision`` 直到战斗结束或 SL。

        参数
        ----------
        plan:
            作战计划 (阵型、夜战、节点决策等)。
        initial_ship_stats:
            初始血量状态（来自出征准备页面的检测结果）。
        tracking_session:
            外层持有的地图会话；单场结束时保留其历史，由拥有者结束整个会话。

        返回
        -------
        CombatResult
        """
        self._plan = plan
        self._recognizer = CombatRecognizer(
            self._ctx,
        )
        self._reset()

        if tracking_session is None:
            self._start_tracking()
        else:
            self._tracking = tracking_session
            self._apply_tracking_node()
        if initial_ship_stats is not None:
            self._ship_stats = initial_ship_stats[:]

        result = CombatResult(history=self._history)

        while True:
            try:
                decision = self._step()
            except CombatStopRequestedError:
                _log.info('[Combat] 收到停止请求，正在退出战斗')
                result.flag = ConditionFlag.FIGHT_END
                break
            except CombatRecognitionTimeoutError as e:
                _log.warning('[Combat] 状态识别超时: {}', e)
                if self._try_recovery():
                    continue
                result.flag = ConditionFlag.SL
                break

            if decision == ConditionFlag.FIGHT_CONTINUE:
                continue
            elif decision == ConditionFlag.DOCK_FULL:
                _log.warning('[Combat] 战斗进入失败：船坞已满')
                result.flag = ConditionFlag.DOCK_FULL
                break
            elif decision == ConditionFlag.SL:
                # TODO: 这里出现了轻微的抽象泄露，因为 SL 需要调用 restart_game
                result.flag = ConditionFlag.SL
                from autowsgr.ops import restart_game

                restart_game(self._device)
                break
            elif decision == ConditionFlag.FIGHT_END:
                _log.debug('[Combat] 战斗已结束，日志: {}', self._history)
                result.flag = ConditionFlag.OPERATION_SUCCESS
                break

        if tracking_session is None:
            self._tracking_action('end')
        result.ship_stats = self._ship_stats[:]
        result.node_count = self._node_count
        _log.info(
            '[Combat] 战斗结束: {} (节点数={})',
            result.flag.value,
            result.node_count,
        )
        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════════════════════
    def _is_map_routing_phase(self, last_phase: CombatPhase) -> bool:
        return (
            last_phase
            in (CombatPhase.PROCEED, CombatPhase.FIGHT_CONDITION, CombatPhase.START_FIGHT)
            or self._last_action == 'detour'
        )

    def _reset(self) -> None:
        """重置运行时状态。"""
        self._history.reset()
        self._node = '0'
        self._node_count = 0
        self._formation_by_rule = None
        self._tracking = None

        self._phase = CombatPhase.START_FIGHT
        self._last_action = ''

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

        _log_sm.debug(
            '[Combat] 当前: {} (action={}) → 候选: {}',
            last_phase.name,
            self._last_action,
            [c.name for c in candidates],
        )

        # 构建轮询间动作（加速点击 + 节点追踪）
        poll_action = self._get_poll_action(last_phase)
        new_phase = self._recognizer.wait_for_phase(
            candidates,
            poll_action=poll_action,
        )

        self._phase = new_phase
        return new_phase

    def _get_poll_action(self, last_phase: CombatPhase) -> Callable[[np.ndarray], None] | None:
        """根据当前状态和模式大类，返回每轮匹配前执行的动作。

        MAP 模式下，地图移动期间执行加速点击、节点追踪、资源弹窗点掉；
        SINGLE 模式下仅加速点击。
        """
        category = MODE_CATEGORIES.get(self._plan.mode)
        if self._phase is CombatPhase.FIGHT_PERIOD:
            return lambda _: time.sleep(0.5)
        if category is ModeCategory.MAP:
            if self._is_map_routing_phase(last_phase):
                device = self._device

                def _poll_map(screen: np.ndarray) -> None:
                    click_speed_up(device)
                    self._tracking_motion(screen)
                    dismiss_resource_confirm(device, screen)

                return _poll_map

        elif category is ModeCategory.SINGLE and last_phase is CombatPhase.START_FIGHT:

            def _poll_single(_: np.ndarray) -> None:
                click_speed_up(self._device)

            return _poll_single

        return None

    def _start_tracking(self) -> None:
        from autowsgr.combat.node_fusion.integration import TrackingSession

        self._tracking = TrackingSession.start(
            self._plan,
            self._ctx.config.log.dir,
            record_replay=self._ctx.config.log.node_fusion_replay,
        )
        if self._tracking is not None:
            self._node = '0'

    def _tracking_motion(self, screen: np.ndarray) -> None:
        if self._tracking is not None:
            frame = getattr(self._recognizer, 'last_frame', None)
            if isinstance(frame, CapturedFrame) and frame.image is screen:
                self._tracking.motion(frame, self._node)

    def _apply_tracking_node(self) -> None:
        if self._tracking is None:
            return
        node = self._tracking.current_node
        if node != self._node:
            _log.info('[NodeFusion] 决策节点: {} → {}', self._node, node)
            self._formation_by_rule = None
        elif self._tracking.phase_is_new_encounter:
            self._formation_by_rule = None
        self._node = node

    def _tracking_phase(
        self,
        phase: CombatPhase,
        *,
        frame: CapturedFrame | None = None,
        enemies: EnemyObservation | None = None,
    ) -> None:
        if self._tracking is not None:
            if frame is None:
                frame = getattr(self._recognizer, 'last_match', None)
            self._tracking.phase(phase, frame, self._node, enemies)
            self._apply_tracking_node()

    def _tracking_enemy_observation(self, mode: str) -> EnemyObservation | None:
        if self._tracking is None:
            return None
        evidence = self._tracking.enemy_observation(
            getattr(self._recognizer, 'last_match', None),
            self._ocr,
            mode,
            self._node,
            capture=getattr(self._recognizer, 'capture_frame', None),
        )
        self._apply_tracking_node()
        return evidence

    def _tracking_action(
        self,
        action: str,
        *,
        clicked: bool | None = None,
        page_left: bool | None = None,
        timestamp: float | None = None,
    ) -> None:
        if self._tracking is not None:
            self._tracking.action(
                action,
                self._phase,
                self._node,
                clicked=clicked,
                page_left=page_left,
                timestamp=timestamp,
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_current_decision(self) -> NodeDecision:
        """获取当前节点的决策。"""
        if (
            self._plan.mode == CombatMode.DECISIVE
            and self._node == '0'
            and self._tracking is not None
            and self._tracking.estimate is not None
        ):
            decisions = [
                self._plan.get_node_decision(node)
                for node, weight in self._tracking.estimate.node_weights.items()
                if weight > 0 and node in self._plan.nodes
            ]
            if decisions and all(decision == decisions[0] for decision in decisions):
                return decisions[0]
        return self._plan.get_node_decision(self._node)

    def _try_recovery(self) -> bool:
        """尝试从错误中恢复。"""
        _log.warning('[Combat] 尝试错误恢复...')
        time.sleep(3.0)

        screen = self._device.screenshot()
        end_phase = self._plan.end_phase

        # 恢复判据不只看终态页: 若页面其实停在当前状态的某个合法后继上
        # (典型: 战果页点击穿透到掉落页/经验页), 认出来就能接着跑, 不必
        # 判 SL 重开整局 —— 那会丢掉刚打完的这一局战果。
        candidates: list[CombatPhase] = []
        if end_phase is not None:
            candidates.append(end_phase)
        for phase in resolve_successors(self._plan.transitions, self._phase, self._last_action):
            if phase not in candidates:
                candidates.append(phase)

        result = self._recognizer.identify_current(screen, candidates)
        if result is not None:
            _log.warning('[Combat] 错误恢复: 识别到 {}, 继续战斗', result.name)
            self._phase = result
            return True
        return False

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
    ctx: GameContext,
    plan: CombatPlan,
    *,
    ship_stats: list[ShipDamageState],
    tracking_session: TrackingSession | None = None,
) -> CombatResult:
    """执行一次完整战斗的便捷函数。"""
    engine = CombatEngine(ctx=ctx)
    return engine.fight(plan, initial_ship_stats=ship_stats, tracking_session=tracking_session)
