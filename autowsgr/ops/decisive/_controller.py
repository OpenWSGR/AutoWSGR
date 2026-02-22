"""决战过程控制器（状态机核心）。

``DecisiveController`` 是决战的最高层编排器，**不直接执行任何 UI 操作**，
而是通过以下三个下层控制器的接口组装完整流程：

- :class:`~autowsgr.ui.decisive.map_controller.DecisiveMapController`
  — 决战地图页所有交互（overlay 处理、出征、撤退、节点间修理）
- :class:`~autowsgr.ui.battle.preparation.BattlePreparationPage`
  — 出征准备页操作（编队、修理、开始战斗）
- :class:`~autowsgr.ui.decisive_battle_page.DecisiveBattlePage`
  — 决战总览页操作（章节导航、重置）

逻辑决策委托给 :class:`~autowsgr.ops.decisive._logic.DecisiveLogic`。
"""

from __future__ import annotations

import enum
import time
from typing import TYPE_CHECKING

from loguru import logger

from autowsgr.combat.engine import run_combat
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.emulator import AndroidController
from autowsgr.infra import DecisiveConfig
from autowsgr.ops.decisive._logic import DecisiveLogic
from autowsgr.ops.decisive._state import DecisiveState
from autowsgr.types import DecisivePhase, Formation, ShipDamageState
from autowsgr.ui import BattlePreparationPage, RepairStrategy
from autowsgr.ui.decisive import DecisiveBattlePage, DecisiveMapController
from autowsgr.ui.decisive.overlay import DecisiveOverlay
from autowsgr.vision import ApiDll


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np

    from autowsgr.vision import OCREngine


# ─────────────────────────────────────────────────────────────────────────────
# 结果枚举
# ─────────────────────────────────────────────────────────────────────────────


class DecisiveResult(enum.Enum):
    """决战单轮的最终结局。"""

    CHAPTER_CLEAR = "chapter_clear"
    """大关通关 (3 个小关全部完成)。"""

    RETREAT = "retreat"
    """主动撤退 (清空进度)。"""

    LEAVE = "leave"
    """暂离保存 (保留进度退出)。"""

    ERROR = "error"
    """异常退出。"""


# ─────────────────────────────────────────────────────────────────────────────
# 控制器
# ─────────────────────────────────────────────────────────────────────────────


class DecisiveController:
    """决战过程控制器（状态机核心）。

    通过 :class:`DecisiveMapController` 执行所有地图页 UI 操作，
    通过 :class:`BattlePreparationPage` 执行出征准备操作，
    通过 :class:`DecisiveBattlePage` 执行章节重置操作，
    通过 :class:`DecisiveLogic` 进行所有逻辑决策。
    """

    def __init__(
        self,
        ctrl: AndroidController,
        config: DecisiveConfig,
        *,
        ocr: OCREngine | None = None,
        image_matcher: Callable[[np.ndarray], str | None] | None = None,
        dll: ApiDll | None = None,
    ) -> None:
        self._ctrl = ctrl
        self._config = config
        self._ocr = ocr
        self._image_matcher = image_matcher
        self._dll = dll
        self._state = DecisiveState(chapter=config.chapter)
        self._logic = DecisiveLogic(config, self._state)
        self._battle_page = DecisiveBattlePage(self._ctrl, ocr=self._ocr)
        self._map = DecisiveMapController(
            ctrl, config, ocr=ocr, dll=dll, image_matcher=image_matcher,
        )

    @property
    def state(self) -> DecisiveState:
        """当前决战状态（只读）。"""
        return self._state

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def run(self) -> DecisiveResult:
        """执行一轮完整决战（3 个小关）。"""
        logger.info("[决战] 开始第 {} 章决战", self._config.chapter)
        self._state.reset()
        self._state.phase = DecisivePhase.ENTER_MAP
        try:
            return self._main_loop()
        except Exception:
            logger.exception("[决战] 执行异常")
            self._state.phase = DecisivePhase.FINISHED
            return DecisiveResult.ERROR

    def run_for_times(self, times: int = 1) -> list[DecisiveResult]:
        """执行多轮决战；遇到 LEAVE / ERROR 时提前停止。"""
        results: list[DecisiveResult] = []
        for i in range(times):
            logger.info("[决战] 第 {}/{} 轮", i + 1, times)
            result = self.run()
            results.append(result)
            if result in (DecisiveResult.LEAVE, DecisiveResult.ERROR):
                logger.warning("[决战] 第 {} 轮终止: {}", i + 1, result.value)
                break
            if i < times - 1:
                self._reset_chapter()
        return results

    # ── 主循环 ────────────────────────────────────────────────────────────────

    def _main_loop(self) -> DecisiveResult:
        """决战主状态机循环。

        状态转移::
            ENTER_MAP -> ADVANCE_CHOICE | MAP_READY
            ADVANCE_CHOICE -> CHOOSE_FLEET
            CHOSE_FLEET -> MAP_READY
            MAP_READY -> PREPARE_COMBAT | IN_COMBAT | RETREAT | LEAVE
            PREPARE_COMBAT -> IN_COMBAT | RETREAT | LEAVE
            IN_COMBAT -> NODE_RESULT
            NODE_RESULT -> STAGE_CLEAR | ADVANCE_CHOICE | CHOOSE_FLEET
            STAGE_CLEAR -> ENTER_MAP | CHAPTER_CLEAR
            RETREAT -> (reset) -> ENTER_MAP
            LEAVE -> FINISHED
        """
        _handlers = {
            DecisivePhase.ENTER_MAP:      self._handle_enter_map,
            DecisivePhase.CHOOSE_FLEET:   self._handle_choose_fleet,
            DecisivePhase.MAP_READY:      self._handle_map_ready,
            DecisivePhase.ADVANCE_CHOICE: self._handle_advance_choice,
            DecisivePhase.PREPARE_COMBAT: self._handle_prepare_combat,
            DecisivePhase.IN_COMBAT:      self._handle_combat,
            DecisivePhase.NODE_RESULT:    self._handle_node_result,
            DecisivePhase.STAGE_CLEAR:    self._handle_stage_clear,
        }

        while self._state.phase != DecisivePhase.FINISHED:
            phase = self._state.phase
            logger.debug(
                "[决战] 阶段: {} | 小关: {} | 节点: {}",
                phase.name, self._state.stage, self._state.node,
            )

            if phase == DecisivePhase.CHAPTER_CLEAR:
                logger.info("[决战] 大关通关!")
                self._state.phase = DecisivePhase.FINISHED
                return DecisiveResult.CHAPTER_CLEAR

            if phase == DecisivePhase.RETREAT:
                self._execute_retreat()
                self._state.reset()
                self._state.phase = DecisivePhase.ENTER_MAP
                continue

            if phase == DecisivePhase.LEAVE:
                self._execute_leave()
                self._state.phase = DecisivePhase.FINISHED
                return DecisiveResult.LEAVE

            handler = _handlers.get(phase)
            if handler is None:
                logger.error("[决战] 未知阶段: {}", phase)
                self._state.phase = DecisivePhase.FINISHED
                return DecisiveResult.ERROR

            handler()

        return DecisiveResult.CHAPTER_CLEAR

    # ══════════════════════════════════════════════════════════════════════
    # 阶段处理方法
    # ══════════════════════════════════════════════════════════════════════

    def _handle_enter_map(self) -> None:
        """进入地图：点击出征 → 等待地图页或战备舰队弹窗。"""
        # TODO: 进入地图的流程需要修改
        logger.info("[决战] 进入地图 (小关 {})", self._state.stage + 1)
        self._state.stage += 1
        self._state.node = "A"

        self._map.click_sortie()
        self._state.phase = self._map.poll_for_map_or_overlay(timeout=15.0)


    def _handle_choose_fleet(self) -> None:
        """战备舰队获取：OCR 识别选项 → 购买决策 → 关闭弹窗。"""
        logger.info("[决战] 战备舰队获取")
        screen = self._map.screenshot()
        score, selections = self._map.recognize_fleet_options(screen)
        self._state.score = score or self._state.score

        if selections:
            first_node = self._state.is_begin()
            to_buy = self._logic.choose_ships(selections, first_node=first_node)

            if not to_buy:
                # 无合适选项 → 刷新一次再试
                self._map.refresh_fleet()
                screen = self._map.screenshot()
                score, selections = self._map.recognize_fleet_options(screen)
                self._state.score = score or self._state.score
                to_buy = self._logic.choose_ships(selections, first_node=first_node)

            for name in to_buy:
                sel = selections[name]
                self._map.buy_fleet_option(sel.click_position)
                if name not in {"长跑训练", "肌肉记忆", "黑科技"}:
                    self._state.ships.add(name)

        self._map.close_fleet_overlay()
        self._state.phase = DecisivePhase.MAP_READY

    def _handle_map_ready(self) -> None:
        """地图就绪：检测 overlay → 分发到对应阶段。"""
        screen = self._map.screenshot()
        overlay = self._map.detect_overlay(screen)

        if overlay == DecisiveOverlay.FLEET_ACQUISITION:
            self._state.phase = DecisivePhase.CHOOSE_FLEET
        elif overlay == DecisiveOverlay.ADVANCE_CHOICE:
            self._state.phase = DecisivePhase.ADVANCE_CHOICE
        else:
            self._state.phase = DecisivePhase.PREPARE_COMBAT

    def _handle_advance_choice(self) -> None:
        """选择前进点：决策 → 点击卡片 → 确认。"""
        logger.info("[决战] 选择前进点")
        # TODO: OCR 识别可选节点名 (P1 #8)
        choice_idx = self._logic.get_advance_choice([])
        self._map.select_advance_card(choice_idx)
        self._state.phase = DecisivePhase.MAP_READY

    def _handle_prepare_combat(self) -> None:
        # TODO: 进入准备页面的操作不对
        """出征准备：编队 → 修理检查 → 开始出征。"""
        logger.info(
            "[决战] 出征准备 (小关 {} 节点 {})", self._state.stage, self._state.node,
        )

        # 先计算最优编队并检查是否要撤退
        best_fleet = self._logic.get_best_fleet()
        if self._logic.should_retreat(best_fleet):
            logger.info("[决战] 舰船不足, 准备撤退")
            self._state.phase = DecisivePhase.RETREAT
            return
        self._state.fleet = best_fleet

        # 点击出征进入准备页
        self._map.click_sortie()

        # 准备页操作
        page = BattlePreparationPage(self._ctrl)

        # 修理
        strategy = (
            RepairStrategy.MODERATE
            if self._config.repair_level <= 1
            else RepairStrategy.SEVERE
        )
        page.apply_repair(strategy)

        # 检测战前血量
        screen = self._ctrl.screenshot()
        damage = page.detect_ship_damage(screen)
        self._state.ship_stats = [damage.get(i, ShipDamageState.NORMAL) for i in range(6)]

        # 出征
        page.start_battle()
        time.sleep(1.0)
        self._state.phase = DecisivePhase.IN_COMBAT

    def _handle_combat(self) -> None:
        """战斗阶段：委托 CombatEngine 执行。"""
        logger.info(
            "[决战] 开始战斗 (小关 {} 节点 {})",
            self._state.stage,
            self._state.node,
        )

        if self._image_matcher is None:
            logger.warning("[决战] 无图像匹配器, 跳过战斗")
            self._state.phase = DecisivePhase.NODE_RESULT
            return

        plan = CombatPlan(
            name=f"决战-{self._state.stage}-{self._state.node}",
            mode=CombatMode.BATTLE,
            default_node=NodeDecision(
                formation=Formation.double_column,
                night=self._logic.is_key_point(),
            ),
        )

        result = run_combat(
            self._ctrl,
            plan,
            ship_stats=self._state.ship_stats[:],
        )

        self._state.ship_stats = result.ship_stats[:]
        logger.info(
            "[决战] 战斗结束: {} (节点 {} 血量 {})",
            result.flag.value,
            self._state.node,
            self._state.ship_stats,
        )
        self._state.phase = DecisivePhase.NODE_RESULT

    def _handle_node_result(self) -> None:
        """节点战斗结束：根据 MapData 判断小关结束，检查修理需求。"""
        # TODO: 流程有问题，处理结果之后应该处理获取战备舰队等
        logger.info("[决战] 节点 {} 战斗结束", self._state.node)

        # 使用 MapData 判断小关是否结束 (替代硬编码 > "J")
        if self._logic.is_stage_end():
            logger.info(
                "[决战] 小关 {} 终止节点 {} 已到达",
                self._state.stage, self._state.node,
            )
            self._state.phase = DecisivePhase.STAGE_CLEAR
            return

        # 推进到下一节点
        next_node = chr(ord(self._state.node) + 1)
        self._state.node = next_node

        # 节点间修理: should_repair() 返回 true 时调用实际修理
        if self._logic.should_repair():
            logger.info("[决战] 需要修理, 执行节点间修理")
            repaired = self._map.repair_at_node(self._config.repair_level)
            if repaired:
                logger.info("[决战] 修理了 {} 个槽位", len(repaired))

        self._state.phase = DecisivePhase.MAP_READY

    def _handle_stage_clear(self) -> None:
        """小关通关：确认奖励弹窗，决定是否进入下一小关。"""
        logger.info("[决战] 小关 {} 通关!", self._state.stage)
        self._map.confirm_stage_clear()

        if self._state.stage >= 3:
            self._state.phase = DecisivePhase.CHAPTER_CLEAR
        else:
            self._state.phase = DecisivePhase.ENTER_MAP

    # ══════════════════════════════════════════════════════════════════════
    # 撤退与暂离
    # ══════════════════════════════════════════════════════════════════════

    def _execute_retreat(self) -> None:
        """执行撤退操作。"""
        logger.info("[决战] 执行撤退")
        self._map.open_retreat_dialog()
        self._map.confirm_retreat()

    def _execute_leave(self) -> None:
        """执行暂离操作。"""
        logger.info("[决战] 执行暂离")
        self._map.open_retreat_dialog()
        self._map.confirm_leave()

    # ══════════════════════════════════════════════════════════════════════
    # 章节重置
    # ══════════════════════════════════════════════════════════════════════

    def _reset_chapter(self) -> None:
        """重置章节，为下一轮做准备。

        操作流程: 总览页导航到目标章节 → 点击底部重置按钮 → 确认重置。
        参照旧代码 ``DecisiveBattle.reset_chapter``。
        """
        logger.info("[决战] 重置章节 (Ex-{})", self._config.chapter)
        self._state.reset()

        # 导航到目标章节
        try:
            self._battle_page.navigate_to_chapter(self._config.chapter)
        except Exception:
            logger.warning("[决战] 章节导航失败, 假设已在目标章节")

        # 点击底部重置/开始按钮 (底部正中)
        self._ctrl.click(0.5, 0.925)
        time.sleep(1.5)

        # 确认重置弹窗
        self._ctrl.click(0.5, 0.5)
        time.sleep(1.5)

        logger.info("[决战] 章节重置完成")
