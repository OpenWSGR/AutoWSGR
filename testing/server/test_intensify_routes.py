from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from autowsgr.server import main as server_main
from autowsgr.server.device_lease import device_operation_lease
from autowsgr.server.intensify_preview_dependencies import IntensifyPreviewConfigurationError
from autowsgr.server.intensify_preview_service import (
    IntensifyPreviewDataError,
    IntensifyPreviewSelectionError,
    IntensifyPreviewSessionUnavailableError,
)
from autowsgr.server.routes import ops
from autowsgr.server.schemas import (
    AutoIntensifyRequest,
    IntensifyRequest,
    IntensifySnapshotPreviewRequest,
)
from autowsgr.ui.intensify_workflow import IntensifyPolicy, SelectionRef


def _policy() -> IntensifyRequest:
    return IntensifyRequest(
        target_ship='萤火虫',
        material_ship_types=['DD'],
        max_materials=4,
        protected_ships=['信赖'],
    )


def _automatic_policy() -> AutoIntensifyRequest:
    return AutoIntensifyRequest(
        material_ship_types=['DD'],
        max_materials=4,
        protected_ships=['信赖'],
    )


def _snapshot_preview_request() -> IntensifySnapshotPreviewRequest:
    return IntensifySnapshotPreviewRequest(
        session_id='snapshot-session',
        selected_target_ref='target:target-revision:0:0:0:0.1000:0.2000',
        allowed_material_identities=['素材舰'],
        maximum_materials=2,
        selected_material_refs=['material:revision:0:0:0:0.1000:0.2000'],
    )


def _snapshot_session() -> object:
    return SimpleNamespace(
        session_id='created-session',
        created_at=datetime(2026, 8, 24, 3, 0, tzinfo=UTC),
        expires_at=datetime(2026, 8, 24, 3, 10, tzinfo=UTC),
        target_snapshot=SimpleNamespace(
            total=266,
            revision='target-revision',
            targets=(
                SimpleNamespace(
                    ref=SelectionRef('target:target-revision:0:0:0:0.1000:0.2000'),
                    ship_id=7,
                    name='目标舰',
                    occurrence=0,
                    levels=SimpleNamespace(
                        firepower=1,
                        torpedo=2,
                        armor=3,
                        anti_air=4,
                    ),
                ),
            ),
        ),
        material_snapshot=SimpleNamespace(
            total=1,
            viewport_count=6,
            names=('素材舰',),
            ship_ids=(11,),
            refs=('material:material-revision:0:0:0:0.1000:0.2000',),
        ),
    )


def test_snapshot_session_scans_under_device_lease_and_returns_only_safe_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeScanService:
        def create_session(self) -> object:
            captured['lease_owner'] = device_operation_lease.owner
            return _snapshot_session()

    context = object()
    monkeypatch.setattr(ops, 'get_context', lambda: context)

    def provide_service(supplied: object) -> FakeScanService:
        captured['context'] = supplied
        return FakeScanService()

    monkeypatch.setattr(
        ops,
        'get_intensify_snapshot_scan_service',
        provide_service,
    )

    response = asyncio.run(ops.intensify_snapshot_session())

    assert response.success is True
    assert response.data == {
        'sessionId': 'created-session',
        'createdAt': '2026-08-24T03:00:00+00:00',
        'expiresAt': '2026-08-24T03:10:00+00:00',
        'targetTotal': 266,
        'targetRevision': 'target-revision',
        'materialTotal': 1,
        'materialViewportCount': 6,
        'targets': [
            {
                'ref': 'target:target-revision:0:0:0:0.1000:0.2000',
                'shipId': 7,
                'identity': '目标舰',
                'occurrence': 0,
                'current': {
                    'firepower': 1,
                    'torpedo': 2,
                    'armor': 3,
                    'antiAir': 4,
                },
            },
        ],
        'materials': [
            {
                'ref': 'material:material-revision:0:0:0:0.1000:0.2000',
                'shipId': 11,
                'identity': '素材舰',
                'index': 0,
            },
        ],
    }
    assert captured['context'] is context
    assert captured['lease_owner'] == 'api:intensify-snapshot-scan'
    assert device_operation_lease.owner is None


def test_snapshot_session_rejects_active_device_owner_before_context_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_reads = 0

    def get_context() -> object:
        nonlocal context_reads
        context_reads += 1
        return object()

    monkeypatch.setattr(ops, 'get_context', get_context)
    token = device_operation_lease.acquire('task:active')
    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(ops.intensify_snapshot_session())
    finally:
        device_operation_lease.release(token)

    assert exc_info.value.status_code == 409
    assert context_reads == 0


@pytest.mark.parametrize(
    'error',
    [
        IntensifyPreviewConfigurationError('未设置扫描资源'),
        ops.IntensifySnapshotScanError('扫描失败'),
    ],
)
def test_snapshot_session_maps_configuration_and_scan_failures_to_503(
    monkeypatch: pytest.MonkeyPatch,
    error: RuntimeError,
) -> None:
    context = object()
    monkeypatch.setattr(ops, 'get_context', lambda: context)

    def unavailable(_context: object) -> object:
        if isinstance(error, IntensifyPreviewConfigurationError):
            raise error
        return SimpleNamespace(create_session=lambda: (_ for _ in ()).throw(error))

    monkeypatch.setattr(ops, 'get_intensify_snapshot_scan_service', unavailable)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(ops.intensify_snapshot_session())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == str(error)
    assert device_operation_lease.owner is None


def test_intensify_preview_is_device_free_and_explicitly_non_executable() -> None:
    token = device_operation_lease.acquire('test-owner')
    try:
        response = asyncio.run(ops.intensify_preview(_policy()))
    finally:
        device_operation_lease.release(token)

    assert response.success is True
    assert response.data == {
        **_policy().model_dump(),
        'executable': False,
        'reason': response.data['reason'],
    }
    assert '未操作设备' in response.data['reason']


def test_snapshot_preview_is_device_free_and_uses_only_server_owned_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakePreviewService:
        def preview(self, command: object) -> dict[str, object]:
            captured['command'] = command
            captured['lease_owner'] = device_operation_lease.owner
            return {'executable': False, 'targets': [], 'materials': []}

    monkeypatch.setattr(ops, 'get_intensify_preview_service', FakePreviewService)
    token = device_operation_lease.acquire('test-owner')
    try:
        response = asyncio.run(ops.intensify_snapshot_preview(_snapshot_preview_request()))
    finally:
        device_operation_lease.release(token)

    assert response.success is True
    assert response.data == {'executable': False, 'targets': [], 'materials': []}
    assert '未操作设备' in response.message
    assert captured['lease_owner'] == 'test-owner'
    command = captured['command']
    assert command.session_id == 'snapshot-session'
    assert command.selected_target_ref == SelectionRef('target:target-revision:0:0:0:0.1000:0.2000')
    assert command.policy == IntensifyPolicy(frozenset({'素材舰'}), maximum_materials=2)
    assert command.selected_material_refs == (
        SelectionRef('material:revision:0:0:0:0.1000:0.2000'),
    )


@pytest.mark.parametrize(
    ('error', 'status_code'),
    [
        (IntensifyPreviewSessionUnavailableError('强化快照会话不可用'), 404),
        (IntensifyPreviewSelectionError('强化素材选择不可用'), 409),
        (IntensifyPreviewDataError('权威强化数据不可用'), 503),
    ],
)
def test_snapshot_preview_maps_service_failures_without_leaking_device_access(
    monkeypatch: pytest.MonkeyPatch,
    error: RuntimeError,
    status_code: int,
) -> None:
    class FailingPreviewService:
        def preview(self, _command: object) -> dict[str, object]:
            raise error

    monkeypatch.setattr(ops, 'get_intensify_preview_service', FailingPreviewService)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(ops.intensify_snapshot_preview(_snapshot_preview_request()))

    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == str(error)
    assert device_operation_lease.owner is None


def test_snapshot_preview_maps_missing_trusted_process_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_provider() -> object:
        raise IntensifyPreviewConfigurationError('未设置受信任资源路径')

    monkeypatch.setattr(ops, 'get_intensify_preview_service', unavailable_provider)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(ops.intensify_snapshot_preview(_snapshot_preview_request()))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == '未设置受信任资源路径'


@pytest.mark.parametrize('forbidden_field', ['strengthen_path', 'validation_proof'])
def test_snapshot_preview_request_rejects_caller_owned_authority_fields(
    forbidden_field: str,
) -> None:
    payload = _snapshot_preview_request().model_dump()
    payload[forbidden_field] = 'forbidden'

    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        IntensifySnapshotPreviewRequest.model_validate(payload)


def test_snapshot_preview_request_rejects_selection_beyond_policy_limit() -> None:
    with pytest.raises(ValidationError, match='maximum_materials'):
        IntensifySnapshotPreviewRequest(
            session_id='snapshot-session',
            selected_target_ref='target:target-revision:0:0:0:0.1000:0.2000',
            allowed_material_identities=['素材舰'],
            maximum_materials=1,
            selected_material_refs=['material:one', 'material:two'],
        )


def test_intensify_requests_accept_null_material_limit_as_unlimited() -> None:
    execute = AutoIntensifyRequest(
        material_ship_types=None,
        max_materials=None,
    )
    preview = IntensifySnapshotPreviewRequest(
        session_id='snapshot-session',
        selected_target_ref='target:target-revision:0:0:0:0.1000:0.2000',
        allowed_material_identities=['素材舰'],
        maximum_materials=None,
        selected_material_refs=['material:one', 'material:two'],
    )

    assert execute.max_materials is None
    assert preview.maximum_materials is None


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('selected_target_ref', ' '),
        ('allowed_material_identities', ['素材舰', ' ']),
        ('selected_material_refs', ['material:one', ' ']),
    ],
)
def test_snapshot_preview_request_rejects_blank_exact_values(
    field: str,
    value: str | list[str],
) -> None:
    payload = _snapshot_preview_request().model_dump()
    payload[field] = value

    with pytest.raises(ValidationError, match=r'不能为空|非空字符串列表'):
        IntensifySnapshotPreviewRequest.model_validate(payload)


@pytest.mark.parametrize(
    ('path', 'model_name'),
    [
        ('/api/intensify/snapshot-sessions', 'IntensifySnapshotSessionResponse'),
        ('/api/intensify/snapshot-preview', 'IntensifySnapshotPreviewResponse'),
    ],
)
def test_snapshot_openapi_exposes_typed_data(path: str, model_name: str) -> None:
    schema = server_main.app.openapi()
    response_schema = schema['paths'][path]['post']['responses']['200']['content'][
        'application/json'
    ]['schema']
    response_model_name = response_schema['$ref'].rsplit('/', 1)[-1]
    data_schema = schema['components']['schemas'][response_model_name]['properties']['data']

    assert model_name in str(data_schema)


def test_intensify_execute_fails_closed_without_touching_device() -> None:
    response = asyncio.run(ops.intensify_action(_automatic_policy()))

    assert response.success is False
    assert response.error is not None
    assert '安全中止' in response.error
    assert device_operation_lease.owner is None


def test_intensify_execute_obeys_device_lease() -> None:
    token = device_operation_lease.acquire('test-owner')
    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(ops.intensify_action(_automatic_policy()))
    finally:
        device_operation_lease.release(token)

    assert exc_info.value.status_code == 409
    assert 'test-owner' in exc_info.value.detail


def test_intensify_execute_passes_request_policy_to_automatic_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    context = object()

    def fake_auto_intensify(supplied_context: object, **options: object) -> object:
        captured['context'] = supplied_context
        captured['options'] = options
        return SimpleNamespace(
            success=True,
            total_batches=0,
            total_materials_used=0,
            elapsed_seconds=0.0,
            batches=[],
            message='done',
        )

    monkeypatch.setattr(ops, 'get_context', lambda: context)
    monkeypatch.setattr('autowsgr.ops.intensify.auto_intensify', fake_auto_intensify)

    request = _automatic_policy().model_copy(update={'max_materials': None})
    response = asyncio.run(ops.intensify_action(request))

    assert response.success is True
    assert captured == {
        'context': context,
        'options': {
            'material_ship_types': frozenset({'dd'}),
            'maximum_materials': None,
            'protected_material_identities': frozenset({'信赖'}),
            'reuse_target_inventory_baseline': False,
        },
    }


def test_intensify_execute_omitted_request_retains_execution_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_auto_intensify(_context: object, **options: object) -> object:
        captured['options'] = options
        return SimpleNamespace(
            success=True,
            total_batches=0,
            total_materials_used=0,
            elapsed_seconds=0.0,
            batches=[],
            message='done',
        )

    context = SimpleNamespace(
        config=SimpleNamespace(
            intensify=SimpleNamespace(
                material_ship_types=['dd'],
                max_materials=4,
                protected_ships=['信赖'],
            )
        )
    )
    monkeypatch.setattr(ops, 'get_context', lambda: context)
    monkeypatch.setattr('autowsgr.ops.intensify.auto_intensify', fake_auto_intensify)

    response = asyncio.run(ops.intensify_action())

    assert response.success is True
    assert captured['options'] == {
        'material_ship_types': frozenset({'dd'}),
        'maximum_materials': 4,
        'protected_material_identities': frozenset({'信赖'}),
        'reuse_target_inventory_baseline': False,
    }


def test_auto_intensify_request_rejects_target_authority_fields() -> None:
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        AutoIntensifyRequest.model_validate(
            {
                'target_ship': '萤火虫',
                'material_ship_types': ['DD'],
                'max_materials': 4,
                'protected_ships': [],
            }
        )


def test_auto_intensify_request_accepts_finite_limit_above_legacy_cap() -> None:
    assert AutoIntensifyRequest(max_materials=41).max_materials == 41


def test_intensify_policy_rejects_target_in_protected_list() -> None:
    with pytest.raises(ValueError, match='保护名单'):
        IntensifyRequest(
            target_ship='萤火虫',
            material_ship_types=['DD'],
            max_materials=4,
            protected_ships=['萤火虫'],
        )
