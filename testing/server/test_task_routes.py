"""Task route admission tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import HTTPException

import autowsgr.ops.normal_fight as normal_fight_module
from autowsgr import ops
from autowsgr.combat import CombatPlan, CombatResult
from autowsgr.combat.fleet import FleetSelectionSource, ResolvedFleetSelection
from autowsgr.server import main as server_main
from autowsgr.server.device_lease import DeviceOperationBusyError
from autowsgr.server.routes import task
from autowsgr.server.schemas import (
    ApiResponse,
    CampaignRequest,
    CombatPlanRequest,
    DecisiveRequest,
    EventFightRequest,
    ExerciseRequest,
    FleetRuleRequest,
    NodeDecisionRequest,
    NormalFightRequest,
    RoundResult,
    TaskStatusResponse,
)
from autowsgr.types import ConditionFlag, ShipType


if TYPE_CHECKING:
    from pathlib import Path

    from autowsgr.server.task_manager import TaskOutcome


if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.server.task_manager import TaskOutcome


@dataclass
class _TaskManager:
    is_running: bool = False
    stop_event: object = field(default_factory=object)


@dataclass
class _ExecutingTaskManager:
    """同步执行 route 创建的 executor，避免测试启动后台线程。"""

    is_running: bool = False
    stop_event: object = field(default_factory=object)
    outcome: TaskOutcome | None = None
    results: list[dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def should_stop() -> bool:
        return False

    @staticmethod
    def update_progress(**_progress: object) -> None:
        return None

    def add_result(self, result: dict[str, Any]) -> None:
        self.results.append(result)

    def start_task(
        self,
        *args: object,
        task_type: str | None = None,
        total_rounds: int | None = None,
        executor: Callable[[object], TaskOutcome] | None = None,
    ) -> str:
        if args:
            _task_type, _total_rounds, executor = args
        del task_type, total_rounds
        assert executor is not None
        self.outcome = executor(object())
        return 'task_test'


def test_task_start_rejects_concurrent_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task admission rejects a second running task under the lifecycle lock."""
    monkeypatch.setattr(task, 'task_manager', _TaskManager(is_running=True))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(task.task_start(ExerciseRequest()))

    assert exc_info.value.status_code == 409


def test_task_start_requires_system_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task admission fails after system shutdown removed the context."""
    monkeypatch.setattr(task, 'task_manager', _TaskManager())
    monkeypatch.setattr(server_main, '_ctx', None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(task.task_start(ExerciseRequest()))

    assert exc_info.value.status_code == 503


def test_campaign_route_preserves_out_of_times_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Campaign terminal reason reaches the task outcome consumed by the GUI."""
    manager = _ExecutingTaskManager()

    class CampaignRunnerStub:
        def __init__(
            self,
            _ctx: object,
            *,
            campaign_name: str,
            times: int,
        ) -> None:
            assert campaign_name == '困难航母'
            assert times == 1

        @staticmethod
        def run() -> list[CombatResult]:
            return [CombatResult(flag=ConditionFlag.BATTLE_TIMES_EXCEED)]

    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(ops, 'CampaignRunner', CampaignRunnerStub)

    response = asyncio.run(
        task._start_campaign(
            object(),
            CampaignRequest(campaign_name='困难航母', times=1),
        )
    )

    assert response.success is True
    assert manager.outcome is not None
    assert manager.outcome.success is False
    assert manager.outcome.results[0]['success'] is False
    assert manager.outcome.results[0]['result'] == ConditionFlag.BATTLE_TIMES_EXCEED.value
    assert manager.results == manager.outcome.results


def test_task_start_reports_device_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task lease conflicts are returned synchronously as HTTP 409."""
    manager = _TaskManager()
    ctx = type('Context', (), {'stop_event': None})()

    async def busy_start(_ctx: object, _request: ExerciseRequest) -> object:
        raise DeviceOperationBusyError('设备正由 api:repair 使用')

    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(server_main, '_ctx', ctx)
    monkeypatch.setattr(task, '_start_exercise', busy_start)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(task.task_start(ExerciseRequest()))

    assert exc_info.value.status_code == 409


@pytest.mark.parametrize(
    ('task_request', 'helper_name'),
    [
        (NormalFightRequest(plan_id='plan.yaml'), '_start_normal_fight'),
        (EventFightRequest(plan_id='event.yaml'), '_start_event_fight'),
        (CampaignRequest(campaign_name='困难航母'), '_start_campaign'),
        (ExerciseRequest(), '_start_exercise'),
        (DecisiveRequest(), '_start_decisive'),
    ],
)
def test_task_start_dispatches_request_with_shared_context(
    monkeypatch: pytest.MonkeyPatch,
    task_request: object,
    helper_name: str,
) -> None:
    """Each supported request is admitted with the current context and stop token."""
    manager = _TaskManager()
    ctx = type('Context', (), {'stop_event': None})()
    calls: list[tuple[object, object]] = []
    response = object()

    async def start_helper(received_ctx: object, received_request: object) -> object:
        calls.append((received_ctx, received_request))
        return response

    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(server_main, '_ctx', ctx)
    monkeypatch.setattr(task, helper_name, start_helper)

    result = asyncio.run(task.task_start(task_request))  # type: ignore[arg-type]

    assert result is response
    assert calls == [(ctx, task_request)]
    assert ctx.stop_event is manager.stop_event


def test_decisive_error_result_marks_task_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A decisive ERROR is a task failure, not a successful completed round."""
    from autowsgr import ops
    from autowsgr.ops import DecisiveResult

    class ErrorController:
        def __init__(self, _ctx: object, _config: object) -> None:
            pass

        def run(self) -> DecisiveResult:
            return DecisiveResult.ERROR

    manager = _ExecutingTaskManager()
    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(ops, 'DecisiveController', ErrorController)

    asyncio.run(task._start_decisive(object(), DecisiveRequest()))

    assert manager.outcome is not None
    assert manager.outcome.success is False
    assert manager.outcome.error == '决战异常退出'
    assert manager.outcome.results == [
        {
            'round': 1,
            'success': False,
            'result': 'error',
            'error': '决战异常退出',
        }
    ]


def test_decisive_leave_result_remains_successful(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An intentional decisive leave remains a successful terminal result."""
    from autowsgr import ops
    from autowsgr.ops import DecisiveResult

    class LeaveController:
        def __init__(self, _ctx: object, _config: object) -> None:
            pass

        def run(self) -> DecisiveResult:
            return DecisiveResult.LEAVE

    manager = _ExecutingTaskManager()
    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(ops, 'DecisiveController', LeaveController)

    asyncio.run(task._start_decisive(object(), DecisiveRequest()))

    assert manager.outcome is not None
    assert manager.outcome.success is True
    assert manager.outcome.error is None
    assert manager.outcome.results == [{'round': 1, 'success': True, 'result': 'leave'}]


@pytest.mark.parametrize(
    'detail',
    [
        {
            'round': 1,
            'success': True,
            'nodes': ['A', 'B'],
            'mvp': '位置1',
            'grade': 'S',
            'ship_damage': [0, 1],
            'node_count': 2,
            'enemies': {'B': {'DD': 2}},
            'events': [{'type': 'FIGHT', 'node': 'B', 'custom': 'kept'}],
        },
        {'round': 2, 'success': False, 'error': 'fleet change failed'},
        {'round': 3, 'success': True, 'result': 'leave'},
    ],
)
def test_round_result_schema_preserves_existing_detail_shapes(
    detail: dict[str, Any],
) -> None:
    """Typed task results must not strip or synthesize detail fields."""
    assert RoundResult.model_validate(detail).model_dump(exclude_unset=True) == detail


def test_task_status_openapi_exposes_typed_data() -> None:
    """The status endpoint documents TaskStatusResponse instead of untyped Any."""
    schema = server_main.app.openapi()
    response_schema = schema['paths']['/api/task/status']['get']['responses']['200']['content'][
        'application/json'
    ]['schema']
    response_model_name = response_schema['$ref'].rsplit('/', 1)[-1]
    data_schema = schema['components']['schemas'][response_model_name]['properties']['data']

    assert 'TaskStatusResponse' in str(data_schema)


def test_typed_task_status_preserves_terminal_wire_payload() -> None:
    """Typed envelope round-trips terminal details without adding absent fields."""
    payload = {
        'success': True,
        'data': {
            'task_id': 'task_1234',
            'status': 'failed',
            'progress': None,
            'result': {
                'total_runs': 2,
                'success_runs': 1,
                'details': [
                    {'round': 1, 'success': True, 'result': 'leave'},
                    {'round': 2, 'success': False, 'error': 'fleet change failed'},
                ],
            },
            'error': 'fleet change failed',
        },
    }

    response = ApiResponse[TaskStatusResponse].model_validate(payload)

    assert response.model_dump(mode='json', exclude_unset=True) == payload


def test_task_status_returns_typed_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """The route validates manager status through its typed response contract."""
    status = {
        'task_id': None,
        'status': 'idle',
        'progress': None,
        'result': None,
    }
    monkeypatch.setattr(task.task_manager, 'get_status', lambda: status)

    response = asyncio.run(task.task_status())

    assert isinstance(response, ApiResponse)
    assert isinstance(response.data, TaskStatusResponse)
    assert response.model_dump(mode='json', exclude_unset=True) == {
        'success': True,
        'data': status,
    }


@pytest.mark.parametrize(
    'route_case',
    [
        ('_start_normal_fight', NormalFightRequest, 'run_normal_fight'),
        ('_start_event_fight', EventFightRequest, 'run_event_fight'),
    ],
)
@pytest.mark.parametrize(
    ('fleet_source', 'expected_source', 'expected_name'),
    [
        ('api_rules', FleetSelectionSource.OVERRIDE_RULES, 'API规则舰'),
        ('api_fleet', FleetSelectionSource.OVERRIDE_FLEET, 'API普通舰'),
        ('yaml_preset', FleetSelectionSource.PLAN_PRESET, 'YAML预设舰'),
        ('yaml_fleet', FleetSelectionSource.PLAN_FLEET, 'YAML普通舰'),
    ],
)
def test_fight_routes_resolve_all_fleet_sources_before_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    route_case: tuple[
        str,
        type[NormalFightRequest | EventFightRequest],
        str,
    ],
    fleet_source: str,
    expected_source: FleetSelectionSource,
    expected_name: str,
) -> None:
    """normal/event route 都只向 runner 传递解析完成的 canonical selection。"""
    helper_name, request_type, run_name = route_case
    manager = _ExecutingTaskManager()
    captured: list[ResolvedFleetSelection] = []

    def run_fight(
        _ctx: object,
        _plan: object,
        *,
        times: int,
        fleet_selection: ResolvedFleetSelection,
    ) -> list[CombatResult]:
        assert times == 1
        captured.append(fleet_selection)
        return [CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)]

    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(ops, run_name, run_fight)

    if fleet_source == 'api_rules':
        plan_request = CombatPlanRequest(
            fleet_id=3,
            fleet=['被规则覆盖的API舰'],
            fleet_rules=[
                FleetRuleRequest(
                    name=expected_name,
                    ship_type=['kp'],
                    min_level=90,
                ),
            ],
        )
        request = request_type(plan=plan_request)
    elif fleet_source == 'api_fleet':
        request = request_type(
            plan=CombatPlanRequest(
                fleet_id=3,
                fleet=[expected_name],
            ),
        )
    else:
        yaml_path = tmp_path / f'{fleet_source}.yaml'
        preset = (
            '\nfleet_presets:\n'
            '  - name: route测试\n'
            '    ships:\n'
            f'      - name: {expected_name}\n'
            '        ship_type: [cg]\n'
            if fleet_source == 'yaml_preset'
            else ''
        )
        yaml_path.write_text(
            f'chapter: 1\nmap: 1\nfleet_id: 2\nfleet:\n  - {expected_name}\n{preset}',
            encoding='utf-8',
        )
        request = request_type(plan_id=str(yaml_path))

    response = asyncio.run(getattr(task, helper_name)(object(), request))

    assert response.success is True
    assert manager.outcome is not None
    assert manager.outcome.success is True
    assert len(captured) == 1
    selection = captured[0]
    assert selection.source is expected_source
    assert selection.fleet_id == (3 if fleet_source.startswith('api_') else 2)
    assert selection.primary_names == [expected_name]
    if fleet_source == 'api_rules':
        assert selection.slot_rules is not None
        assert selection.slot_rules[0].primary is not None
        assert selection.slot_rules[0].primary.ship_types == (ShipType.KP,)
    elif fleet_source == 'yaml_preset':
        assert selection.slot_rules is not None
        assert selection.slot_rules[0].primary is not None
        assert selection.slot_rules[0].primary.ship_types == (ShipType.CG,)


def test_event_route_top_level_fleet_id_overrides_api_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _ExecutingTaskManager()
    captured: list[ResolvedFleetSelection] = []

    def run_event_fight(
        _ctx: object,
        _plan: object,
        *,
        times: int,
        fleet_selection: ResolvedFleetSelection,
    ) -> list[CombatResult]:
        assert times == 1
        captured.append(fleet_selection)
        return [CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)]

    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(ops, 'run_event_fight', run_event_fight)
    request = EventFightRequest(
        plan=CombatPlanRequest(fleet_id=3, fleet=['岛风']),
        fleet_id=5,
    )

    asyncio.run(task._start_event_fight(object(), request))

    assert captured[0].fleet_id == 5


def test_normal_route_applies_explicit_node_overrides_to_yaml_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """GUI 随请求发送的节点阵型应覆盖入队时生成的 YAML 快照。"""
    manager = _ExecutingTaskManager()
    captured: list[CombatPlan] = []

    def run_normal_fight(
        _ctx: object,
        plan: CombatPlan,
        *,
        times: int,
        fleet_selection: ResolvedFleetSelection,
    ) -> list[CombatResult]:
        assert times == 1
        assert fleet_selection.fleet_id == 1
        captured.append(plan)
        return [CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)]

    yaml_path = tmp_path / 'node-formation.yaml'
    yaml_path.write_text(
        '\n'.join(
            [
                'chapter: 7',
                'map: 4',
                'selected_nodes: [A, B]',
                'node_defaults:',
                '  formation: 2',
                'node_args:',
                '  B:',
                '    formation: 3',
                '    sl_when_detour_fails: false',
                '',
            ],
        ),
        encoding='utf-8',
    )
    request = NormalFightRequest(
        plan_id=str(yaml_path),
        plan=CombatPlanRequest(
            node_defaults=NodeDecisionRequest(formation=2),
            node_args={
                'B': NodeDecisionRequest(
                    formation=4,
                    night=True,
                    long_missile_support=True,
                    proceed=False,
                    SL_when_detour_fails=True,
                )
            },
        ),
    )
    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(ops, 'run_normal_fight', run_normal_fight)

    response = asyncio.run(task._start_normal_fight(object(), request))

    assert response.success is True
    assert len(captured) == 1
    decision = captured[0].get_node_decision('B')
    assert decision.formation.value == 4
    assert decision.night is True
    assert decision.long_missile_support is True
    assert decision.proceed is False
    assert decision.SL_when_detour_fails is True
    assert not hasattr(decision, 'sl_when_detour_fails')


def test_normal_route_enters_real_runner_with_resolved_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP route reaches the public ops entry and constructs the real runner."""
    manager = _ExecutingTaskManager()
    captured: list[ResolvedFleetSelection] = []

    def run_for_times(
        runner: object,
        times: int,
        *,
        gap: float = 0.0,
        **_kwargs: object,
    ) -> list[CombatResult]:
        assert times == 1
        assert gap == 0.0
        assert isinstance(runner, normal_fight_module.NormalFightRunner)
        captured.append(runner._fleet_selection)
        return [CombatResult(flag=ConditionFlag.OPERATION_SUCCESS)]

    monkeypatch.setattr(task, 'task_manager', manager)
    monkeypatch.setattr(normal_fight_module.NormalFightRunner, 'run_for_times', run_for_times)

    request = NormalFightRequest(
        plan=CombatPlanRequest(
            fleet_id=4,
            fleet_rules=[FleetRuleRequest(name='真实 runner 舰', ship_type=['kp'])],
        ),
    )

    ctx = SimpleNamespace(
        ctrl=None,
        config=SimpleNamespace(dock_full_destroy=False, destroy_ship_types=None),
    )
    response = asyncio.run(task._start_normal_fight(ctx, request))

    assert response.success is True
    assert manager.outcome is not None
    assert manager.outcome.success is True
    assert len(captured) == 1
    assert captured[0].source is FleetSelectionSource.OVERRIDE_RULES
    assert captured[0].fleet_id == 4
    assert captured[0].primary_names == ['真实 runner 舰']
