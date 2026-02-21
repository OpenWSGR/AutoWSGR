"""战斗状态处理器 — 各状态节点的决策逻辑。

``PhaseHandlersMixin`` 为 :class:`~autowsgr.combat.engine.CombatEngine`
提供各阶段的处理器方法（``_handle_*``），
将决策逻辑从主循环中分离以降低文件复杂度。

每个 ``_handle_*`` 方法对应一个 :class:`~autowsgr.combat.state.CombatPhase`，
执行该阶段所需的决策和操作，并返回 :class:`~autowsgr.types.ConditionFlag`
指示引擎是否继续循环。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from autowsgr.combat.actions import (
    check_blood,
    click_enter_fight,
    click_fight_condition,
    click_formation,
    click_image,
    click_night_battle,
    click_proceed,
    click_result,
    click_retreat,
    click_skip_missile_animation,
    get_ship_drop,
    image_exist,
)
from autowsgr.combat.history import CombatEvent, EventType, FightResult
from autowsgr.combat.plan import CombatMode, NodeDecision
from autowsgr.combat.rules import RuleResult
from autowsgr.combat.state import CombatPhase
from autowsgr.types import ConditionFlag, Formation

if TYPE_CHECKING:
    from autowsgr.combat.history import CombatHistory
    from autowsgr.combat.plan import CombatPlan
    from autowsgr.emulator.controller import AndroidController


class PhaseHandlersMixin:
    """战斗状态处理器 Mixin。

    为 ``CombatEngine`` 提供 ``_make_decision`` 及所有 ``_handle_*`` 方法。

    约定: 本 Mixin 假设宿主类具有以下属性::

        _device: AndroidController
        _plan: CombatPlan
        _node: str
        _last_action: str
        _ship_stats: list[int]
        _enemies: dict[str, int]
        _enemy_formation: str
        _history: CombatHistory
        _node_count: int
        _formation_by_rule: Formation | None
    """

    # 类型提示 (供 IDE/mypy 在 Mixin 上下文使用)
    _device: AndroidController
    _plan: CombatPlan
    _node: str
    _last_action: str
    _ship_stats: list[int]
    _enemies: dict[str, int]
    _enemy_formation: str
    _history: CombatHistory
    _node_count: int
    _formation_by_rule: Formation | None

    def _make_decision(self, phase: CombatPhase) -> ConditionFlag:
        """根据当前状态做出决策并执行操作。

        这是旧代码中 ``NormalFightPlan._make_decision()`` 与
        ``DecisionBlock.make_decision()`` 的统一重写。

        Parameters
        ----------
        phase:
            当前识别到的战斗状态。

        Returns
        -------
        ConditionFlag
        """
        # ── 终止状态 ──
        end_phase = self._plan.end_phase
        if phase == end_phase:
            self._history.add(CombatEvent(
                event_type=EventType.AUTO_RETURN,
                node=self._node,
                action="正常",
            ))
            return ConditionFlag.FIGHT_END

        # ── 各状态决策 ──

        if phase == CombatPhase.FIGHT_CONDITION:
            return self._handle_fight_condition()

        if phase == CombatPhase.SPOT_ENEMY_SUCCESS:
            return self._handle_spot_enemy()

        if phase == CombatPhase.FORMATION:
            return self._handle_formation()

        if phase == CombatPhase.MISSILE_ANIMATION:
            return self._handle_missile_animation()

        if phase == CombatPhase.FIGHT_PERIOD:
            return self._handle_fight_period()

        if phase == CombatPhase.NIGHT_PROMPT:
            return self._handle_night_prompt()

        if phase == CombatPhase.RESULT:
            return self._handle_result()

        if phase == CombatPhase.GET_SHIP:
            return self._handle_get_ship()

        if phase == CombatPhase.PROCEED:
            return self._handle_proceed()

        if phase == CombatPhase.FLAGSHIP_SEVERE_DAMAGE:
            return self._handle_flagship_severe_damage()

        logger.error("未知状态: {}", phase.name)
        return ConditionFlag.SL

    # ── 各状态处理器 ─────────────────────────────────────────────────────────

    def _handle_fight_condition(self) -> ConditionFlag:
        """处理战况选择。
        TODO: 需测试
        """
        condition = self._plan.fight_condition
        click_fight_condition(self._device, condition)
        self._last_action = str(condition.value)

        self._history.add(CombatEvent(
            event_type=EventType.FIGHT_CONDITION,
            node=self._node,
            action=str(condition.value),
        ))
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_spot_enemy(self) -> ConditionFlag:
        """处理索敌成功 — 核心决策节点。

        决策顺序:
        1. 检查节点是否在白名单中
        2. 检查阵型规则 (formation_rules)
        3. 检查敌舰规则 (enemy_rules)
        4. 根据结果执行: 撤退 / 迂回 / 设置阵型 / 进入战斗
        """
        decision = self._get_current_decision()

        # 白名单检查
        if not self._plan.is_selected_node(self._node):
            click_retreat(self._device)
            self._last_action = "retreat"
            self._history.add(CombatEvent(
                event_type=EventType.SPOT_ENEMY,
                node=self._node,
                action="撤退",
                extra={"reason": "不在预设点"},
            ))
            return ConditionFlag.FIGHT_END

        # 检查迂回按钮是否可用
        can_detour = image_exist(self._device, "bypass", 0.8)
        want_detour = can_detour and decision.detour

        # 阵型规则优先
        rule_action = None
        if decision.formation_rules and self._enemy_formation:
            rule_action = decision.formation_rules.evaluate_formation(
                self._enemy_formation
            )

        # 敌舰规则
        if rule_action is None or rule_action.result == RuleResult.NO_ACTION:
            if decision.enemy_rules:
                rule_action = decision.enemy_rules.evaluate(self._enemies)

        # 应用规则结果
        if rule_action is not None:
            if rule_action.result == RuleResult.RETREAT:
                click_retreat(self._device)
                self._last_action = "retreat"
                self._history.add(CombatEvent(
                    event_type=EventType.SPOT_ENEMY,
                    node=self._node,
                    action="撤退",
                    enemies=self._enemies.copy(),
                ))
                return ConditionFlag.FIGHT_END

            if rule_action.result == RuleResult.DETOUR:
                if not can_detour:
                    logger.error("规则指定迂回, 但该点无法迂回")
                    raise ValueError("该点无法迂回, 但在规则中指定了迂回")
                want_detour = True

            if rule_action.result == RuleResult.FORMATION and rule_action.formation:
                self._formation_by_rule = rule_action.formation

        # 执行迂回
        if want_detour:
            clicked = click_image(self._device, "bypass", 2.5)
            if clicked:
                logger.info("执行迂回")
            else:
                logger.warning("未找到迂回按钮")
            self._last_action = "detour"
            self._history.add(CombatEvent(
                event_type=EventType.SPOT_ENEMY,
                node=self._node,
                action="迂回",
                enemies=self._enemies.copy(),
            ))
            return ConditionFlag.FIGHT_CONTINUE

        # 远程导弹支援
        if decision.long_missile_support:
            clicked = click_image(self._device, "missile_support", 2.5)
            if clicked:
                logger.info("开启远程导弹支援")
            else:
                logger.warning("未找到远程支援按钮")

        # 进入战斗
        click_enter_fight(self._device)
        self._last_action = "fight"
        self._history.add(CombatEvent(
            event_type=EventType.SPOT_ENEMY,
            node=self._node,
            action="战斗",
            enemies=self._enemies.copy(),
        ))
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_formation(self) -> ConditionFlag:
        """处理阵型选择。"""
        decision = self._get_current_decision()
        is_from_spot_enemy = self._last_action in ("fight", "detour")

        # 白名单检查
        if not self._plan.is_selected_node(self._node):
            self._history.add(CombatEvent(
                event_type=EventType.FORMATION,
                node=self._node,
                action="SL",
                extra={"reason": "不在预设点"},
            ))
            return ConditionFlag.SL

        # 迂回失败 SL
        if is_from_spot_enemy and self._last_action == "detour":
            if decision.SL_when_detour_fails:
                self._history.add(CombatEvent(
                    event_type=EventType.DETOUR,
                    node=self._node,
                    result="失败",
                ))
                self._history.add(CombatEvent(
                    event_type=EventType.FORMATION,
                    node=self._node,
                    action="SL",
                ))
                return ConditionFlag.SL

        # 确定阵型
        formation = decision.formation

        if is_from_spot_enemy and self._formation_by_rule is not None:
            formation = self._formation_by_rule
            self._formation_by_rule = None
            logger.debug("使用规则阵型: {}", formation.name)
        elif not is_from_spot_enemy:
            # 索敌失败
            if decision.SL_when_spot_enemy_fails:
                self._history.add(CombatEvent(
                    event_type=EventType.FORMATION,
                    node=self._node,
                    action="SL",
                    extra={"reason": "索敌失败"},
                ))
                return ConditionFlag.SL
            if decision.formation_when_spot_enemy_fails is not None:
                formation = decision.formation_when_spot_enemy_fails

        # 选择阵型
        click_formation(self._device, formation)

        self._last_action = str(formation.value)
        self._history.add(CombatEvent(
            event_type=EventType.FORMATION,
            node=self._node,
            action=f"阵型{formation.value} ({formation.name})",
            enemies=self._enemies.copy() if self._enemies else None,
        ))
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_missile_animation(self) -> ConditionFlag:
        """跳过导弹支援动画。"""
        logger.info("跳过导弹支援动画")
        click_skip_missile_animation(self._device)
        self._last_action = "skip_animation"
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_fight_period(self) -> ConditionFlag:
        """处理战斗进行中。"""
        decision = self._get_current_decision()
        if decision.SL_when_enter_fight:
            self._history.add(CombatEvent(
                event_type=EventType.ENTER_FIGHT,
                node=self._node,
                action="SL",
            ))
            return ConditionFlag.SL
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_night_prompt(self) -> ConditionFlag:
        """处理夜战选择。"""
        decision = self._get_current_decision()
        pursue = decision.night

        click_night_battle(self._device, pursue=pursue)
        self._last_action = "yes" if pursue else "no"

        self._history.add(CombatEvent(
            event_type=EventType.NIGHT_BATTLE,
            node=self._node,
            action="追击" if pursue else "撤退",
        ))
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_result(self) -> ConditionFlag:
        """处理战果结算。
        TODO: 增强可靠性
        """
        time.sleep(1)  # 等待结算界面完全加载
        click_result(self._device)
        time.sleep(0.25)
        click_result(self._device)  # 二次点击以关闭结算界面
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_get_ship(self) -> ConditionFlag:
        """处理获取舰船。"""
        ship_name = get_ship_drop(self._device)
        if ship_name:
            logger.info("获得舰船: {}", ship_name)

        self._history.add(CombatEvent(
            event_type=EventType.GET_SHIP,
            node=self._node,
            result=ship_name or "",
        ))
        click_result(self._device)
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_proceed(self) -> ConditionFlag:
        """处理继续前进 / 回港决策。

        决策依据:
        1. 当前节点的 ``proceed`` 配置
        2. 血量是否满足 ``proceed_stop`` 条件
        """
        self._node_count += 1
        decision = self._get_current_decision()

        should_proceed = decision.proceed and check_blood(
            self._ship_stats, decision.proceed_stop
        )

        click_proceed(self._device, go_forward=should_proceed)
        self._last_action = "yes" if should_proceed else "no"

        self._history.add(CombatEvent(
            event_type=EventType.PROCEED,
            node=self._node,
            action="前进" if should_proceed else "回港",
            ship_stats=self._ship_stats[:],
        ))

        if should_proceed:
            return ConditionFlag.FIGHT_CONTINUE
        return ConditionFlag.FIGHT_END

    def _handle_flagship_severe_damage(self) -> ConditionFlag:
        """处理旗舰大破。"""
        click_image(self._device, "flagship_damage", 2.0)
        time.sleep(0.25)

        self._history.add(CombatEvent(
            event_type=EventType.FLAGSHIP_DAMAGE,
            node=self._node,
            action="回港",
        ))
        return ConditionFlag.FIGHT_END

    # ── Mixin 所需的方法签名 (由宿主类提供) ──

    def _get_current_decision(self) -> NodeDecision:
        """获取当前节点的决策 (由 CombatEngine 实现)。"""
        raise NotImplementedError
