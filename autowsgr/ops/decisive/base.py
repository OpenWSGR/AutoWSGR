"""决战控制器基类。

集中声明所有下层控制器引用与运行时可变属性，
供 :class:`DecisivePhaseHandlers`、:class:`DecisiveChapterOps`
以及最终的 :class:`DecisiveController` 继承使用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.constants import DECISIVE_SKILL_NAMES, update_shipnames
from autowsgr.infra import DecisiveConfig, get_logger
from autowsgr.ops.decisive.logic import DecisiveLogic
from autowsgr.ops.decisive.state import DecisiveState
from autowsgr.ui.decisive import DecisiveBattlePage, DecisiveMapController


if TYPE_CHECKING:
    from autowsgr.context import GameContext

_log = get_logger('ops.decisive')


class DecisiveBase:
    """决战控制器基类。

    **成员属性**::

        _ctrl              emulator 控制器
        _config            决战配置 (DecisiveConfig)
        _ocr               OCR 引擎
        _state             运行时可变状态 (DecisiveState)
        _logic             纯决策模块 (DecisiveLogic)
        _battle_page       决战总览页 UI
        _map               决战地图页 UI
        _resume_mode       是否恢复进度模式
        _has_chosen_fleet  是否已经历过战备舰队获取
        _wait_deadline     等待超时截止时间
        _use_last_fleet_attempts  使用上次舰队尝试次数

    继承体系::

        DecisiveBase
        ├── DecisiveChapterOps(DecisiveBase)   ← 章节管理
        ├── DecisivePhaseHandlers(DecisiveBase) ← 阶段处理器
        └── DecisiveController(DecisivePhaseHandlers, DecisiveChapterOps)
    """

    def __init__(
        self,
        ctx: GameContext,
        config: DecisiveConfig,
    ) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._ocr = ctx.ocr
        # 合并配置：传入的 config 覆盖 ctx.config，未指定的字段使用 ctx.config 的值
        base = (
            ctx.config.decisive_battle.model_dump()
            if ctx.config.decisive_battle is not None
            else {}
        )
        merged_config_dict = {
            **base,
            **config.model_dump(exclude_unset=True),
        }
        merged_config = DecisiveConfig(**merged_config_dict)
        self._config = merged_config
        _log.info('[决战] 当前运行配置: {}', merged_config)
        if len(merged_config.level1) < 6:
            _log.warning('[决战] 一级舰队小于6艘, 请检查配置是否有误')

        # 将决战配置中的舰船名 + 技能名合并到全局 SHIPNAMES，
        # 后续 OCR 识别无需再临时拼接候选列表。
        update_shipnames(merged_config.level1 + merged_config.level2 + DECISIVE_SKILL_NAMES)

        self._state = DecisiveState(chapter=merged_config.chapter)
        self._logic = DecisiveLogic(merged_config, self._state, ctx=ctx)
        self._battle_page = DecisiveBattlePage(self._ctx, ocr=self._ocr)
        self._map = DecisiveMapController(
            ctx,
            merged_config,
        )
        self._resume_mode: bool = False
        self._has_chosen_fleet: bool = False
        self._wait_deadline: float = 0.0
        self._use_last_fleet_attempts: int = 0

    @property
    def state(self) -> DecisiveState:
        """当前决战状态（只读）。"""
        return self._state
