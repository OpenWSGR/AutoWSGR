"""测试 autowsgr.server.schemas。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from autowsgr.server.schemas import (
    ApiResponse,
    CombatPlanRequest,
    DecisiveRequest,
    FleetRuleRequest,
    LogLevel,
    NodeDecisionRequest,
    NormalFightRequest,
    SystemStatusResponse,
    TaskProgress,
    TaskResult,
    TaskStatusEnum,
    TaskStatusResponse,
    TaskType,
)


def test_task_type_values() -> None:
    """TaskType 应包含预期的枚举值。"""
    assert TaskType.NORMAL_FIGHT == 'normal_fight'
    assert TaskType.EVENT_FIGHT == 'event_fight'


def test_task_status_enum_values() -> None:
    """TaskStatusEnum 应包含预期的状态值。"""
    assert TaskStatusEnum.RUNNING == 'running'
    assert TaskStatusEnum.FAILED == 'failed'


def test_log_level_values() -> None:
    """LogLevel 应包含预期的日志级别。"""
    assert LogLevel.DEBUG == 'DEBUG'
    assert LogLevel.ERROR == 'ERROR'


def test_node_decision_request_defaults() -> None:
    """NodeDecisionRequest 默认值应符合预期。"""
    nd = NodeDecisionRequest()
    assert nd.formation == 2
    assert nd.night is False
    assert nd.proceed is True


def test_node_decision_request_formation_bounds() -> None:
    """formation 超出 1-5 应校验失败。"""
    with pytest.raises(ValidationError):
        NodeDecisionRequest(formation=0)
    with pytest.raises(ValidationError):
        NodeDecisionRequest(formation=6)


def test_fleet_rule_request_candidates_empty() -> None:
    """candidates 全空时应校验失败。"""
    with pytest.raises(ValidationError, match='candidates 不能为空'):
        FleetRuleRequest(candidates=['', '  '])


def test_fleet_rule_request_ship_type_invalid() -> None:
    """ship_type 不在白名单时应校验失败。"""
    with pytest.raises(ValidationError, match='ship_type 不合法'):
        FleetRuleRequest(candidates=['A'], ship_type='xx')


def test_fleet_rule_request_level_range() -> None:
    """max_level < min_level 时应校验失败。"""
    with pytest.raises(ValidationError, match='max_level 必须大于或等于 min_level'):
        FleetRuleRequest(candidates=['A'], min_level=10, max_level=5)


def test_combat_plan_request_defaults() -> None:
    """CombatPlanRequest 默认值应符合预期。"""
    plan = CombatPlanRequest()
    assert plan.fleet_id == 1
    assert plan.repair_mode == [2, 2, 2, 2, 2, 2]


def test_normal_fight_request_defaults() -> None:
    """NormalFightRequest 默认值应符合预期。"""
    req = NormalFightRequest()
    assert req.times == 1
    assert req.gap == 0.0
    assert req.type == 'normal_fight'


def test_decisive_request_defaults() -> None:
    """DecisiveRequest 默认值应符合预期。"""
    req = DecisiveRequest()
    assert req.chapter == 6
    assert req.use_quick_repair is True
    assert len(req.level1) > 0


def test_api_response_serialization() -> None:
    """ApiResponse 应能正确序列化。"""
    resp = ApiResponse(success=True, data={'key': 'value'}, message='ok')
    assert resp.model_dump()['success'] is True
    assert resp.model_dump()['data'] == {'key': 'value'}


def test_task_status_response_defaults() -> None:
    """TaskStatusResponse 默认值应符合预期。"""
    ts = TaskStatusResponse()
    assert ts.status == TaskStatusEnum.IDLE
    assert ts.task_id is None


def test_task_result_defaults() -> None:
    """TaskResult 默认值应符合预期。"""
    tr = TaskResult()
    assert tr.total_runs == 0
    assert tr.details == []


def test_system_status_response() -> None:
    """SystemStatusResponse 应正确存储状态。"""
    ss = SystemStatusResponse(status=TaskStatusEnum.RUNNING, emulator_connected=True)
    assert ss.status == 'running'
    assert ss.emulator_connected is True


def test_task_progress() -> None:
    """TaskProgress 应正确存储进度信息。"""
    tp = TaskProgress(current=3, total=10, node='B')
    assert tp.current == 3
    assert tp.total == 10
    assert tp.node == 'B'
