"""Pydantic 数据模型 — API 请求与响应格式定义。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, Field, field_validator, model_validator

from autowsgr.combat.fleet import ALLOWED_SHIP_TYPE_CODES


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举类型
# ═══════════════════════════════════════════════════════════════════════════════


class TaskType(StrEnum):
    """任务类型。"""

    NORMAL_FIGHT = 'normal_fight'
    EVENT_FIGHT = 'event_fight'
    CAMPAIGN = 'campaign'
    EXERCISE = 'exercise'
    DECISIVE = 'decisive'


class TaskStatusEnum(StrEnum):
    """任务状态。"""

    IDLE = 'idle'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    STOPPED = 'stopped'


class LogLevel(StrEnum):
    """日志级别。"""

    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'


RuleSpec: TypeAlias = tuple[str, Literal['retreat', 'detour'] | int]
"""HTTP rule item: condition expression plus retreat/detour/formation action."""


# ═══════════════════════════════════════════════════════════════════════════════
# 节点决策模型
# ═══════════════════════════════════════════════════════════════════════════════


class NodeDecisionRequest(BaseModel):
    """单个地图节点的战术决策。"""

    formation: int = Field(default=2, ge=1, le=5, description='阵型 (1-5)')
    night: bool = Field(default=False, description='是否夜战')
    proceed: bool = Field(default=True, description='是否前进')
    proceed_stop: list[int] = Field(
        default_factory=lambda: [2, 2, 2, 2, 2, 2],
        description='停止前进条件 (6个位置)',
    )
    detour: bool = Field(default=False, description='是否迂回')
    long_missile_support: bool = Field(
        default=False,
        description='是否开启远程导弹支援',
    )
    SL_when_detour_fails: bool = Field(
        default=True,
        description='迂回失败时是否 SL',
    )
    enemy_rules: list[RuleSpec] | None = Field(
        default=None,
        description='索敌规则',
    )
    enemy_formation_rules: list[RuleSpec] | None = Field(
        default=None,
        description='敌方阵型规则',
    )
    SL_when_spot_enemy_fails: bool = Field(
        default=False,
        description='索敌失败时是否 SL',
    )
    SL_when_enter_fight: bool = Field(
        default=False,
        description='进入战斗时是否 SL',
    )
    formation_when_spot_enemy_fails: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description='索敌失败时使用的替代阵型',
    )

    model_config = {'extra': 'forbid'}


class FleetShipRuleRequest(BaseModel):
    """一艘主选或备选舰船自己的选船规则。"""

    name: str = Field(description='舰船名')
    search_name: str | None = Field(default=None, description='选船搜索关键词（用于同名舰船区分）')
    ship_type: list[str] | None = Field(default=None, description='允许的舰种列表（如 [ss, ssg]）')
    min_level: int | None = Field(default=None, ge=1, description='等级下限（含）')
    max_level: int | None = Field(default=None, ge=1, description='等级上限（含）')

    @field_validator('name')
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError('name 不能为空')
        return normalized

    @field_validator('search_name')
    @classmethod
    def _validate_search_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator('ship_type', mode='before')
    @classmethod
    def _validate_ship_type(cls, value: Any) -> list[str] | None:
        if value is None or value == '':
            return None

        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list) or not values:
            raise ValueError('ship_type 必须是非空字符串列表')

        normalized: list[str] = []
        for ship_type in values:
            if not isinstance(ship_type, str) or not ship_type.strip():
                raise ValueError('ship_type 必须是非空字符串列表')
            code = ship_type.strip().lower()
            if code not in ALLOWED_SHIP_TYPE_CODES:
                allowed = ', '.join(sorted(ALLOWED_SHIP_TYPE_CODES))
                raise ValueError(f'ship_type 不合法: {ship_type!r}, 可选值: {allowed}')
            if code not in normalized:
                normalized.append(code)
        return normalized

    @model_validator(mode='after')
    def _validate_level_range(self) -> FleetShipRuleRequest:
        if (
            self.min_level is not None
            and self.max_level is not None
            and self.max_level < self.min_level
        ):
            raise ValueError('max_level 必须大于或等于 min_level')
        return self

    model_config = {'extra': 'forbid'}


class FleetRuleRequest(FleetShipRuleRequest):
    """一个槽位的主选规则及其位置级备选规则。"""

    name: str | None = Field(default=None, description='主选舰船名')
    candidates: list[FleetShipRuleRequest] = Field(
        default_factory=list,
        description='位置级备选舰船规则（按填写顺序尝试）',
    )

    @field_validator('name')
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode='after')
    def _validate_slot(self) -> FleetRuleRequest:
        """无主选时只允许保留非空的位置级备选队列。"""
        if self.name is not None:
            return self
        if len(self.candidates) == 0:
            raise ValueError('位置至少需要一艘主选或备选舰船')
        if any(
            value is not None
            for value in (
                self.search_name,
                self.ship_type,
                self.min_level,
                self.max_level,
            )
        ):
            raise ValueError('没有主选 name 时不能填写主选规则')
        return self


class CombatPlanRequest(BaseModel):
    """作战计划请求体。"""

    name: str = Field(default='', description='计划名称')
    mode: str = Field(default='normal', description='战斗模式')
    chapter: int | str = Field(default=1, description='章节号')
    map: int | str = Field(default=1, description='地图号')
    fleet_id: int = Field(default=1, ge=1, le=6, description='舰队编号')
    fleet: list[str] | None = Field(default=None, description='舰队成员')
    fleet_rules: list[str | FleetRuleRequest] | None = Field(
        default=None,
        description='舰队槽位规则（字符串或候选规则）',
    )
    repair_mode: list[int] = Field(
        default_factory=lambda: [2, 2, 2, 2, 2, 2],
        description='修理策略 (6个位置)',
    )
    fight_condition: int = Field(default=4, ge=1, le=5, description='战况选择')
    selected_nodes: list[str] = Field(
        default_factory=list,
        description='白名单节点',
    )
    node_defaults: NodeDecisionRequest = Field(
        default_factory=NodeDecisionRequest,
        description='默认节点决策',
    )
    node_args: dict[str, NodeDecisionRequest] = Field(
        default_factory=dict,
        description='各节点决策',
    )
    event_name: str | None = Field(default=None, description='活动名称')

    model_config = {'extra': 'forbid'}


# ═══════════════════════════════════════════════════════════════════════════════
# 任务请求模型
# ═══════════════════════════════════════════════════════════════════════════════


class NormalFightRequest(BaseModel):
    """常规战请求。"""

    type: Literal[TaskType.NORMAL_FIGHT] = TaskType.NORMAL_FIGHT
    plan: CombatPlanRequest | None = Field(
        default=None,
        description='作战计划 (与 plan_id 二选一)',
    )
    plan_id: str | None = Field(
        default=None,
        description='计划名称或 YAML 文件路径',
    )
    times: int = Field(default=1, ge=1, description='执行次数')
    gap: float = Field(default=0.0, ge=0, description='间隔时间(秒)')

    model_config = {'extra': 'forbid'}


class EventFightRequest(BaseModel):
    """活动战请求。"""

    type: Literal[TaskType.EVENT_FIGHT] = TaskType.EVENT_FIGHT
    plan: CombatPlanRequest | None = Field(default=None)
    plan_id: str | None = Field(default=None)
    times: int = Field(default=1, ge=1)
    gap: float = Field(default=0.0, ge=0)
    fleet_id: int | None = Field(default=None, description='覆盖舰队')

    model_config = {'extra': 'forbid'}


class CampaignRequest(BaseModel):
    """战役请求。"""

    type: Literal[TaskType.CAMPAIGN] = TaskType.CAMPAIGN
    campaign_name: str = Field(description="战役名称，如 '困难航母'")
    times: int = Field(default=1, ge=1, description='执行次数')

    model_config = {'extra': 'forbid'}


class ExerciseRequest(BaseModel):
    """演习请求。"""

    type: Literal[TaskType.EXERCISE] = TaskType.EXERCISE
    fleet_id: int = Field(default=1, ge=1, le=6)

    model_config = {'extra': 'forbid'}


class DecisiveRequest(BaseModel):
    """决战请求。"""

    type: Literal[TaskType.DECISIVE] = TaskType.DECISIVE
    chapter: int = Field(default=6, ge=1, le=6, description='决战章节')
    decisive_rounds: int = Field(default=1, ge=1, description='决战执行轮数')
    use_new_fleet_change_algorithm: bool = Field(
        default=False,
        description='决战是否使用新的换船算法；关闭时使用原有流程',
    )
    level1: list[str] = Field(
        default_factory=lambda: [
            'U-1206',
            'U-96',
            'U-47',
            '鹦鹉螺',
            '鲃鱼',
            '伊-25',
        ],
        description='一级舰队',
    )
    level2: list[str] = Field(
        default_factory=lambda: ['M-296', '大青花鱼', 'U-1405'],
        description='二级舰队',
    )
    flagship_priority: list[str] = Field(
        default_factory=lambda: ['U-1206'],
        description='旗舰优先级',
    )
    use_quick_repair: bool = Field(
        default=True,
        description='是否启用快修（桶修），关闭后不修理受损舰船',
    )

    model_config = {'extra': 'forbid'}


TaskStartRequest = (
    NormalFightRequest | EventFightRequest | CampaignRequest | ExerciseRequest | DecisiveRequest
)


# ═══════════════════════════════════════════════════════════════════════════════
# 响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class TaskProgress(BaseModel):
    """任务进度。"""

    current: int = Field(default=0, description='当前轮次')
    total: int = Field(default=0, description='总轮次')
    node: str | None = Field(default=None, description='当前节点')


class RoundResult(BaseModel):
    """单轮战斗结果。"""

    round: int = Field(description='轮次')
    success: bool = Field(description='本轮是否成功')
    nodes: list[str] = Field(default_factory=list, description='经过的节点')
    mvp: str | None = Field(default=None, description='MVP 舰船')
    ship_damage: list[int] = Field(
        default_factory=list,
        description='舰船破损状态',
    )
    grade: str | None = Field(default=None, description='战果等级')
    node_count: int | None = Field(default=None, description='经过的节点数量')
    enemies: dict[str, dict[str, int]] | None = Field(default=None, description='各节点敌舰')
    events: list[dict[str, Any]] | None = Field(default=None, description='战斗事件')
    result: str | None = Field(default=None, description='任务专用结果')
    error: str | None = Field(default=None, description='本轮错误信息')

    model_config = {'extra': 'allow'}


class TaskResult(BaseModel):
    """任务完整结果。"""

    total_runs: int = Field(default=0, description='总执行次数')
    success_runs: int = Field(default=0, description='成功次数')
    details: list[RoundResult] = Field(default_factory=list, description='各轮详情')


class TaskStatusResponse(BaseModel):
    """任务状态响应。"""

    task_id: str | None = Field(default=None, description='任务ID')
    status: TaskStatusEnum = Field(default=TaskStatusEnum.IDLE, description='任务状态')
    progress: TaskProgress | None = Field(default=None, description='进度')
    result: TaskResult | None = Field(default=None, description='结果')
    error: str | None = Field(default=None, description='错误信息')


class SystemStatusResponse(BaseModel):
    """系统状态响应。"""

    status: TaskStatusEnum = Field(description='系统状态')
    emulator_connected: bool = Field(default=False, description='模拟器已连接')
    game_running: bool = Field(default=False, description='游戏运行中')
    current_task: str | None = Field(default=None, description='当前任务ID')


class LogMessage(BaseModel):
    """日志消息。"""

    timestamp: str = Field(description='时间戳 ISO 8601')
    level: LogLevel = Field(description='日志级别')
    channel: str = Field(default='', description='日志通道')
    message: str = Field(description='日志内容')


class ApiResponse[ResponseDataT](BaseModel):
    """通用 API 响应。"""

    success: bool = Field(description='是否成功')
    data: ResponseDataT | None = Field(default=None, description='响应数据')
    message: str | None = Field(default=None, description='消息')
    error: str | None = Field(default=None, description='错误信息')

    model_config = {'extra': 'forbid'}
