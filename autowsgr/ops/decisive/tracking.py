"""决战小关会话：跨单场战斗保存融合历史，并控制地图字母采样。"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from autowsgr.combat.node_fusion.integration import TrackingSession
from autowsgr.combat.node_fusion.model import FusionObservation, FusionProfile, FusionTracker
from autowsgr.combat.plan import CombatMode
from autowsgr.infra.logger import get_logger
from autowsgr.ops.decisive.config import MapData


if TYPE_CHECKING:
    from pathlib import Path

    from autowsgr.combat.node_fusion.model import NodeEstimate
    from autowsgr.emulator.frame import CapturedFrame


_log = get_logger('ops.decisive')


@dataclass(frozen=True, slots=True)
class NodeSamplingPolicy:
    """地图字母采样的滞回阈值；模型权重不代表校准后的正确率。"""

    stop_threshold: float = 0.95
    resume_threshold: float = 0.80

    def __post_init__(self) -> None:
        if not 0 < self.resume_threshold < self.stop_threshold < 1:
            raise ValueError('Sampling thresholds must satisfy 0 < resume < stop < 1')


class DecisiveTrackingSession(TrackingSession):
    """由决战控制器拥有，一次小关内的引擎只借用此会话。"""

    def __init__(
        self,
        chapter: int,
        stage: int,
        *,
        known_start: bool = False,
        log_dir: str | Path | None = None,
        record_replay: bool = False,
        sampling: NodeSamplingPolicy | None = None,
    ) -> None:
        super().__init__()
        self.chapter = chapter
        self.stage = stage
        self.combat_mode = CombatMode.DECISIVE
        self.sampling = sampling or NodeSamplingPolicy()
        self.sample_node_label = not known_start
        self._sampling_requested = False
        self._encounter_index = 0
        self.encounter_id = f'{self._sortie_id}:0'
        self._map_label = f'决战 {chapter}-{stage}'
        metadata = MapData.tracking_map(chapter, stage)
        profile = FusionProfile(min_travel_seconds=None)
        self.tracker = FusionTracker(
            metadata,
            profile,
            dynamics='decisive',
            initial={'A': 1.0} if known_start else None,
        )
        self._history_tracker = self.tracker
        self._last_result = self.tracker.estimate
        self._decision_estimate = self._last_result
        if record_replay:
            self._open_log(log_dir)
        self._record_start(
            metadata,
            profile,
            map_id=(chapter, stage),
            plan_name=self._map_label,
            sampling=asdict(self.sampling),
        )
        _log.info(
            '[决战定位] {} 初始化={}，字母停采阈值={}，恢复阈值={}（未校准模型权重）',
            self._map_label,
            self.tracker.initial,
            self.sampling.stop_threshold,
            self.sampling.resume_threshold,
        )

    def publish(self, observation: FusionObservation) -> NodeEstimate | None:
        estimate = super().publish(observation)
        if estimate is None or estimate.anomaly:
            self._decision_estimate = None
            self.sample_node_label = True
            return estimate
        if estimate.ignored is not None:
            return estimate
        self._decision_estimate = estimate
        confidence = max(estimate.node_weights.values(), default=0.0)
        was_sampling = self.sample_node_label
        if confidence < self.sampling.resume_threshold:
            self.sample_node_label = True
        elif (
            confidence >= self.sampling.stop_threshold
            and self.current_node != '0'
            and not self._sampling_requested
        ):
            self.sample_node_label = False
        if was_sampling != self.sample_node_label:
            _log.info(
                '[决战定位] 地图字母采样{}，最大节点权重={:.4f}',
                '恢复' if self.sample_node_label else '停用',
                confidence,
            )
        return estimate

    def request_node_sample(self, reason: str) -> None:
        """页面冲突等独立事件可恢复主动采样，保留已有候选及原始历史。"""
        self.sample_node_label = True
        self._sampling_requested = True
        _log.info('[决战定位] 恢复地图字母采样: {}', reason)

    def map_ready(self, frame: CapturedFrame, node_label: str | None = None) -> None:
        """地图准备页确认当前遭遇；可附加同一帧中的 native 字母观察。"""
        if self.tracker is not None and node_label not in self.tracker.map_data.nodes:
            node_label = None
        requested = self._sampling_requested
        if node_label is not None:
            self._sampling_requested = False
        estimate = self.publish(
            FusionObservation(
                kind='phase',
                timestamp=frame.captured_at,
                frame_id=frame.sequence,
                phase='DECISIVE_MAP_READY',
                node_label=node_label,
                encounter_id=self.encounter_id,
                decision_node=self.current_node,
            )
        )
        if requested and (estimate is None or estimate.anomaly or estimate.ignored):
            self._sampling_requested = True
            self.sample_node_label = True

    def completed_encounter(self, encounter_id: str) -> FusionObservation | None:
        """读取模型确认的完成事件；停用后的原会话历史仍可归档或去重。"""
        if self._history_tracker is None:
            return None
        return self._history_tracker.completed_encounter(encounter_id)

    def complete_encounter(self, encounter_id: str) -> bool:
        """只由已成功结束的单场战斗触发，同一标识重复提交不推进。"""
        if self.completed_encounter(encounter_id) is not None:
            return False
        if encounter_id != self.encounter_id:
            raise ValueError('Completed encounter does not belong to the current battle')
        estimate = self.publish(
            FusionObservation(
                kind='action',
                timestamp=time.monotonic(),
                action='encounter_complete',
                clicked=True,
                encounter_id=encounter_id,
                decision_node=self.current_node,
            )
        )
        if estimate is None or estimate.anomaly or estimate.ignored:
            raise RuntimeError('Cannot explain the completed decisive encounter')
        self._encounter_index += 1
        self.encounter_id = f'{self._sortie_id}:{self._encounter_index}'
        return True

    def stage_clear(self, frame: CapturedFrame) -> bool:
        """仅接收实际通关画面，结束小关后汇总用户识别反馈。"""
        estimate = self.publish(
            FusionObservation(
                kind='phase',
                timestamp=frame.captured_at,
                frame_id=frame.sequence,
                phase='DECISIVE_STAGE_CLEAR',
                encounter_id=self.encounter_id,
                decision_node=self.current_node,
            )
        )
        if estimate is None or estimate.anomaly:
            raise RuntimeError('Cannot apply the confirmed decisive stage clear')
        if estimate.ignored:
            return False
        self.finish()
        return True
