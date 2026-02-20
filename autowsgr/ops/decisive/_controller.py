from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from loguru import logger

from autowsgr.emulator.controller import AndroidController
from autowsgr.ops.decisive._config import DecisiveConfig
from autowsgr.ops.decisive._handlers import PhaseHandlersMixin
from autowsgr.ops.decisive._logic import DecisiveLogic
from autowsgr.ops.decisive._state import DecisivePhase, DecisiveState

if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np


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


class DecisiveController(PhaseHandlersMixin):
    """决战过程控制器（状态机核心）。

    通过继承 :class:`PhaseHandlersMixin` 获得所有阶段处理与 OCR 辅助方法；
    本模块只包含：构造、公共入口、主循环和章节重置。
    """

    def __init__(
        self,
        ctrl: AndroidController,
        config: DecisiveConfig,
        *,
        ocr_func: Callable[[np.ndarray], str] | None = None,
    ) -> None:
        self._ctrl = ctrl
        self._config = config
        self._ocr = ocr_func
        self._state = DecisiveState(chapter=config.chapter)
        self._logic = DecisiveLogic(config, self._state)

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

            ENTER_MAP -> [CHOOSE_FLEET] -> MAP_READY
            MAP_READY -> ADVANCE_CHOICE | PREPARE_COMBAT
            PREPARE_COMBAT -> IN_COMBAT -> NODE_RESULT
            NODE_RESULT -> MAP_READY | STAGE_CLEAR | RETREAT | LEAVE
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
                self._handle_retreat()
                self._state.reset()
                self._state.phase = DecisivePhase.ENTER_MAP
                continue

            if phase == DecisivePhase.LEAVE:
                self._handle_leave()
                self._state.phase = DecisivePhase.FINISHED
                return DecisiveResult.LEAVE

            handler = _handlers.get(phase)
            if handler is None:
                logger.error("[决战] 未知阶段: {}", phase)
                self._state.phase = DecisivePhase.FINISHED
                return DecisiveResult.ERROR

            handler()

        return DecisiveResult.CHAPTER_CLEAR

    # ── 章节重置 ──────────────────────────────────────────────────────────────

    def _reset_chapter(self) -> None:
        """重置章节，为下一轮做准备。TODO: 切换章节 -> 重置按钮 -> 确认。"""
        logger.info("[决战] 重置章节")
        self._state.reset()
