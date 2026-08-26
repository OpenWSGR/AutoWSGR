"""战斗状态处理器 — 各状态节点的决策逻辑。


每个 ``_handle_*`` 方法对应一个 :class:`~autowsgr.combat.state.CombatPhase`，
执行该阶段所需的决策和操作，并返回 :class:`~autowsgr.types.ConditionFlag`
指示引擎是否继续循环。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

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
    detect_result_grade,
    detect_ship_stats,
    get_enemy_formation,
    get_enemy_info,
    get_ship_drop,
    image_exist,
)
from autowsgr.combat.recognition import detect_mvp
from autowsgr.image_resources import TemplateKey
from autowsgr.infra.logger import get_logger
from autowsgr.types import ConditionFlag, Formation, ShipDamageState
from autowsgr.ui.utils import wait_leave_page
from autowsgr.vision import ImageChecker

from .history import CombatEvent, CombatHistory, EventType, FightResult
from .plan import CombatMode, CombatPlan, NodeDecision
from .rules import RuleResult
from .state import CombatPhase


if TYPE_CHECKING:
    from autowsgr.combat.recognizer import CombatRecognizer
    from autowsgr.emulator import AndroidController
    from autowsgr.vision import OCREngine


_log = get_logger('combat')


# ── 状态 → 处理器方法名映射  ────────────────────────────────────────────────

_PHASE_HANDLERS: dict[CombatPhase, str] = {
    CombatPhase.FIGHT_CONDITION: '_handle_fight_condition',
    CombatPhase.SPOT_ENEMY_SUCCESS: '_handle_spot_enemy',
    CombatPhase.FORMATION: '_handle_formation',
    CombatPhase.MISSILE_ANIMATION: '_handle_missile_animation',
    CombatPhase.FIGHT_PERIOD: '_handle_fight_period',
    CombatPhase.NIGHT_PROMPT: '_handle_night_prompt',
    CombatPhase.RESULT: '_handle_result',
    CombatPhase.EXP_SETTLEMENT: '_handle_exp_settlement',
    CombatPhase.GET_SHIP: '_handle_get_ship',
    CombatPhase.PROCEED: '_handle_proceed',
    CombatPhase.FLAGSHIP_SEVERE_DAMAGE: '_handle_flagship_severe_damage',
    CombatPhase.DOCK_FULL: '_handle_dock_full',
}


class PhaseHandlersMixin:
    """战斗状态处理器 Mixin。

    为 ``CombatEngine`` 提供 ``_make_decision`` 及所有 ``_handle_*`` 方法。

    约定: 本 Mixin 假设宿主类具有以下属性::

        _device: AndroidController
        _plan: CombatPlan
        _ocr: OCREngine | None
        _node: str
        _last_action: str
        _ship_stats: list[ShipDamageState]
        _history: CombatHistory
        _node_count: int
        _formation_by_rule: Formation | None
        _recognizer: CombatRecognizer
    """

    # 类型提示 (供 IDE/mypy 在 Mixin 上下文使用)
    _device: AndroidController
    _plan: CombatPlan
    _ocr: OCREngine | None
    _node: str
    _last_action: str
    _ship_stats: list[ShipDamageState]
    _history: CombatHistory
    _recognizer: CombatRecognizer
    _node_count: int
    _formation_by_rule: Formation | None

    def _make_decision(self, phase: CombatPhase) -> ConditionFlag:
        """根据当前状态做出决策并执行操作。

        每个状态通过 ``_PHASE_HANDLERS`` 映射到对应的处理器方法；
        处理器执行完毕后，若当前状态是终止阶段则返回 ``FIGHT_END``。

        Parameters
        ----------
        phase:
            当前识别到的战斗状态。

        Returns
        -------
        ConditionFlag
        """
        # ── 派发处理器 ──
        handler_name = _PHASE_HANDLERS.get(phase)
        if handler_name is not None:
            result = getattr(self, handler_name)()
        else:
            result = ConditionFlag.FIGHT_CONTINUE

        # ── 终止态检查 ──
        if phase == self._plan.end_phase:
            self._history.add(
                CombatEvent(
                    event_type=EventType.AUTO_RETURN,
                    node=self._node,
                    action='正常',
                )
            )
            return ConditionFlag.FIGHT_END

        return result

    # ── 各状态处理器 ─────────────────────────────────────────────────────────

    def _handle_fight_condition(self) -> ConditionFlag:
        """处理战况选择。
        TODO: 需测试
        """
        condition = self._plan.fight_condition
        click_fight_condition(self._device, condition)
        self._last_action = str(condition.value)

        self._history.add(
            CombatEvent(
                event_type=EventType.FIGHT_CONDITION,
                node=self._node,
                action=str(condition.value),
            )
        )
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_spot_enemy(self) -> ConditionFlag:  # noqa: PLR0912
        """处理索敌成功 — 核心决策节点。

        决策顺序:
        1. 采集敌方编成和阵型
        2. 检查节点是否在白名单中
        3. 检查阵型规则 (formation_rules)
        4. 检查敌舰规则 (enemy_rules)
        5. 根据结果执行: 撤退 / 迂回 / 设置阵型 / 进入战斗
        """
        # ── 信息采集 ──
        mode = 'exercise' if self._plan.mode == CombatMode.EXERCISE else 'fight'
        enemies = get_enemy_info(self._device, mode=mode)
        enemy_formation = get_enemy_formation(self._device, self._ocr)
        _log.info('[Combat] 敌方编成: {} 阵型: {}', enemies, enemy_formation)

        decision = self._get_current_decision()

        # 白名单检查
        if not self._plan.is_selected_node(self._node):
            click_retreat(self._device)
            self._last_action = 'retreat'
            self._history.add(
                CombatEvent(
                    event_type=EventType.SPOT_ENEMY,
                    node=self._node,
                    action='撤退',
                    extra={'reason': '不在预设点'},
                )
            )
            return ConditionFlag.FIGHT_END

        # 检查迂回按钮是否可用
        can_detour = image_exist(self._device, TemplateKey.BYPASS, 0.8)
        want_detour = can_detour and decision.detour

        # 阵型规则优先
        rule_action = None
        if decision.formation_rules and enemy_formation:
            rule_action = decision.formation_rules.evaluate_formation(enemy_formation)

        # 敌舰规则
        if (
            rule_action is None or rule_action.result == RuleResult.NO_ACTION
        ) and decision.enemy_rules:
            rule_action = decision.enemy_rules.evaluate(enemies)

        # 应用规则结果
        if rule_action is not None:
            if rule_action.result == RuleResult.RETREAT:
                click_retreat(self._device)
                self._last_action = 'retreat'
                self._history.add(
                    CombatEvent(
                        event_type=EventType.SPOT_ENEMY,
                        node=self._node,
                        action='撤退',
                        enemies=enemies.copy(),
                    )
                )
                return ConditionFlag.FIGHT_END

            if rule_action.result == RuleResult.DETOUR:
                if not can_detour:
                    _log.error('[Combat] 规则指定迂回, 但该点无法迂回')
                    raise ValueError('该点无法迂回, 但在规则中指定了迂回')
                want_detour = True

            if rule_action.result == RuleResult.FORMATION and rule_action.formation:
                self._formation_by_rule = rule_action.formation

        # 执行迂回
        if want_detour:
            clicked = click_image(self._device, TemplateKey.BYPASS, 2.5)
            if clicked:
                _log.info('[Combat] 执行迂回')
                spot_templates = TemplateKey.SPOT_ENEMY.templates
                wait_leave_page(
                    self._device,
                    checker=lambda screen: (
                        ImageChecker.find_any(screen, spot_templates, confidence=0.8) is not None
                    ),
                    timeout=10.0,
                    source='spot_enemy_success',
                    target='map_routing',
                )
            else:
                _log.warning('[Combat] 未找到迂回按钮')
            self._last_action = 'detour'
            self._history.add(
                CombatEvent(
                    event_type=EventType.SPOT_ENEMY,
                    node=self._node,
                    action='迂回',
                    enemies=enemies.copy(),
                )
            )
            return ConditionFlag.FIGHT_CONTINUE

        # 远程导弹支援
        if decision.long_missile_support:
            clicked = click_image(self._device, TemplateKey.MISSILE_SUPPORT, 2.5)
            if clicked:
                _log.info('[Combat] 开启远程导弹支援')
            else:
                _log.warning('[Combat] 未找到远程支援按钮')

        # 进入战斗
        click_enter_fight(self._device)
        self._last_action = 'fight'
        self._history.add(
            CombatEvent(
                event_type=EventType.SPOT_ENEMY,
                node=self._node,
                action='战斗',
                enemies=enemies.copy(),
            )
        )
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_formation(self) -> ConditionFlag:
        """处理阵型选择。"""
        decision = self._get_current_decision()
        is_from_spot_enemy = self._last_action in ('fight', 'detour')

        # 白名单检查
        if not self._plan.is_selected_node(self._node):
            self._history.add(
                CombatEvent(
                    event_type=EventType.FORMATION,
                    node=self._node,
                    action='SL',
                    extra={'reason': '不在预设点'},
                )
            )
            return ConditionFlag.SL

        # 迂回失败 SL
        if is_from_spot_enemy and self._last_action == 'detour' and decision.SL_when_detour_fails:
            self._history.add(
                CombatEvent(
                    event_type=EventType.DETOUR,
                    node=self._node,
                    result='失败',
                )
            )
            self._history.add(
                CombatEvent(
                    event_type=EventType.FORMATION,
                    node=self._node,
                    action='SL',
                )
            )
            return ConditionFlag.SL

        # 确定阵型
        formation = decision.formation

        if is_from_spot_enemy and self._formation_by_rule is not None:
            formation = self._formation_by_rule
            self._formation_by_rule = None
            _log.debug('[Combat] 使用规则阵型: {}', formation.name)
        elif not is_from_spot_enemy:
            # 索敌失败
            if decision.SL_when_spot_enemy_fails:
                self._history.add(
                    CombatEvent(
                        event_type=EventType.FORMATION,
                        node=self._node,
                        action='SL',
                        extra={'reason': '索敌失败'},
                    )
                )
                return ConditionFlag.SL
            if decision.formation_when_spot_enemy_fails is not None:
                formation = decision.formation_when_spot_enemy_fails

        # 选择阵型
        _log.info('[Combat] 阵型选择: {}', formation.name)
        click_formation(self._device, formation)

        self._last_action = str(formation.value)
        self._history.add(
            CombatEvent(
                event_type=EventType.FORMATION,
                node=self._node,
                action=f'阵型{formation.value} ({formation.name})',
            )
        )
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_missile_animation(self) -> ConditionFlag:
        """跳过导弹支援动画。"""
        _log.info('[Combat] 跳过导弹支援动画')
        click_skip_missile_animation(self._device)
        self._last_action = 'skip_animation'
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_fight_period(self) -> ConditionFlag:
        """处理战斗进行中。"""
        decision = self._get_current_decision()
        if decision.SL_when_enter_fight:
            self._history.add(
                CombatEvent(
                    event_type=EventType.ENTER_FIGHT,
                    node=self._node,
                    action='SL',
                )
            )
            return ConditionFlag.SL
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_night_prompt(self) -> ConditionFlag:
        """处理夜战选择。"""
        decision = self._get_current_decision()
        pursue = decision.night

        _log.info('[Combat] 夜战选择: {}', '追击' if pursue else '撤退')
        click_night_battle(self._device, pursue=pursue)
        self._last_action = 'yes' if pursue else 'no'

        self._history.add(
            CombatEvent(
                event_type=EventType.NIGHT_BATTLE,
                node=self._node,
                action='追击' if pursue else '撤退',
            )
        )
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_result(self) -> ConditionFlag:
        """处理战果结算 -- 采集评级/MVP/血量并关闭界面。

        始终采集完整战果信息 (评级/MVP/血量): 触发器计数、条件战斗判定、
        掉落统计均依赖 FightResult 数据, 快速模式不采集会导致计数器不工作。

        ``collect_result_info`` 仅影响页面通过策略:
        慢速 (有战果条件): 经验页入状态机逐页推进;
        快速 (默认): 经验页是过渡页, 点击直接穿行。
        """
        # 硬等待: RESULT 页面动画 (结算界面滑入/文字淡入) 需要时间稳定,
        # 远端卡顿机器上立即 OCR 会截到半渲染画面导致血量/评级/MVP 识别失败
        time.sleep(1.5)

        # ── 信息采集 (始终采集: 计数器/触发器/掉落统计依赖) ──
        grade = detect_result_grade(self._device)
        self._ship_stats = detect_ship_stats(self._device, self._ship_stats)
        screen = self._device.screenshot()
        mvp = detect_mvp(screen)

        fight_result = FightResult(
            node=self._node,
            mvp=mvp,
            grade=grade,
            ship_stats=self._ship_stats[:],
        )
        self._history.add(
            CombatEvent(
                event_type=EventType.RESULT,
                node=self._node,
                result=grade,
                ship_stats=self._ship_stats[:],
                extra={'mvp': mvp},
            )
        )
        _log.info('[Combat] 战果: {} 节点: {}', fight_result, self._node)

        # ── 关闭结算界面 ──
        if self._plan.collect_result_info:
            # 慢速: 经验页入状态机逐页推进
            self._click_result_until_closed(CombatPhase.RESULT)
        else:
            # 快速: 经验页是过渡页, 点击直接穿行
            self._click_result_until_closed(
                CombatPhase.RESULT,
                pass_through=(CombatPhase.EXP_SETTLEMENT,),
            )
        return ConditionFlag.FIGHT_CONTINUE

    def _click_result_until_closed(
        self,
        phase: CombatPhase,
        *,
        attempts: int = 6,
        interval: float = 0.3,
        polls: int = 4,
        pass_through: tuple[CombatPhase, ...] = (),
    ) -> None:
        """点击战果类页面继续，并验证已到达**已知后继状态**。

        验证判据是到达验证而非"原页面签名消失"——点击 RESULT 战果页后,
        游戏先进入**经验结算子页** (逐舰船经验, 对应 CombatPhase.EXP_SETTLEMENT):
        若以"RESULT 消失"为成功判据, 复检会在经验页误判成功提前返回,
        引擎随后等待 PROCEED/GET_SHIP 等状态全部落空
        (实机 2026-08-15: 状态识别超时 → 恢复失败 → 强制重启)。

        **快速点击 + 复检轮询**: 点击后每 *interval* 秒截图识别一次
        (最多 *polls* 次), 在 ``[phase] + pass_through + 后继状态`` 集合上判定:
          - 命中后继 → 成功返回;
          - 命中 *pass_through* 中的页面 (如快速穿行模式的经验页) →
            视为未到达, 继续点击跳过;
          - 命中 *phase* → 点击被动画吞掉, 立即重试点击 (重试即动画等待);
          - 识别不到 (过渡帧/页面渐变中) → **只等待不点击**: 对切换中的
            页面盲目连点会穿透中间页, 落点若是 PROCEED 对话框还可能误触
            按钮。轮询窗口耗尽仍认不出才继续点击推进 (真正的未知页)。

        Parameters
        ----------
        phase:
            待关闭页面的状态签名 (RESULT / GET_SHIP)。
        attempts:
            最大点击次数。
        interval:
            复检轮询间隔 (秒)。
        polls:
            每次点击后的复检轮询上限 (过渡帧最长等待 attempts x interval x polls)。
        pass_through:
            识别到即**继续点击跳过**的过渡页 (快速穿行模式的 EXP_SETTLEMENT)。
        """
        successors = self._result_successors(phase)
        candidates = [phase, *pass_through, *successors]
        for attempt in range(1, attempts + 1):
            click_result(self._device)
            for _ in range(polls):
                time.sleep(interval)
                screen = self._device.screenshot()
                current = self._recognizer.identify_current(screen, candidates)
                if current is None:
                    continue  # 过渡帧: 只等待, 不点击 (防穿透/误触)
                if current in pass_through:
                    _log.debug(
                        '[Combat] {} 到达过渡页 {} (第 {} 次点击), 继续点击跳过',
                        phase.name,
                        current.name,
                        attempt,
                    )
                    break  # 过渡页: 继续点击 (与"被吞"同路径)
                if current == phase:
                    _log.warning(
                        '[Combat] {} 页面未关闭 (第 {} 次点击), 延迟重试', phase.name, attempt
                    )
                    break  # 确认被吞 → 重试点击
                _log.debug('[Combat] {} 已推进到 {}', phase.name, current.name)
                return
            else:
                # 整个轮询窗口都无法识别 → 未知页, 继续点击推进
                _log.debug(
                    '[Combat] {} 点击后持续无法识别 (第 {} 次), 继续点击', phase.name, attempt
                )
        _log.error('[Combat] {} 页面点击 {} 次仍未推进, 继续执行', phase.name, attempts)

    def _result_successors(self, phase: CombatPhase) -> list[CombatPhase]:
        """返回战果类页面点击后的**合法落点集合** (到达验证候选)。

        比 state.py 转移图宽: 转移图按真实流转建模, 此集合额外包含穿透
        场景 — 快速点击下连点两击可能跳过中间页 (如 RESULT 点击穿透到
        GET_SHIP), 复检把它们都认出来即可提前停止点击, 交引擎主循环按
        当前页继续。

        慢速 (collect_result_info=True): RESULT 之后含经验结算页 (作为
        到达点逐页推进); 快速: 经验页是 pass_through 过渡页, 不在到达集。

        RESULT 之后: PROCEED / 终态页 / GET_SHIP / 旗舰大破 (+经验页, 慢速);
        EXP_SETTLEMENT 之后: 同上但去掉 EXP_SETTLEMENT 自身;
        GET_SHIP 之后: 同上但去掉 GET_SHIP 自身。
        """
        successors = [CombatPhase.PROCEED, CombatPhase.FLAGSHIP_SEVERE_DAMAGE]
        end_phase = self._plan.end_phase
        if end_phase is not None:
            successors.append(end_phase)
        if phase == CombatPhase.RESULT:
            successors.append(CombatPhase.GET_SHIP)
            if self._plan.collect_result_info:
                successors.append(CombatPhase.EXP_SETTLEMENT)
        elif phase == CombatPhase.EXP_SETTLEMENT:
            successors.append(CombatPhase.GET_SHIP)
        return successors

    def _handle_exp_settlement(self) -> ConditionFlag:
        """处理经验结算子页 — 点击继续推进到掉落/前进/终态页。"""
        self._click_result_until_closed(CombatPhase.EXP_SETTLEMENT)
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_get_ship(self) -> ConditionFlag:
        """处理获取舰船。"""
        ship_name = get_ship_drop(self._device, self._ocr)
        if ship_name:
            _log.info('[Combat] 获得舰船: {}', ship_name)

        self._history.add(
            CombatEvent(
                event_type=EventType.GET_SHIP,
                node=self._node,
                result=ship_name or '',
            )
        )
        self._click_result_until_closed(CombatPhase.GET_SHIP)
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_proceed(self) -> ConditionFlag:
        """处理继续前进 / 回港决策。

        决策依据:
        1. 当前节点的 ``proceed`` 配置
        2. 血量是否满足 ``proceed_stop`` 条件
        """
        self._node_count += 1
        decision = self._get_current_decision()

        should_proceed = decision.proceed and check_blood(self._ship_stats, decision.proceed_stop)

        _log.info('[Combat] 继续前进决策: {}', '前进' if should_proceed else '回港')
        click_proceed(self._device, go_forward=should_proceed)
        self._last_action = 'yes' if should_proceed else 'no'

        self._history.add(
            CombatEvent(
                event_type=EventType.PROCEED,
                node=self._node,
                action='前进' if should_proceed else '回港',
                ship_stats=self._ship_stats[:],
            )
        )

        if should_proceed:
            return ConditionFlag.FIGHT_CONTINUE
        return ConditionFlag.FIGHT_END

    def _handle_flagship_severe_damage(self) -> ConditionFlag:
        """处理旗舰大破。"""
        _log.info('[Combat] 旗舰大破, 强制回港')
        click_image(self._device, TemplateKey.FLAGSHIP_DAMAGE, 2.0)
        time.sleep(0.25)

        self._history.add(
            CombatEvent(
                event_type=EventType.FLAGSHIP_DAMAGE,
                node=self._node,
                action='回港',
            )
        )
        return ConditionFlag.FIGHT_END

    def _handle_dock_full(self) -> ConditionFlag:
        """处理船坞已满弹窗 — 返回 DOCK_FULL 标志交由上层处理。"""
        _log.warning('[Combat] 检测到船坞已满，战斗无法开始')
        self._history.add(
            CombatEvent(
                event_type=EventType.AUTO_RETURN,
                node=self._node,
                action='船坞已满',
            )
        )
        return ConditionFlag.DOCK_FULL

    # ── Mixin 所需的方法签名 (由宿主类提供) ──

    def _get_current_decision(self) -> NodeDecision:
        """获取当前节点的决策 (由 CombatEngine 实现)。"""
        raise NotImplementedError
