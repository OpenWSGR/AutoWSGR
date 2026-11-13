"""出征级节点追踪会话：采集适配、融合推断、决策确认及标量日志。

引擎只转发观测和操作，并读取已确认的当前位置。截图、点击和 OCR 底层
不感知融合状态、记录策略或地图语义。
"""

from __future__ import annotations

import gzip
import json
import math
import time
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from autowsgr_native.vessel_type import VesselType

from autowsgr import __version__
from autowsgr.combat.node_fusion.calibration import (
    NATIVE_VERSION,
    SlotMismatch,
    recognition_mismatches,
)
from autowsgr.combat.node_fusion.enemy import EnemyObservation, observe_enemy
from autowsgr.combat.node_fusion.map import TrackingMap
from autowsgr.combat.node_fusion.model import (
    MODEL_VERSION,
    FusionObservation,
    FusionProfile,
    FusionTracker,
)
from autowsgr.combat.node_fusion.position import ShipPositionDetector
from autowsgr.combat.plan import CombatMode
from autowsgr.combat.state import CombatPhase
from autowsgr.emulator.frame import CapturedFrame
from autowsgr.infra.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.combat.node_fusion.model import NodeEstimate
    from autowsgr.combat.plan import CombatPlan
    from autowsgr.emulator import AndroidController
    from autowsgr.vision import OCREngine


_log = get_logger('combat')
_CAPABILITY_NAMES = {
    'distance': '船位距离',
    'ray': '运动射线',
    'topology': '地图路由约束',
    'node_types': '节点类型',
    'encounter_history': '按遭遇推进的历史推断',
    'enemy': '敌方阵容与阵型',
    'detour': '迂回属性',
}
_ENCOUNTER_PHASES = frozenset(
    {
        CombatPhase.SPOT_ENEMY_SUCCESS,
        CombatPhase.FORMATION,
        CombatPhase.MISSILE_ANIMATION,
        CombatPhase.FIGHT_PERIOD,
        CombatPhase.NIGHT_PROMPT,
        CombatPhase.RESULT,
        CombatPhase.EXP_SETTLEMENT,
        CombatPhase.GET_SHIP,
        CombatPhase.PROCEED,
        CombatPhase.GARRISON,
        CombatPhase.FLAGSHIP_SEVERE_DAMAGE,
    }
)


def _channel_summary(weights: dict[str, float]) -> str:
    """单路独立分布：首名压过次名的自然对数分差；无次名标注唯一。"""
    ranked = sorted(
        ((node, weight) for node, weight in weights.items() if weight > 0.0),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked:
        return '-'
    if len(ranked) == 1:
        return f'{ranked[0][0]}(唯一)'
    top, second = ranked[0], ranked[1]
    gap = math.log(top[1]) - math.log(second[1])
    return f'{top[0]}>{second[0]}+{gap:.1f}'


class _TimedClickDevice:
    """仅在本模块代理实际点击，记录发送时间，不改共享点击接口。"""

    def __init__(self, device: AndroidController) -> None:
        self._device = device
        self.clicked_at: float | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._device, name)

    def click(self, *args: Any, **kwargs: Any) -> Any:
        if self.clicked_at is None:
            self.clicked_at = time.monotonic()
        return self._device.click(*args, **kwargs)


class TrackingSession:
    """每次出征唯一的节点来源，导航目的点不作为已到达节点使用。"""

    def __init__(self) -> None:
        self.tracker: FusionTracker | None = None
        self.detector = ShipPositionDetector()
        self.log_path: Path | None = None
        self._last_result: NodeEstimate | None = None
        self._decision_estimate: NodeEstimate | None = None
        self.phase_is_new_encounter = False
        self._last_motion = float('-inf')
        self._sortie_id = uuid4().hex
        self._map_label = '?'
        self._motion_frames = 0
        self._history_tracker: FusionTracker | None = None
        self._statistics_finished = False
        self.combat_mode = CombatMode.NORMAL
        self.encounter_id: str | None = None

    @property
    def estimate(self) -> NodeEstimate | None:
        """最后一次发布的结果，包含未被模型接纳的观察及其拒绝原因。"""
        return self._last_result

    @property
    def current_node(self) -> str:
        """由场景确认的决策节点，不将最新模型结果自动作为已发布决策。"""
        if self._decision_estimate is None:
            return '0'
        return self._decision_estimate.current_node or '0'

    @classmethod
    def start(
        cls,
        plan: CombatPlan,
        log_dir: str | Path | None,
        *,
        record_replay: bool = False,
    ) -> TrackingSession | None:
        if plan.mode not in (CombatMode.NORMAL, CombatMode.EVENT):
            return None
        session = cls()
        session.combat_mode = plan.mode
        if record_replay:
            session._open_log(log_dir)
        session._map_label = (
            f'{plan.event_name} {plan.chapter}-{plan.map_id}'
            if plan.event_name
            else f'{plan.chapter}-{plan.map_id}'
        )
        try:
            if plan.mode == CombatMode.NORMAL:
                metadata = TrackingMap.load(plan.chapter, plan.map_id)
            else:
                metadata = (
                    TrackingMap.load_event(
                        plan.event_name, plan.chapter, plan.map_id, plan.entrance
                    )
                    if plan.event_name
                    else None
                )
            if metadata is None:
                raise ValueError('没有可用的地图坐标，当前位置无法确认')
            # 普通地图的一秒下限已有验证，活动移动机制未确认时不套用该限制。
            profile = FusionProfile(
                min_travel_seconds=1.0 if plan.mode == CombatMode.NORMAL else None
            )
            session.tracker = FusionTracker(metadata, profile)
            session._history_tracker = session.tracker
        except Exception as exc:
            session.fail(f'初始化失败: {type(exc).__name__}: {exc}')
            return session
        session._record_start(
            metadata,
            profile,
            map_id=(plan.chapter, plan.map_id),
            plan_name=plan.name,
            event_name=plan.event_name,
            entrance=plan.entrance,
        )
        session._warn_degradation(metadata)
        if session.log_path is not None:
            _log.info('[NodeFusion] 回放记录: {}', session.log_path)
        return session

    def _record_start(
        self,
        metadata: TrackingMap,
        profile: FusionProfile,
        *,
        map_id: tuple[int | str, int | str],
        plan_name: str,
        event_name: str | None = None,
        entrance: str | None = None,
        sampling: dict[str, Any] | None = None,
    ) -> None:
        """冻结模型、初始化与地图；未开启回放时不序列化副本。"""
        if self.log_path is None or self.tracker is None:
            return
        self._record(
            {
                'kind': 'start',
                'schema_version': 4,
                'model_version': MODEL_VERSION,
                'backend_version': __version__,
                'mode': 'fusion',
                'combat_mode': self.combat_mode,
                'dynamics': self.tracker.dynamics,
                'initial': self.tracker.initial,
                'sampling': sampling or {},
                'map': list(map_id),
                'plan': plan_name,
                'event_name': event_name,
                'entrance': entrance,
                'metadata_sha256': metadata.fingerprint,
                'metadata_source': metadata.source,
                'metadata_snapshot': metadata.to_dict(),
                'capabilities': metadata.capabilities,
                'degradation_reasons': metadata.degradation_reasons,
                'native_version': version('autowsgr-native'),
                'native_ship_types': {
                    name: value.as_chinese()
                    for name in dir(VesselType)
                    if isinstance(value := getattr(VesselType, name), VesselType)
                },
            }
        )
        self._record({'kind': 'profile', 'profile': asdict(profile)})

    @staticmethod
    def _warn_degradation(metadata: TrackingMap) -> None:
        """每次出征只警告一次，局部资料缺失另列原因，不误报整项全部停用。"""
        if not metadata.degradation_reasons:
            return
        enabled = [
            _CAPABILITY_NAMES[name] for name, value in metadata.capabilities.items() if value
        ]
        limited = [
            _CAPABILITY_NAMES[name] for name, value in metadata.capabilities.items() if not value
        ]
        _log.warning(
            '[NodeFusion] 地图信息不完整，已自动降级。来源={}；原因={}；启用能力={}；受限或停用={}',
            metadata.source or '内存地图',
            '；'.join(metadata.degradation_reasons),
            '、'.join(enabled) or '无',
            '、'.join(limited) or '无',
        )

    def _open_log(self, log_dir: str | Path | None) -> None:
        try:
            directory = Path(log_dir or 'logs') / 'node-fusion'
            directory.mkdir(parents=True, exist_ok=True)
            self.log_path = directory / f'{self._sortie_id}.jsonl.gz'
        except OSError as exc:
            _log.warning('[NodeFusion] 无法创建标量日志，节点推断继续: {}', exc)

    def _write(self, record: dict) -> None:
        if self.log_path is not None:
            # 标量日志行内键名与舰名重复度高，gzip 压缩比约 5-8 倍。
            with gzip.open(self.log_path, 'at', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')

    def _record(self, record: dict) -> None:
        try:
            self._write(record)
        except Exception as exc:
            # 文件系统故障只关闭日志，不能停用唯一节点追踪器。
            self.log_path = None
            _log.warning('[NodeFusion] 标量日志写入失败，节点推断继续: {}', exc)

    def fail(self, reason: str) -> None:
        self.tracker = None
        self._last_result = None
        self._decision_estimate = None
        self.phase_is_new_encounter = False
        _log.error('[NodeFusion] 节点无法确认: {}', reason)
        self._record({'kind': 'disabled', 'reason': reason})

    def finish(self) -> None:
        """出征结束后核对舰类识别；不符时告警请求反馈，全程一致保持静默。"""
        if self._statistics_finished or self._history_tracker is None:
            return
        self._statistics_finished = True
        try:
            mismatches = recognition_mismatches(self._history_tracker, combat_mode=self.combat_mode)
        except Exception as exc:
            _log.warning('[NodeFusion校验] 本趟校验未完成，不影响游戏: {}', exc)
            return
        by_node: dict[str, list[SlotMismatch]] = {}
        for item in mismatches:
            by_node.setdefault(item.node, []).append(item)
        for node, items in by_node.items():
            detail = '；'.join(
                f'槽{item.slot} {item.expected}→{item.code}({item.recognized}) '
                f'[事件{item.event_id}, 遭遇{item.encounter_id}]'
                for item in items
            )
            _log.warning(
                '[NodeFusion校验] 舰类识别与地图签名不符，请反馈：模式 {} 地图 {} 节点 {}：{}（native {}）',
                self.combat_mode,
                self._map_label,
                node,
                detail,
                NATIVE_VERSION,
            )
        if by_node and self.log_path is not None:
            _log.warning('[NodeFusion校验] 复核观测记录: {}', self.log_path)

    def publish(self, observation: FusionObservation) -> NodeEstimate | None:
        if self.tracker is None:
            return None
        try:
            self._last_result = self.tracker.observe(observation)
        except Exception as exc:
            self.fail(f'推断失败: {type(exc).__name__}: {exc}')
            return None
        if self.log_path is not None:
            summary = self.estimate.as_dict()
            # 关闭回放时不构造序列化副本；启用后只记录增量修订。
            summary.pop('history', None)
            if observation.kind != 'phase':
                states = summary.pop('state_weights', ())
                summary['state_count'] = len(states)
            self._record(
                {
                    'kind': 'observation',
                    'schema_version': 4,
                    'observation': asdict(observation),
                    'estimate': summary,
                }
            )
        if observation.kind == 'motion' and self.estimate.ignored is None:
            self._motion_frames += 1
        return self.estimate

    def motion(self, frame: CapturedFrame | None, decision_node: str) -> None:
        if self.tracker is None or not isinstance(frame, CapturedFrame):
            return
        if frame.captured_at - self._last_motion < 0.1:
            return
        self._last_motion = frame.captured_at
        try:
            position = self.detector.detect(frame.image)
        except Exception as exc:
            # 一次船位识别失败是证据缺失，阶段与敌情仍可继续定位。
            _log.warning('[NodeFusion] 本帧船位识别失败: {}', exc)
            position = None
        self.publish(
            FusionObservation(
                kind='motion',
                timestamp=frame.captured_at,
                frame_id=frame.sequence,
                position=position,
                decision_node=decision_node,
                detector_status=self.detector.detection_status,
            )
        )

    def _log_attribution(self, estimate: NodeEstimate) -> None:
        """到达帧输出各证据通道的独立候选集，便于定位某点位的弱判据。"""
        diagnostics = estimate.diagnostics

        def channel(name: str) -> str:
            row = diagnostics.get(name)
            weights = row.get('weights') if isinstance(row, dict) else None
            return _channel_summary(weights or {})

        ranked = sorted(estimate.node_weights.values(), reverse=True)
        margin = ranked[0] - ranked[1] if len(ranked) > 1 else 1.0
        frames = self._motion_frames
        self._motion_frames = 0
        _log.debug(
            '[NodeFusion归因] 节点={} 索敌前{}({}帧) 敌情{} margin={:.3f}',
            estimate.current_node or '?',
            channel('history_prior'),
            frames,
            channel('enemy'),
            margin,
        )

    def phase(
        self,
        phase: CombatPhase,
        frame: CapturedFrame | None,
        decision_node: str,
        enemies: EnemyObservation | None = None,
    ) -> None:
        self.phase_is_new_encounter = False
        known_frame = frame if isinstance(frame, CapturedFrame) else None
        estimate = self.publish(
            FusionObservation(
                kind='phase',
                timestamp=known_frame.captured_at if known_frame else time.monotonic(),
                frame_id=known_frame.sequence if known_frame else None,
                phase=phase.name,
                enemies=enemies,
                decision_node=decision_node,
                encounter_id=self.encounter_id,
            )
        )
        if phase not in _ENCOUNTER_PHASES:
            return
        if estimate is None or estimate.anomaly:
            self._decision_estimate = None
            self.phase_is_new_encounter = False
        elif estimate.ignored is None:
            self._decision_estimate = estimate
            row = next(
                (row for row in reversed(estimate.history) if row['event_id'] == estimate.event_id),
                None,
            )
            self.phase_is_new_encounter = row is not None and row['transition'] == 'new_encounter'
            if self.phase_is_new_encounter:
                self._log_attribution(estimate)

    def enemy_observation(
        self,
        frame: CapturedFrame | None,
        ocr: OCREngine | None,
        mode: str,
        decision_node: str,
        capture: Callable[[], CapturedFrame] | None = None,
    ) -> EnemyObservation | None:
        if self.tracker is None:
            return None
        if not isinstance(frame, CapturedFrame):
            frame = capture() if capture else None
        if not isinstance(frame, CapturedFrame):
            self.fail('索敌截图缺少采集来源')
            return None
        try:
            evidence = observe_enemy(frame.image, ocr, mode=mode)
        except Exception as exc:
            _log.warning('[NodeFusion] 本次敌情采集失败，继续使用阶段和历史: {}', exc)
            evidence = None
        self.phase(CombatPhase.SPOT_ENEMY_SUCCESS, frame, decision_node, evidence)
        return evidence

    def action(
        self,
        action: str,
        phase: CombatPhase,
        decision_node: str,
        *,
        clicked: bool | None = None,
        page_left: bool | None = None,
        timestamp: float | None = None,
    ) -> None:
        estimate = self.publish(
            FusionObservation(
                kind='action',
                timestamp=time.monotonic() if timestamp is None else timestamp,
                action=action,
                phase=phase.name,
                clicked=clicked,
                page_left=page_left,
                decision_node=decision_node,
                encounter_id=self.encounter_id,
            )
        )
        if (
            action in ('proceed', 'detour', 'retreat', 'end')
            and clicked is not False
            and estimate is not None
            and estimate.ignored is None
        ):
            self._decision_estimate = None
            self.phase_is_new_encounter = False
        if action == 'end':
            self.finish()

    @staticmethod
    def time_click(
        device: AndroidController, operation: Callable[[AndroidController], bool]
    ) -> tuple[bool, float]:
        proxy = _TimedClickDevice(device)
        clicked = operation(cast('AndroidController', proxy))
        return clicked, proxy.clicked_at if proxy.clicked_at is not None else time.monotonic()
