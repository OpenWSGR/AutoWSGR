"""操作端点路由 — 远征收取、建造、奖励、烹饪、修理、解装。"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from autowsgr.infra.logger import get_logger
from autowsgr.server.device_lease import exclusive_device_operation
from autowsgr.server.intensify_preview_dependencies import (
    IntensifyPreviewConfigurationError,
    get_intensify_preview_service,
    get_intensify_snapshot_scan_service,
)
from autowsgr.server.intensify_preview_service import (
    IntensifyPreviewCommand,
    IntensifyPreviewDataError,
    IntensifyPreviewSelectionError,
    IntensifyPreviewSessionUnavailableError,
)
from autowsgr.server.intensify_snapshot_scan_service import IntensifySnapshotScanError
from autowsgr.server.schemas import (
    ApiResponse,
    AutoIntensifyRequest,
    IntensifyRequest,
    IntensifySnapshotPreviewRequest,
    IntensifySnapshotPreviewResponse,
    IntensifySnapshotSessionResponse,
)
from autowsgr.server.serializers import (
    serialize_intensify_material_inventory,
    serialize_intensify_target_inventory,
)
from autowsgr.ui.intensify_workflow import IntensifyPolicy, SelectionRef

from ..main import get_context


_log = get_logger('server')

router = APIRouter(tags=['ops'])


_INTENSIFY_UNAVAILABLE = (
    '强化执行尚未接入可验证的主页收益、确认弹窗和结果回执识别；已安全中止且未操作设备'
)


@router.post(
    '/api/intensify/snapshot-sessions',
    response_model=ApiResponse[IntensifySnapshotSessionResponse],
)
@exclusive_device_operation('api:intensify-snapshot-scan')
async def intensify_snapshot_session() -> ApiResponse[IntensifySnapshotSessionResponse]:
    """Scan both complete inventories and publish one short-lived read-only session."""
    try:
        context = get_context()
        service = get_intensify_snapshot_scan_service(context)
        session = await asyncio.to_thread(service.create_session)
        targets = serialize_intensify_target_inventory(session.target_snapshot)
        materials = serialize_intensify_material_inventory(session.material_snapshot)
    except (IntensifyPreviewConfigurationError, IntensifySnapshotScanError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return ApiResponse(
        success=True,
        data={
            'sessionId': session.session_id,
            'createdAt': session.created_at.isoformat(),
            'expiresAt': session.expires_at.isoformat(),
            'targetTotal': session.target_snapshot.total,
            'targetRevision': session.target_snapshot.revision,
            'materialTotal': session.material_snapshot.total,
            'materialViewportCount': session.material_snapshot.viewport_count,
            'targets': targets,
            'materials': materials,
        },
        message='强化目标与素材库存只读快照已创建；未选择舰船且不可执行',
    )


@router.post('/api/intensify/preview', response_model=ApiResponse)
async def intensify_preview(request: IntensifyRequest) -> ApiResponse:
    """Validate a manual policy without acquiring or reading the shared device."""
    return ApiResponse(
        success=True,
        data={
            **request.model_dump(),
            'executable': False,
            'reason': _INTENSIFY_UNAVAILABLE,
        },
        message='强化策略已校验；当前执行链保持关闭',
    )


@router.post(
    '/api/intensify/snapshot-preview',
    response_model=ApiResponse[IntensifySnapshotPreviewResponse],
)
async def intensify_snapshot_preview(
    request: IntensifySnapshotPreviewRequest,
) -> ApiResponse[IntensifySnapshotPreviewResponse]:
    """Preview exact server-owned inventory occurrences without touching the device."""
    command = IntensifyPreviewCommand(
        session_id=request.session_id,
        selected_target_ref=SelectionRef(request.selected_target_ref),
        policy=IntensifyPolicy(
            frozenset(request.allowed_material_identities),
            maximum_materials=request.maximum_materials,
        ),
        selected_material_refs=tuple(
            SelectionRef(value) for value in request.selected_material_refs
        ),
    )
    try:
        service = get_intensify_preview_service()
        payload = await asyncio.to_thread(service.preview, command)
    except IntensifyPreviewSessionUnavailableError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except IntensifyPreviewSelectionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (IntensifyPreviewConfigurationError, IntensifyPreviewDataError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return ApiResponse(
        success=True,
        data=payload,
        message='强化快照候选预览已生成；未操作设备且不可执行',
    )


@router.post('/api/intensify', response_model=ApiResponse)
@exclusive_device_operation('api:intensify')
async def intensify_action(request: AutoIntensifyRequest | None = None) -> ApiResponse:
    """执行自动强化流程（持有设备独占 Lease）。"""
    try:
        ctx = get_context()
    except RuntimeError:
        return ApiResponse(success=False, error=_INTENSIFY_UNAVAILABLE)

    from autowsgr.ops.intensify import auto_intensify

    execution_policy = ctx.config.intensify if request is None else request
    material_ship_types = execution_policy.material_ship_types
    maximum_materials = execution_policy.max_materials
    protected_ships = execution_policy.protected_ships

    try:
        result = await asyncio.to_thread(
            auto_intensify,
            ctx,
            material_ship_types=(
                None if material_ship_types is None else frozenset(material_ship_types)
            ),
            maximum_materials=maximum_materials,
            protected_material_identities=frozenset(protected_ships),
        )
        return ApiResponse(
            success=result.success,
            data={
                'totalBatches': result.total_batches,
                'totalMaterialsUsed': result.total_materials_used,
                'elapsedSeconds': result.elapsed_seconds,
                'batches': [
                    {
                        'targetName': b.target_name,
                        'targetIndex': b.target_index,
                        'materials': b.materials,
                        'gains': {
                            'firepower': b.gains.firepower,
                            'torpedo': b.gains.torpedo,
                            'armor': b.gains.armor,
                            'antiAir': b.gains.anti_air,
                        },
                        'statsBefore': {
                            'firepower': b.stats_before.firepower,
                            'torpedo': b.stats_before.torpedo,
                            'armor': b.stats_before.armor,
                            'antiAir': b.stats_before.anti_air,
                        },
                        'statsAfter': {
                            'firepower': b.stats_after.firepower,
                            'torpedo': b.stats_after.torpedo,
                            'armor': b.stats_after.armor,
                            'antiAir': b.stats_after.anti_air,
                        },
                    }
                    for b in result.batches
                ],
            },
            message=result.message,
        )
    except Exception as e:
        _log.opt(exception=True).warning('[API] 自动强化失败: {}', e)
        return ApiResponse(success=False, error=str(e))


# ── 远征收取 ──


@router.post('/api/expedition/check', response_model=ApiResponse)
@exclusive_device_operation('api:expedition-check')
async def expedition_check() -> ApiResponse:
    """检查并收取已完成的远征。"""
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from autowsgr.ops.expedition import collect_expedition

    try:
        result = await asyncio.to_thread(collect_expedition, ctx)
        return ApiResponse(
            success=True,
            data={'collected': result},
            message='远征检查完成',
        )
    except Exception as e:
        _log.opt(exception=True).warning('[API] 远征检查失败: {}', e)
        return ApiResponse(success=False, error=str(e))


class ExpeditionAutoCheckRequest(BaseModel):
    """自动远征检查请求。"""

    allow_repair: bool = True
    """是否允许执行浴室维修。前端在队列中还有后续战斗任务时可设为 False。"""


@router.post('/api/expedition/auto_check', response_model=ApiResponse)
@exclusive_device_operation('api:expedition-auto-check')
async def expedition_auto_check(request: ExpeditionAutoCheckRequest) -> ApiResponse:
    """自动远征检查（挂机专用）。

    顺带领取任务奖励并根据调用方配置决定是否执行浴室维修。
    """
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from autowsgr.ops.expedition import collect_expedition
    from autowsgr.ops.repair import repair_in_bath
    from autowsgr.ops.reward import collect_rewards

    results: dict[str, Any] = {}

    # 1. 远征收取
    try:
        results['expedition'] = await asyncio.to_thread(collect_expedition, ctx)
    except Exception as e:
        _log.opt(exception=True).warning('[API] 自动远征检查: 远征收取失败: {}', e)
        results['expedition_error'] = str(e)

    # 2. 任务奖励
    try:
        results['rewards'] = await asyncio.to_thread(collect_rewards, ctx)
    except Exception as e:
        _log.opt(exception=True).warning('[API] 自动远征检查: 奖励领取失败: {}', e)
        results['rewards_error'] = str(e)

    # 3. 浴室维修
    if not request.allow_repair:
        _log.info('[API] 自动远征检查: 前端禁止维修（队列中还有后续任务），跳过浴室维修')
        results['repair_skipped'] = True
        results['repair_reason'] = '队列中有后续战斗任务'
    else:
        try:
            await asyncio.to_thread(repair_in_bath, ctx)
            results['repair'] = True
        except Exception as e:
            _log.opt(exception=True).warning('[API] 自动远征检查: 浴室维修失败: {}', e)
            results['repair_error'] = str(e)

    return ApiResponse(
        success=True,
        data=results,
        message='自动远征检查完成',
    )


# ── 建造操作 ──


class BuildStartRequest(BaseModel):
    """建造请求。"""

    fuel: int = 30
    ammo: int = 30
    steel: int = 30
    bauxite: int = 30
    build_type: str = 'ship'
    allow_fast_build: bool = False


@router.post('/api/build/collect', response_model=ApiResponse)
@exclusive_device_operation('api:build-collect')
async def build_collect() -> ApiResponse:
    """收取已完成的建造。"""
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from autowsgr.ops import collect_built_ships

    try:
        count = await asyncio.to_thread(collect_built_ships, ctx)
        return ApiResponse(success=True, data={'collected': count}, message=f'收取了 {count} 艘')
    except Exception as e:
        _log.opt(exception=True).warning('[API] 收取建造失败: {}', e)
        return ApiResponse(success=False, error=str(e))


@router.post('/api/build/start', response_model=ApiResponse)
@exclusive_device_operation('api:build-start')
async def build_start(request: BuildStartRequest) -> ApiResponse:
    """开始建造。"""
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from autowsgr.ops import BuildRecipe, build_ship

    recipe = BuildRecipe(
        fuel=request.fuel,
        ammo=request.ammo,
        steel=request.steel,
        bauxite=request.bauxite,
    )

    try:
        await asyncio.to_thread(
            build_ship,
            ctx,
            recipe=recipe,
            build_type=request.build_type,
            allow_fast_build=request.allow_fast_build,
        )
        return ApiResponse(success=True, message='建造已开始')
    except Exception as e:
        _log.opt(exception=True).warning('[API] 建造失败: {}', e)
        return ApiResponse(success=False, error=str(e))


# ── 任务奖励 ──


@router.post('/api/reward/collect', response_model=ApiResponse)
@exclusive_device_operation('api:reward-collect')
async def reward_collect() -> ApiResponse:
    """收取任务奖励。"""
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from autowsgr.ops import collect_rewards

    try:
        collected = await asyncio.to_thread(collect_rewards, ctx)
        return ApiResponse(success=True, data={'collected': collected}, message='奖励收取完成')
    except Exception as e:
        _log.opt(exception=True).warning('[API] 收取奖励失败: {}', e)
        return ApiResponse(success=False, error=str(e))


# ── 食堂烹饪 ──


class CookRequest(BaseModel):
    """烹饪请求。"""

    position: int = 1
    force_cook: bool = False


@router.post('/api/cook', response_model=ApiResponse)
@exclusive_device_operation('api:cook')
async def cook_action(request: CookRequest) -> ApiResponse:
    """食堂烹饪。"""
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from autowsgr.ops import cook

    try:
        result = await asyncio.to_thread(
            cook, ctx, position=request.position, force_cook=request.force_cook
        )
        return ApiResponse(success=True, data={'cooked': result}, message='烹饪完成')
    except Exception as e:
        _log.opt(exception=True).warning('[API] 烹饪失败: {}', e)
        return ApiResponse(success=False, error=str(e))


# ── 浴室修理 ──


@router.post('/api/repair/bath', response_model=ApiResponse)
@exclusive_device_operation('api:repair-bath')
async def repair_bath() -> ApiResponse:
    """浴室修理。"""
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from autowsgr.ops import repair_in_bath

    try:
        await asyncio.to_thread(repair_in_bath, ctx)
        return ApiResponse(success=True, message='浴室修理完成')
    except Exception as e:
        _log.opt(exception=True).warning('[API] 浴室修理失败: {}', e)
        return ApiResponse(success=False, error=str(e))


class RepairShipRequest(BaseModel):
    """按舰船名泡澡修理请求。"""

    ship_name: str


@router.post('/api/repair/ship', response_model=ApiResponse)
@exclusive_device_operation('api:repair-ship')
async def repair_ship(request: RepairShipRequest) -> ApiResponse:
    """使用浴室修理指定名称的舰船。

    前端泡澡修理系统调用此端点，将指定舰船送入浴室修理。
    后端会导航到浴室页面，打开选择修理 overlay，查找并点击指定舰船。
    """
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from autowsgr.ops.repair import repair_ship_by_name

    try:
        repair_secs = await asyncio.to_thread(repair_ship_by_name, ctx, request.ship_name)
        if repair_secs < 0:
            return ApiResponse(
                success=False,
                error=f'浴场已满，无法修理 {request.ship_name}',
            )
        return ApiResponse(
            success=True,
            data={'ship_name': request.ship_name, 'repair_seconds': repair_secs},
            message=f'{request.ship_name} 已送入泡澡修理 ({repair_secs}s)',
        )
    except Exception as e:
        _log.opt(exception=True).warning('[API] 泡澡修理失败: {}', e)
        return ApiResponse(success=False, error=str(e))


# ── 解装 / 解体 ──


class DestroyRequest(BaseModel):
    """解装请求。"""

    ship_types: list[str] | None = None
    remove_equipment: bool = True


@router.post('/api/destroy', response_model=ApiResponse)
@exclusive_device_operation('api:destroy')
async def destroy_action(request: DestroyRequest) -> ApiResponse:
    """解装/解体舰船。"""
    try:
        ctx = get_context()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    from autowsgr.ops import destroy_ships
    from autowsgr.types import ShipType

    ship_types = None
    if request.ship_types:
        ship_types = [ShipType(t) for t in request.ship_types]

    try:
        await asyncio.to_thread(
            destroy_ships,
            ctx,
            ship_types=ship_types,
            remove_equipment=request.remove_equipment,
        )
        return ApiResponse(success=True, message='解装完成')
    except Exception as e:
        _log.opt(exception=True).warning('[API] 解装失败: {}', e)
        return ApiResponse(success=False, error=str(e))
