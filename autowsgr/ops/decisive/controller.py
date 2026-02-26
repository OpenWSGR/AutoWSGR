"""决战过程控制器（状态机核心）。

``DecisiveController`` 是决战的最高层编排器，**不直接执行任何 UI 操作**，
而是通过以下下层控制器的接口组装完整流程：

- :class:`~autowsgr.ui.decisive.map_controller.DecisiveMapController`
  — 决战地图页所有交互（overlay 处理、出征、撤退、节点间修理）
- :class:`~autowsgr.ui.decisive.preparation.DecisiveBattlePreparationPage`
  — 出征准备页操作（编队、修理、开始战斗）
- :class:`~autowsgr.ui.decisive.battle_page.DecisiveBattlePage`
  — 决战总览页操作（章节导航、重置）

继承体系::

    DecisiveBase                           ← base.py   (成员声明 & 初始化)
    ├── DecisiveChapterOps(DecisiveBase)   ← chapter.py (章节管理)
    ├── DecisivePhaseHandlers(DecisiveBase)← handlers.py (阶段处理器)
    └── DecisiveController(                ← 本文件      (状态机编排)
            DecisivePhaseHandlers,
            DecisiveChapterOps,
        )
"""

from __future__ import annotations

import enum

from autowsgr.infra.logger import get_logger
from autowsgr.ops.decisive.chapter import DecisiveChapterOps
from autowsgr.ops.decisive.handlers import DecisivePhaseHandlers
from autowsgr.types import DecisivePhase


_log = get_logger('ops.decisive')

# ─────────────────────────────────────────────────────────────────────────────
# 结果枚举
# ─────────────────────────────────────────────────────────────────────────────


class DecisiveResult(enum.Enum):
    """决战单轮的最终结局。"""

    CHAPTER_CLEAR = 'chapter_clear'
    """大关通关 (3 个小关全部完成)。"""

    RETREAT = 'retreat'
    """主动撤退 (清空进度)。"""

    LEAVE = 'leave'
    """暂离保存 (保留进度退出)。"""

    ERROR = 'error'
    """异常退出。"""


# ─────────────────────────────────────────────────────────────────────────────
# 组装控制器
# ─────────────────────────────────────────────────────────────────────────────


class DecisiveController(DecisivePhaseHandlers, DecisiveChapterOps):
    """决战过程控制器（状态机核心）。

    通过多重继承组合:
    - :class:`DecisivePhaseHandlers` — 所有阶段处理器
    - :class:`DecisiveChapterOps` — 章节管理操作

    两者均继承 :class:`~autowsgr.ops.decisive.base.DecisiveBase`，
    成员初始化由 ``DecisiveBase.__init__`` 统一完成。
    """

    # ── 主入口 ────────────────────────────────────────────────────────────

    def run(self) -> DecisiveResult:
        """执行一轮完整决战（3 个小关）。"""
        _log.info('[决战] 开始第 {} 章决战', self._config.chapter)
        self._state.reset()
        self._resume_mode = False
        self._has_chosen_fleet = False
        self._prepare_entry_state()
        self._state.phase = DecisivePhase.ENTER_MAP
        try:
            return self._main_loop()
        except Exception:
            _log.exception('[决战] 执行异常')
            self._state.phase = DecisivePhase.FINISHED
            return DecisiveResult.ERROR

    def run_for_times(self, times: int = 1) -> list[DecisiveResult]:
        """执行多轮决战；遇到 LEAVE / ERROR 时提前停止。"""
        results: list[DecisiveResult] = []
        for i in range(times):
            _log.info('[决战] 第 {}/{} 轮', i + 1, times)
            result = self.run()
            results.append(result)
            if result in (DecisiveResult.LEAVE, DecisiveResult.ERROR):
                _log.warning('[决战] 第 {} 轮终止: {}', i + 1, result.value)
                break
        return results

    # ── 主循环 ────────────────────────────────────────────────────────────

    def _main_loop(self) -> DecisiveResult:
        """决战主状态机循环。"""
        _handlers = {
            DecisivePhase.ENTER_MAP: self._handle_enter_map,
            DecisivePhase.WAITING_FOR_MAP: self._handle_waiting_for_map,
            DecisivePhase.USE_LAST_FLEET: self._handle_use_last_fleet,
            DecisivePhase.DOCK_FULL: self._handle_dock_full,
            DecisivePhase.CHOOSE_FLEET: self._handle_choose_fleet,
            DecisivePhase.ADVANCE_CHOICE: self._handle_advance_choice,
            DecisivePhase.PREPARE_COMBAT: self._handle_prepare_combat,
            DecisivePhase.IN_COMBAT: self._handle_combat,
            DecisivePhase.NODE_RESULT: self._handle_node_result,
            DecisivePhase.STAGE_CLEAR: self._handle_stage_clear,
        }

        while self._state.phase != DecisivePhase.FINISHED:
            phase = self._state.phase

            # WAITING_FOR_MAP 太频繁，只在非等待阶段打日志
            if phase != DecisivePhase.WAITING_FOR_MAP:
                _log.debug(
                    '[决战] 阶段: {} | 小关: {} | 节点: {}',
                    phase.name,
                    self._state.stage,
                    self._state.node,
                )

            if phase == DecisivePhase.CHAPTER_CLEAR:
                _log.info('[决战] 大关通关!')
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
                _log.error('[决战] 未知阶段: {}', phase)
                self._state.phase = DecisivePhase.FINISHED
                return DecisiveResult.ERROR

            handler()

        return DecisiveResult.CHAPTER_CLEAR
