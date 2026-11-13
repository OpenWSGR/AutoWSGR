"""固定版本、非交互决战采集：python -m tools.decisive.collect --help。"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from autowsgr.combat.engine import CombatEngine
from autowsgr.combat.node_fusion.enemy import observe_enemy
from autowsgr.combat.state import CombatPhase
from autowsgr.emulator.frame import CapturedFrame
from autowsgr.image_resources import Templates
from autowsgr.ops.decisive.config import MapData
from autowsgr.ops.decisive.controller import DecisiveController, DecisiveResult
from autowsgr.scheduler import launch
from autowsgr.types import ConditionFlag, DecisiveEntryStatus, DecisivePhase
from autowsgr.ui.battle.preparation import BattlePreparationPage
from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage
from autowsgr.vision import ImageChecker, get_api_dll

from tools.decisive.recording import FileStopEvent, RecordingDevice, SampleArchive, TimedProxy


if TYPE_CHECKING:
    from autowsgr.combat.history import CombatResult
    from autowsgr.combat.node_fusion.enemy import EnemyObservation
    from autowsgr.combat.plan import CombatPlan
    from autowsgr.context import GameContext
    from autowsgr.infra import DecisiveConfig


class RecordingCombatEngine(CombatEngine):
    """复用实战索敌结果；采集不会额外识别一次敌舰。"""

    def __init__(self, ctx: GameContext, archive: SampleArchive) -> None:
        super().__init__(ctx)
        self.archive = archive
        self.saw_enemy = False

    def _collect_spot_evidence(self) -> tuple[dict[str, int], str, EnemyObservation]:
        frame = self._recognizer.last_match
        if not isinstance(frame, CapturedFrame):
            frame = self._recognizer.capture_frame()
        timings: dict[str, float] = {}
        dll = TimedProxy(get_api_dll(), 'recognize_enemy', timings, 'enemy_native_seconds')
        ocr = (
            TimedProxy(self._ocr, 'recognize_single', timings, 'formation_ocr_seconds')
            if self._ocr is not None
            else None
        )
        started = time.perf_counter()
        evidence = observe_enemy(frame.image, ocr, mode='fight', dll=dll)
        timings['enemy_total_seconds'] = time.perf_counter() - started
        # 复用刚取得的原始结果；会话及当前战术必须在索敌决策之前更新。
        self._tracking_phase(CombatPhase.SPOT_ENEMY_SUCCESS, frame=frame, enemies=evidence)
        self.archive.record(
            'enemy',
            frame,
            observation=asdict(evidence),
            timings=timings,
            predicted_node=self._node,
            encounter_id=self._tracking.encounter_id if self._tracking is not None else None,
            fusion_event_id=(
                self._tracking.estimate.event_id
                if self._tracking is not None and self._tracking.estimate is not None
                else None
            ),
        )
        self.saw_enemy = True
        formation = {1: '单纵阵', 2: '复纵阵', 3: '轮型阵', 4: '梯形阵', 5: '单横阵'}
        return evidence.counts, formation.get(evidence.formation, evidence.formation_text), evidence

    def _make_decision(self, phase: CombatPhase) -> ConditionFlag:
        if phase in (CombatPhase.RESULT, CombatPhase.FORMATION, CombatPhase.NIGHT_PROMPT):
            self.archive.record(
                phase.name.lower(),
                self._recognizer.last_match,
                predicted_node=self._node,
                encounter_id=self._tracking.encounter_id if self._tracking is not None else None,
            )
        if phase == CombatPhase.FORMATION and not self.saw_enemy:
            self.archive.record('enemy_missing', reason='formation_without_spot_observation')
        return super()._make_decision(phase)


class CollectionController(DecisiveController):
    """观察层覆盖，业务决策仍由决战控制器提供。"""

    def __init__(self, ctx: GameContext, config: DecisiveConfig, archive: SampleArchive) -> None:
        super().__init__(ctx, config)
        self.archive = archive
        self.round_number = 1
        self.label_source: str | None = None
        self._label_node: str | None = None
        self._label_stage: int | None = None
        self._label_round: int | None = None
        self._labelled_completions: set[str] = set()
        self._sampled_encounters: set[str] = set()
        self._sampled_frames: set[tuple[str, int | float]] = set()
        self._allow_reset = False
        self._first_entry: tuple[int, str | None] | None = None

    def _set_label(self, node: str | None, stage: int, source: str | None) -> None:
        self._label_node = node
        self._label_stage = stage
        self._label_round = self.round_number
        self.label_source = source if node else None

    def _update_archive_context(self) -> None:
        label_applies = (
            self._label_stage == self._state.stage and self._label_round == self.round_number
        )
        self.archive.context.update(
            round=self.round_number,
            chapter=self._state.chapter,
            stage=self._state.stage,
            predicted_node=self._tracking.current_node
            if self._tracking is not None
            else self._state.node,
            phase=self._state.phase.name,
            label_node=self._label_node if label_applies else None,
            label_source=self.label_source if label_applies else None,
            encounter_id=self._tracking.encounter_id if self._tracking is not None else None,
            fusion_log=(
                str(self._tracking.log_path)
                if self._tracking is not None and self._tracking.log_path is not None
                else None
            ),
        )

    def _record(self, kind: str, *, snapshot: bool = True, **fields: object) -> None:
        self._update_archive_context()
        frame = self._ctrl.capture_frame() if snapshot else None
        self.archive.record(kind, frame, **fields)

    def run_current_map(self, stage: int, node: str | None) -> DecisiveResult:
        """首轮继续已有进度；位于主页时导航进入，绝不额外重置。"""
        if self._ctx.stop_event.is_set():
            return DecisiveResult.STOPPED
        self._close_tracking()
        self._known_start_stage = None
        self._state.stage = stage
        self._state.node = node or 'U'
        self._set_label(None, stage, None)
        self._inventory_refresh_required = True
        self._has_chosen_fleet = True
        self._state.phase = DecisivePhase.WAITING_FOR_MAP
        self._record('start_current_map', requested_stage=stage, requested_node=node)
        screen = self._ctrl.screenshot()
        phase = self._map.detect_decisive_phase(screen)
        if phase is None and BattlePreparationPage.is_current_page(screen):
            self._record('resume_preparation_before')
            if self._ctx.stop_event.is_set():
                raise InterruptedError('返回决战地图前收到停止请求')
            if not BattlePreparationPage.is_current_page(self._ctrl.screenshot()):
                raise RuntimeError('恢复前准备页已发生变化，保留现场停止')
            # 编队异常留下的准备页属于当前小关；沿已有回退路径恢复，不进入总览或重置。
            page = DecisiveBattlePreparationPage(self._ctx, self._config, self._ocr)
            page.go_back()
            if self._ctx.stop_event.is_set():
                raise InterruptedError('返回决战地图后收到停止请求')
            screen = self._ctrl.screenshot()
            phase = self._map.detect_decisive_phase(screen)
            if phase not in (
                DecisivePhase.PREPARE_COMBAT,
                DecisivePhase.CHOOSE_FLEET,
                DecisivePhase.ADVANCE_CHOICE,
            ):
                self._record('resume_preparation_failed')
                raise RuntimeError('准备页回退后未确认当前决战地图，保留现场停止')
            self._record('resume_preparation_after', restored_phase=phase.name)
        if phase is None:
            self._first_entry = (stage, node)
            self._prepare_entry_state()
            self._state.phase = DecisivePhase.ENTER_MAP
            self._record('start_entry_navigation')
        else:
            self._set_label(node, stage, 'user_confirmed_start')
            self._known_start_stage = stage if node == 'A' else None
        self._wait_deadline = time.monotonic() + 15
        return self._main_loop()

    def run(self) -> DecisiveResult:
        """上一轮确实通关后允许正常重置；旧轮标签不沿用到新章节。"""
        self._allow_reset = True
        self._set_label(None, 1, None)
        return super().run()

    def run_stage_clear(self, stage: int) -> DecisiveResult:
        """恢复已确认通关后的奖励结算；不重新执行终点战斗或章节重置。"""
        if self._ctx.stop_event.is_set():
            return DecisiveResult.STOPPED
        self._close_tracking()
        self._known_start_stage = None
        self._first_entry = None
        self._state.stage = stage
        self._state.node = MapData.get_stage_end_node(self._state.chapter, stage)
        self._state.phase = DecisivePhase.STAGE_CLEAR
        self._set_label(self._state.node, stage, 'caller_confirmed_stage_clear')
        self._record('resume_stage_clear', requested_stage=stage)
        self._handle_stage_clear(resume_rewards=True)
        return self._main_loop()

    def _main_loop(self) -> DecisiveResult:
        try:
            return super()._main_loop()
        except Exception:
            self._set_label(None, self._state.stage, None)
            self._record('exception', error=traceback.format_exc())
            raise
        finally:
            self._close_tracking()

    def _handle_enter_map(self) -> None:
        self._record('entry_before')
        entry = self._battle_page.detect_entry_status()
        if entry == DecisiveEntryStatus.REFRESH and not self._allow_reset:
            self._record('initial_entry_requires_reset', entry_status=entry.value)
            raise RuntimeError('首轮入口要求重置，停止并保留现场；不自动清空进度')
        first_entry = self._first_entry
        if first_entry is not None:
            expected_stage, node = first_entry
            actual_stage = self._detect_entry_stage()
            self._record(
                'initial_entry_stage',
                expected_stage=expected_stage,
                actual_stage=actual_stage,
                entry_status=entry.value,
            )
            if actual_stage != expected_stage:
                raise RuntimeError(
                    f'实际小关 {actual_stage} 与请求小关 {expected_stage} 不同，停止复核标签'
                )
            self._known_start_stage = expected_stage if node == 'A' else None
        super()._handle_enter_map()
        if self._state.phase == DecisivePhase.WAITING_FOR_MAP:
            if first_entry is None and self._known_start_stage == 1 and self._state.stage == 1:
                self._set_label('A', 1, 'confirmed_chapter_reset')
            elif first_entry is not None:
                expected_stage, node = first_entry
                if self._state.stage != expected_stage:
                    raise RuntimeError('进入地图时小关发生变化，停止复核标签')
                self._set_label(node, expected_stage, 'user_confirmed_start_and_entry_stage')
                self._first_entry = None
        self._record('entry_after', entry_status=entry.value)

    def _sample_map(
        self, frame: CapturedFrame, encounter_id: str, *, used_for_tracking: bool
    ) -> str | None:
        frame_key = (
            encounter_id,
            frame.sequence if frame.sequence is not None else frame.captured_at,
        )
        if frame_key in self._sampled_frames or (
            encounter_id in self._sampled_encounters and not used_for_tracking
        ):
            return None
        if not self._map.is_map_page(frame.image) or self._map.detect_overlay(frame.image):
            return None
        observation = self._map.observe_node(frame)
        if observation.failure == 'missing_icon':
            self.archive.record(
                'map_missing_icon', frame, locate_seconds=observation.locate_seconds
            )
            return None
        self.archive.record(
            'map_error' if observation.failure == 'native_error' else 'map',
            observation.frame,
            crop=observation.crop,
            raw_node=observation.raw_node,
            used_for_tracking=used_for_tracking,
            icon_x=observation.icon_x,
            crop_bounds=observation.crop_bounds,
            failure=observation.failure,
            error=observation.error,
            timings={
                'locate_seconds': observation.locate_seconds,
                'map_native_seconds': observation.native_seconds,
            },
        )
        if observation.failure == 'native_error':
            raise RuntimeError(f'地图字母识别失败，已归档现场: {observation.error}')
        self._sampled_encounters.add(encounter_id)
        self._sampled_frames.add(frame_key)
        return observation.node_label

    def _observe_map_ready(self, frame: CapturedFrame) -> None:
        """采集强制保留字母观测，同一帧只定位、裁剪和调用 native 一次。"""
        session = self._ensure_tracking()
        self._sync_completed_label()
        self._update_archive_context()
        used_for_tracking = session.sample_node_label
        node = self._sample_map(frame, session.encounter_id, used_for_tracking=used_for_tracking)
        session.map_ready(frame, node if used_for_tracking else None)
        self._state.node = session.current_node if session.current_node != '0' else 'U'
        self._record(
            'map_fusion',
            snapshot=False,
            frame_sequence=frame.sequence,
            used_for_tracking=used_for_tracking,
        )

    def _handle_prepare_combat(self) -> None:
        self._record('prepare_before', snapshot=False)
        # 舰队恢复扫描由生产流程负责，包括已确认 A 的暂离恢复；采集不重复扫描。
        super()._handle_prepare_combat()

    def _run_combat(self, plan: CombatPlan) -> CombatResult:
        self._record('combat_start', snapshot=False)
        engine = RecordingCombatEngine(self._ctx, self.archive)
        result = engine.fight(
            plan,
            initial_ship_stats=self._state.ship_stats[:],
            tracking_session=self._tracking,
        )
        self._record(
            'combat_end',
            result=result.flag.value,
            saw_enemy=engine.saw_enemy,
            node_count=result.node_count,
            history=[
                {**asdict(event), 'event_type': event.event_type.name}
                for event in result.history.events
            ],
        )
        return result

    def _handle_node_result(self) -> None:
        self._record('node_result_before')
        try:
            super()._handle_node_result()
        finally:
            # 后续页面等待可能停止或超时；生产已提交的完成事件仍是事实。
            self._sync_completed_label()
        if self._state.phase == DecisivePhase.STAGE_CLEAR:
            self._set_label(
                MapData.get_stage_end_node(self._state.chapter, self._state.stage),
                self._state.stage,
                'confirmed_stage_clear_page',
            )
        self._record('node_result_after')

    def _sync_completed_label(self) -> None:
        """从确认提交的遭遇独立计步；模型修订 state.node 不会改写真值标签。"""
        encounter_id = self._battle_encounter_id
        if (
            self._tracking is None
            or encounter_id is None
            or encounter_id in self._labelled_completions
        ):
            return
        event = self._tracking.completed_encounter(encounter_id)
        if event is None:
            if encounter_id != self._tracking.encounter_id:
                raise RuntimeError('已完成遭遇缺少生产会话的完成事件，停止采集')
            return
        self._record(
            'encounter_complete',
            snapshot=False,
            encounter_id=encounter_id,
            observation=asdict(event),
        )
        self._labelled_completions.add(encounter_id)
        if self._label_node is None or self._label_stage != self._state.stage:
            return
        end = MapData.get_stage_end_node(self._state.chapter, self._state.stage)
        if self._label_node < end:
            self._set_label(
                chr(ord(self._label_node) + 1),
                self._state.stage,
                'confirmed_start_and_completed_battles',
            )
        else:
            self._set_label(None, self._state.stage, None)

    def _handle_stage_clear(self, *, resume_rewards: bool = False) -> None:
        self._record('stage_clear_before')
        self.archive.capture_phase = 'stage_clear_page'
        try:
            deadline = time.monotonic() + 8
            while not resume_rewards and (
                ImageChecker.find_any(
                    self._ctrl.screenshot(), Templates.Confirm.all(), confidence=0.8
                )
                is None
            ):
                if self._ctx.stop_event.is_set():
                    raise InterruptedError('决战通关确认前收到停止请求')
                if time.monotonic() >= deadline:
                    raise RuntimeError('预测终点但没有通关确认控件；保留现场并停止')
                time.sleep(0.2)
            super()._handle_stage_clear(resume_rewards=resume_rewards)
            if (
                ImageChecker.find_any(
                    self._ctrl.screenshot(),
                    Templates.Decisive.entry_status_templates(),
                    confidence=0.8,
                )
                is None
            ):
                raise RuntimeError('通关操作后未确认决战入口；不记作小关完成')
            self._set_label('A', self._state.stage + 1, 'confirmed_stage_clear')
            self._record(
                'stage_clear_after', completion_confirmed=True, cleared_stage=self._state.stage
            )
        finally:
            self.archive.capture_phase = None

    def _execute_retreat(self) -> None:
        raise RuntimeError('采集期间决策要求撤退，停止以保留进度和现场')

    def _handle_dock_full(self) -> None:
        self._record('dock_full')
        raise RuntimeError('采集期间船坞已满，停止；本场不计步')


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('D:/Games/autowsgr/user_settings.yaml'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=3, help='本次尚需完成的章数')
    parser.add_argument('--round-offset', type=int, default=0, help='之前已经完成的章数')
    parser.add_argument('--start-stage', type=int, choices=(1, 2, 3), default=1)
    entry_mode = parser.add_mutually_exclusive_group()
    entry_mode.add_argument('--start-node', help='人工确认的当前点，例如 A；省略代表未知恢复')
    entry_mode.add_argument(
        '--start-at-entry',
        action='store_true',
        help='已完成至少一章后，从入口正常重置下一章开始剩余采集',
    )
    entry_mode.add_argument(
        '--resume-stage-clear',
        action='store_true',
        help='当前小关战斗已完成，仅恢复尚未完成的奖励结算，不重打终点或重置',
    )
    args = parser.parse_args(argv)
    if args.rounds < 1 or args.round_offset < 0:
        parser.error('rounds 必须为正数，round-offset 不能为负数')
    if args.start_node and (len(args.start_node) != 1 or not 'A' <= args.start_node <= 'J'):
        parser.error('start-node 必须是单个有效节点字母')
    if args.start_at_entry and args.round_offset <= 0:
        parser.error('start-at-entry 仅用于已完成至少一章的续采，round-offset 必须大于 0')
    if args.start_at_entry and (args.start_node is not None or args.start_stage != 1):
        parser.error('start-at-entry 从重置后的第一小关开始，不能指定地图恢复节点或其它小关')
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    archive = SampleArchive(args.output.resolve())
    stop = FileStopEvent(archive.output / 'STOP')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()  # noqa: S607
    archive.write_json(
        'manifest.json',
        {
            'pid': os.getpid(),
            'code_commit': commit,
            'code_directory': str(Path.cwd()),
            'config_path': str(args.config.resolve()),
            'native_version': archive.native_version,
            'stop_file': str(stop.path),
            'arguments': {
                key: str(value) if isinstance(value, Path) else value
                for key, value in vars(args).items()
            },
        },
    )
    ctx = None
    completed = 0
    try:
        # 当前已在地图；启动器仅连接设备/构建 OCR，不导航主页面。
        ctx = launch(args.config, ensure_game=False)
        ctx.stop_event = stop
        ctx.ctrl = RecordingDevice(ctx.ctrl, archive, stop)
        ctx.config = ctx.config.model_copy(
            update={
                'log': ctx.config.log.model_copy(
                    update={'node_fusion_replay': True, 'dir': str(archive.output)}
                )
            }
        )
        archive.write_json('effective_log_config.json', ctx.config.log.model_dump(mode='json'))
        base = ctx.config.decisive_battle
        if base is None or base.chapter != 6:
            raise ValueError('采集要求配置 decisive_battle.chapter=6')
        config = base.model_copy(update={'useful_skill': False, 'useful_skill_strict': False})
        archive.write_json('effective_config.json', config.model_dump(mode='json'))
        controller = CollectionController(ctx, config, archive)
        for index in range(args.rounds):
            controller.round_number = args.round_offset + index + 1
            if index > 0 or args.start_at_entry:
                result = controller.run()
            elif args.resume_stage_clear:
                result = controller.run_stage_clear(args.start_stage)
            else:
                result = controller.run_current_map(args.start_stage, args.start_node)
            if result != DecisiveResult.CHAPTER_CLEAR:
                archive.record('stopped' if stop.is_set() else 'incomplete', result=result.value)
                return 2
            completed += 1
            archive.record('round_complete', completed_rounds=completed)
    except Exception:
        archive.record(
            'stopped' if stop.is_set() else 'exception',
            ctx.ctrl.capture_frame() if ctx else None,
            error=traceback.format_exc(),
        )
        return 2
    else:
        return 0
    finally:
        archive.write_json(
            'summary.json',
            {
                'completed_rounds': completed,
                'requested_rounds': args.rounds,
                'stopped': stop.is_set(),
                'pid': os.getpid(),
            },
        )
        if ctx is not None:
            ctx.ctrl.disconnect()


if __name__ == '__main__':
    raise SystemExit(main())
