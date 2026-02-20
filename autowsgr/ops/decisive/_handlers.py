"""决战阶段处理 Mixin。

将各阶段处理方法从 ``DecisiveController`` 主类中分离，
降低单文件复杂度（参照 :mod:`~autowsgr.combat.handlers` 的设计）。

``PhaseHandlersMixin`` 仅作为 ``DecisiveController`` 的 Mixin 使用，
不直接实例化。所有方法通过 ``self`` 访问以下属性：

    self._ctrl       : AndroidController
    self._config     : DecisiveConfig
    self._state      : DecisiveState
    self._logic      : DecisiveLogic
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

from autowsgr.ops.decisive._logic import FleetSelection
from autowsgr.ops.decisive._overlay import (
    ADVANCE_CARD_POSITIONS,
    CLICK_ADVANCE_CONFIRM,
    CLICK_FLEET_CLOSE,
    CLICK_FLEET_REFRESH,
    CLICK_LEAVE,
    CLICK_RETREAT_BUTTON,
    CLICK_RETREAT_CONFIRM,
    CLICK_SORTIE,
    DecisiveOverlay,
    detect_decisive_overlay,
    get_overlay_signature,
    is_advance_choice,
    is_decisive_map_page,
)
from autowsgr.ops.decisive._state import DecisivePhase
from autowsgr.vision.matcher import PixelChecker

if TYPE_CHECKING:
    from autowsgr.emulator.controller import AndroidController
    from autowsgr.ops.decisive._config import DecisiveConfig
    from autowsgr.ops.decisive._logic import DecisiveLogic
    from autowsgr.ops.decisive._state import DecisiveState


class PhaseHandlersMixin:
    """决战阶段处理 Mixin。

    提供所有 ``_handle_*`` 方法和辅助等待方法。
    需与 ``DecisiveController`` 组合使用（通过 MRO 继承）。
    """

    # 子类须提供这些属性（供类型检查器使用）
    _ctrl: AndroidController
    _config: DecisiveConfig
    _state: DecisiveState
    _logic: DecisiveLogic

    # ══════════════════════════════════════════════════════════════════════
    # 阶段处理方法
    # ══════════════════════════════════════════════════════════════════════

    def _handle_enter_map(self) -> None:
        """进入地图：点击出征 → 等待地图页或战备舰队弹窗。"""
        logger.info("[决战] 进入地图 (小关 {})", self._state.stage + 1)
        self._state.stage += 1
        self._state.node = "A"

        self._ctrl.click(*CLICK_SORTIE)
        time.sleep(2.0)

        screen = self._poll_for_map_or_overlay(timeout=15.0)
        overlay = detect_decisive_overlay(screen)

        if overlay == DecisiveOverlay.FLEET_ACQUISITION:
            self._state.phase = DecisivePhase.CHOOSE_FLEET
        elif is_decisive_map_page(screen):
            self._state.phase = DecisivePhase.MAP_READY
        elif is_advance_choice(screen):
            self._state.phase = DecisivePhase.ADVANCE_CHOICE
        else:
            logger.warning("[决战] 进入地图后页面状态未知, 尝试继续")
            self._state.phase = DecisivePhase.MAP_READY

    def _handle_choose_fleet(self) -> None:
        """战备舰队获取：OCR 识别选项 → 购买决策 → 关闭弹窗。"""
        logger.info("[决战] 战备舰队获取")
        screen = self._ctrl.screenshot()
        selections = self._recognize_fleet_options(screen)

        if selections:
            first_node = self._state.is_begin()
            to_buy = self._logic.choose_ships(selections, first_node=first_node)
            if not to_buy:
                # 无合适选项 → 刷新一次再试
                self._ctrl.click(*CLICK_FLEET_REFRESH)
                time.sleep(1.5)
                screen = self._ctrl.screenshot()
                selections = self._recognize_fleet_options(screen)
                to_buy = self._logic.choose_ships(selections, first_node=first_node)

            for name in to_buy:
                sel = selections[name]
                self._ctrl.click(*sel.click_position)
                time.sleep(0.3)
                if name not in {"长跑训练", "肌肉记忆", "黑科技"}:
                    self._state.ships.add(name)

        self._ctrl.click(*CLICK_FLEET_CLOSE)
        time.sleep(1.0)
        self._state.phase = DecisivePhase.MAP_READY

    def _handle_map_ready(self) -> None:
        """地图就绪：检测 overlay → 分发到对应阶段。"""
        screen = self._ctrl.screenshot()
        overlay = detect_decisive_overlay(screen)

        if overlay == DecisiveOverlay.FLEET_ACQUISITION:
            self._state.phase = DecisivePhase.CHOOSE_FLEET
        elif overlay == DecisiveOverlay.ADVANCE_CHOICE:
            self._state.phase = DecisivePhase.ADVANCE_CHOICE
        else:
            # TODO: 检查副官技能
            self._state.phase = DecisivePhase.PREPARE_COMBAT

    def _handle_advance_choice(self) -> None:
        """选择前进点：决策 → 点击卡片 → 确认。"""
        logger.info("[决战] 选择前进点")
        # TODO: OCR 识别可选节点名 (如 A1, A2)
        choice_idx = self._logic.get_advance_choice([])
        if choice_idx < len(ADVANCE_CARD_POSITIONS):
            self._ctrl.click(*ADVANCE_CARD_POSITIONS[choice_idx])
            time.sleep(0.5)
        self._ctrl.click(*CLICK_ADVANCE_CONFIRM)
        time.sleep(1.5)
        self._state.phase = DecisivePhase.MAP_READY

    def _handle_prepare_combat(self) -> None:
        """出征准备：编队 → 修理检查 → 开始出征。"""
        logger.info(
            "[决战] 出征准备 (小关 {} 节点 {})", self._state.stage, self._state.node
        )
        self._ctrl.click(*CLICK_SORTIE)
        time.sleep(2.0)

        # TODO: 集成 BattlePreparationPage 编队操作
        # TODO: 集成 apply_repair() 修理操作

        best_fleet = self._logic.get_best_fleet()
        if self._logic.should_retreat(best_fleet):
            logger.info("[决战] 舰船不足, 准备撤退")
            self._state.phase = DecisivePhase.RETREAT
            return

        self._state.fleet = best_fleet
        # TODO: 使用 BattlePreparationPage 出征按钮
        self._state.phase = DecisivePhase.IN_COMBAT

    def _handle_combat(self) -> None:
        """战斗阶段：委托 CombatEngine 执行（当前为占位）。

        TODO:
        - 根据 enemy_spec.yaml 及敌方编成决定阵型/夜战
        - 构建 :class:`~autowsgr.combat.plan.CombatPlan`
        - 调用 :func:`~autowsgr.combat.engine.run_combat`
        - 将战果写入 ``self._state.ship_stats``
        """
        logger.info(
            "[决战] 开始战斗 (小关 {} 节点 {})",
            self._state.stage,
            self._state.node,
        )
        # TODO: result = run_combat(self._ctrl, plan, ...)
        # TODO: self._state.ship_stats = result.ship_stats
        self._state.phase = DecisivePhase.NODE_RESULT

    def _handle_node_result(self) -> None:
        """节点战斗结束：推进节点，检查小关结束与修理需求。"""
        logger.info("[决战] 节点 {} 战斗结束", self._state.node)
        next_node = chr(ord(self._state.node) + 1)

        # TODO: 根据 map_end.yaml 判断小关是否真正结束
        if next_node > "J":
            self._state.phase = DecisivePhase.STAGE_CLEAR
            return

        self._state.node = next_node

        if self._logic.should_repair():
            logger.info("[决战] 需要修理")
            # TODO: 调用修理操作

        self._state.phase = DecisivePhase.MAP_READY

    def _handle_stage_clear(self) -> None:
        """小关通关：确认奖励弹窗，决定是否进入下一小关。"""
        logger.info("[决战] 小关 {} 通关!", self._state.stage)
        for _ in range(3):
            self._ctrl.click(0.5, 0.5)
            time.sleep(1.5)

        if self._state.stage >= 3:
            self._state.phase = DecisivePhase.CHAPTER_CLEAR
        else:
            self._state.phase = DecisivePhase.ENTER_MAP

    def _handle_retreat(self) -> None:
        """执行撤退：左上角撤退 → 确认退出 overlay → 点击「撤退」。"""
        logger.info("[决战] 执行撤退")
        self._go_to_map_page()
        self._ctrl.click(*CLICK_RETREAT_BUTTON)
        time.sleep(1.0)
        self._wait_for_overlay(DecisiveOverlay.CONFIRM_EXIT, timeout=5.0)
        self._ctrl.click(*CLICK_RETREAT_CONFIRM)
        time.sleep(2.0)

    def _handle_leave(self) -> None:
        """执行暂离：左上角撤退 → 确认退出 overlay → 点击「暂离」。"""
        logger.info("[决战] 执行暂离")
        self._go_to_map_page()
        self._ctrl.click(*CLICK_RETREAT_BUTTON)
        time.sleep(1.0)
        self._wait_for_overlay(DecisiveOverlay.CONFIRM_EXIT, timeout=5.0)
        self._ctrl.click(*CLICK_LEAVE)
        time.sleep(2.0)

    # ══════════════════════════════════════════════════════════════════════
    # 辅助等待方法
    # ══════════════════════════════════════════════════════════════════════

    def _go_to_map_page(self) -> None:
        """确保当前在决战地图页（若在准备页则点击左上角返回）。"""
        screen = self._ctrl.screenshot()
        if is_decisive_map_page(screen):
            return
        self._ctrl.click(0.03, 0.06)
        time.sleep(1.0)
        if not is_decisive_map_page(self._ctrl.screenshot()):
            logger.warning("[决战] 无法确认已回到地图页")

    def _poll_for_map_or_overlay(
        self,
        timeout: float = 15.0,
        interval: float = 0.5,
    ) -> np.ndarray:
        """轮询截图，直到出现地图页或任意 overlay，返回该截图。"""
        deadline = time.monotonic() + timeout
        while True:
            screen = self._ctrl.screenshot()
            if is_decisive_map_page(screen) or detect_decisive_overlay(screen) is not None:
                return screen
            if time.monotonic() >= deadline:
                logger.warning("[决战] 等待地图页/overlay 超时")
                return screen
            time.sleep(interval)

    def _wait_for_overlay(
        self,
        target: DecisiveOverlay,
        timeout: float = 5.0,
        interval: float = 0.3,
    ) -> np.ndarray:
        """反复截图直到指定 overlay 出现，超时则抛出 ``TimeoutError``。"""
        sig = get_overlay_signature(target)
        deadline = time.monotonic() + timeout
        while True:
            screen = self._ctrl.screenshot()
            if PixelChecker.check_signature(screen, sig):
                return screen
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"等待 overlay {target.value} 超时 ({timeout}s)"
                )
            time.sleep(interval)

    # ══════════════════════════════════════════════════════════════════════
    # OCR 相关（预留接口）
    # ══════════════════════════════════════════════════════════════════════

    def _recognize_fleet_options(
        self,
        screen: np.ndarray,
    ) -> dict[str, FleetSelection]:
        """OCR 识别战备舰队获取界面的 5 个可选项。

        流程::

            1. 裁切右上角资源区域 → 识别可用分数 → 写入 state.score
            2. 裁切底部费用整行   → 识别每张卡的费用
            3. 裁切每张卡名称区域  → 识别舰船名
            4. 组装 {name: FleetSelection}

        Returns
        -------
        dict[str, FleetSelection]
            可购买项字典；OCR 未实现时返回 ``{}``。
        """
        # TODO: 接入 OCR 引擎
        logger.warning("[决战] OCR 识别尚未实现, 跳过舰队选择")
        return {}

    def _recognize_node(self, screen: np.ndarray) -> str:
        """OCR 识别当前节点名（如 'A', 'B'）。

        Returns
        -------
        str
            节点字母；OCR 未实现时返回当前 ``state.node``。
        """
        # TODO: 查找舰船图标位置 → 裁切上方区域 → OCR 识别
        return self._state.node
