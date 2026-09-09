"""Long-running decisive stability test with controlled leave/retreat injections."""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    import argparse


DESC = '决战稳定性长跑: 每票暂离三次、撤退一次，并穿插远征收取'


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--tickets', type=int, default=10, help='决战票数 (默认 10)')
    parser.add_argument('--until', default='08:00', help='持续到本地时间 HH:MM (默认 08:00)')
    parser.add_argument(
        '--stop-after-tickets',
        action='store_true',
        help='完成请求票数后立即结束，不进入截止前定时远征等待',
    )
    parser.add_argument('--seed', type=int, default=None, help='随机插入顺序种子')
    parser.add_argument(
        '--expedition-interval',
        type=int,
        default=300,
        help='无决战票时远征检查间隔秒数 (默认 300)',
    )


def _parse_deadline(raw: str) -> datetime:
    hour, minute = (int(value) for value in raw.split(':', 1))
    now = datetime.now().astimezone()
    deadline = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if deadline <= now:
        deadline += timedelta(days=1)
    return deadline


def _restart_to_home(rt: Any) -> None:
    from autowsgr.ops import ensure_game_ready, restart_game

    app = rt.ctx.config.account.game_app
    package = app.package_name if hasattr(app, 'package_name') else app
    restart_game(rt.ctx.ctrl, package)
    ensure_game_ready(rt.ctx, app)


def _reset_after_restart(rt: Any, config: Any) -> None:
    """Reset the chapter before reusing the device after a ticket error."""
    from autowsgr.types import DecisiveEntryStatus

    controller = _new_controller(rt, config)
    status = controller._battle_page.detect_entry_status(timeout=10.0)
    rt.note(f'异常恢复入口状态: {status.value}')
    if status is DecisiveEntryStatus.REFRESHED:
        return
    if status is DecisiveEntryStatus.CHALLENGING:
        rt.note('决战仍在进行，保留当前进度并继续恢复，不执行章节重置')
        return
    if status is not DecisiveEntryStatus.REFRESH:
        raise RuntimeError(f'异常恢复无法重置章节，入口状态: {status.value}')
    if not controller._battle_page.reset_chapter():
        raise RuntimeError('异常恢复重置章节失败')
    status = controller._battle_page.detect_entry_status(timeout=10.0)
    if status is not DecisiveEntryStatus.REFRESHED:
        raise RuntimeError(f'异常恢复重置后状态异常: {status.value}')


def _new_controller(rt: Any, config: Any) -> Any:
    from autowsgr.ops import DecisiveController
    from autowsgr.types import DecisivePhase

    controller = DecisiveController(rt.ctx, config)
    controller._resume_mode = True
    controller._has_chosen_fleet = False
    controller._prepare_entry_state()
    controller._state.phase = DecisivePhase.ENTER_MAP
    return controller


def _write_report(rt: Any, report: dict[str, Any]) -> None:
    lines = [
        '# Decisive Stability Report',
        '',
        f'- Started: {report["started"]}',
        f'- Deadline: {report["deadline"]}',
        f'- Seed: {report["seed"]}',
        f'- Tickets requested: {report["tickets_requested"]}',
        f'- Tickets attempted: {len(report["tickets"])}',
        f'- Expedition collections: {report["expedition_collections"]}',
        f'- Restart recoveries: {report["restart_recoveries"]}',
        f'- Halted: {report["halted"]}',
        '',
        '## Tickets',
        '',
        '| Ticket | Status | Leaves | Retreats | Expeditions | Error |',
        '| ---: | --- | ---: | ---: | ---: | --- |',
    ]
    lines.extend(
        '| {ticket} | {status} | {leaves} | {retreats} | {expeditions} | {error} |'.format(
            ticket=item['ticket'],
            status=item['status'],
            leaves=item['leaves'],
            retreats=item['retreats'],
            expeditions=item['expeditions'],
            error=item.get('error', ''),
        )
        for item in report['tickets']
    )
    lines.extend(['', '## Events', ''])
    lines.extend(f'- {event}' for event in report['events'])
    report_path = rt.log_dir / 'stability_report.md'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    rt.note(f'稳定性报告: {report_path.resolve()}')


def _run_ticket(  # noqa: C901, PLR0912, PLR0915
    rt: Any, config: Any, ticket: int, rng: random.Random, report: dict[str, Any]
) -> bool:
    from autowsgr.ops import collect_expedition
    from autowsgr.types import DecisivePhase

    item = {
        'ticket': ticket,
        'status': 'error',
        'leaves': 0,
        'retreats': 0,
        'expeditions': 0,
    }
    report['tickets'].append(item)
    controller = rt.action(f'票 {ticket}: 定位决战总览', _new_controller, rt, config)
    if controller is rt.FAILED:
        return False

    injections = ['leave', 'leave', 'leave', 'retreat']
    rng.shuffle(injections)
    consecutive_system_retreats = 0

    def recover_and_reenter(label: str) -> None:
        if rt.action(label, controller._prepare_entry_state) is rt.FAILED:
            raise RuntimeError(label)
        controller._state.phase = DecisivePhase.ENTER_MAP
        controller._wait_deadline = time.monotonic() + 15.0

    handlers = {
        DecisivePhase.ENTER_MAP: controller._handle_enter_map,
        DecisivePhase.WAITING_FOR_MAP: controller._handle_waiting_for_map,
        DecisivePhase.USE_LAST_FLEET: controller._handle_use_last_fleet,
        DecisivePhase.DOCK_FULL: controller._handle_dock_full,
        DecisivePhase.CHOOSE_FLEET: controller._handle_choose_fleet,
        DecisivePhase.ADVANCE_CHOICE: controller._handle_advance_choice,
        DecisivePhase.PREPARE_COMBAT: controller._handle_prepare_combat,
        DecisivePhase.IN_COMBAT: controller._handle_combat,
        DecisivePhase.NODE_RESULT: controller._handle_node_result,
        DecisivePhase.STAGE_CLEAR: controller._handle_stage_clear,
    }

    try:
        while time.monotonic() < report['deadline_monotonic']:
            phase = controller._state.phase
            if phase is DecisivePhase.CHAPTER_CLEAR:
                item['status'] = 'clear'
                break
            if phase in {DecisivePhase.IN_COMBAT, DecisivePhase.STAGE_CLEAR}:
                consecutive_system_retreats = 0

            if phase is DecisivePhase.PREPARE_COMBAT and injections:
                injection = injections.pop(0)
                if injection == 'leave':
                    if (
                        rt.action(
                            f'票 {ticket}: 暂离 #{item["leaves"] + 1}', controller._execute_leave
                        )
                        is rt.FAILED
                    ):
                        raise RuntimeError('暂离失败')
                    item['leaves'] += 1
                    report['events'].append(f'票 {ticket}: leave {item["leaves"]}')
                    collected = rt.action(
                        f'票 {ticket}: 暂离后收取远征',
                        collect_expedition,
                        rt.ctx,
                    )
                    if collected is rt.FAILED:
                        raise RuntimeError('远征收取失败')
                    item['expeditions'] += int(bool(collected))
                    report['expedition_collections'] += int(bool(collected))
                    recover_and_reenter(f'票 {ticket}: 暂离后重新进入决战')
                else:
                    if (
                        rt.action(
                            f'票 {ticket}: 撤退 #{item["retreats"] + 1}',
                            controller._execute_retreat,
                        )
                        is rt.FAILED
                    ):
                        raise RuntimeError('撤退失败')
                    item['retreats'] += 1
                    report['events'].append(f'票 {ticket}: retreat {item["retreats"]}')
                    controller._state.reset()
                    controller._advance_source_node = None
                    controller._state.phase = DecisivePhase.ENTER_MAP
                    recover_and_reenter(f'票 {ticket}: 撤退后重新进入决战')
                continue

            if phase is DecisivePhase.RETREAT:
                consecutive_system_retreats += 1
                if consecutive_system_retreats > 5:
                    report['halted'] = True
                    raise RuntimeError('连续系统撤退超过 5 次，决战没有取得进展')
                if (
                    rt.action(f'票 {ticket}: 处理系统撤退', controller._execute_retreat)
                    is rt.FAILED
                ):
                    raise RuntimeError('系统撤退失败')
                controller._state.reset()
                controller._advance_source_node = None
                controller._state.phase = DecisivePhase.ENTER_MAP
                recover_and_reenter(f'票 {ticket}: 系统撤退后恢复')
                continue

            if phase is DecisivePhase.LEAVE:
                if rt.action(f'票 {ticket}: 处理系统暂离', controller._execute_leave) is rt.FAILED:
                    raise RuntimeError('系统暂离失败')
                recover_and_reenter(f'票 {ticket}: 系统暂离后恢复')
                continue

            handler = handlers.get(phase)
            if handler is None:
                raise RuntimeError(f'未知决战阶段: {phase}')
            if rt.action(f'票 {ticket}: {phase.name}', handler) is rt.FAILED:
                raise RuntimeError(f'决战阶段失败: {phase.name}')
        else:
            item['error'] = '达到稳定性测试截止时间'
    except Exception as exc:
        item['error'] = str(exc)
        report['events'].append(f'票 {ticket}: error={exc}')
        if rt.action(f'票 {ticket}: 异常后重启游戏回首页', _restart_to_home, rt) is not rt.FAILED:
            if (
                rt.action(
                    f'票 {ticket}: 异常后重置决战章节',
                    _reset_after_restart,
                    rt,
                    config,
                )
                is not rt.FAILED
            ):
                report['restart_recoveries'] += 1
            else:
                report['halted'] = True
        else:
            report['halted'] = True
    return item['status'] == 'clear' and not item.get('error') and not injections


def run(rt: Any) -> bool:
    from autowsgr.ops import collect_expedition

    config = rt.ctx.config.decisive_battle
    if config is None:
        rt.note('usersettings.yaml 未配置 decisive_battle')
        return False
    if rt.ctx.ocr is None:
        rt.note('决战稳定性测试需要 OCR，请使用 --with-ocr')
        return False
    if rt.args.tickets < 1:
        rt.note('tickets 必须大于 0')
        return False

    started = datetime.now().astimezone()
    deadline = _parse_deadline(rt.args.until)
    seed = rt.args.seed if rt.args.seed is not None else random.SystemRandom().randrange(1 << 30)
    report: dict[str, Any] = {
        'started': started.isoformat(timespec='seconds'),
        'deadline': deadline.isoformat(timespec='seconds'),
        'deadline_monotonic': time.monotonic() + max(0.0, (deadline - started).total_seconds()),
        'seed': seed,
        'tickets_requested': rt.args.tickets,
        'tickets': [],
        'expedition_collections': 0,
        'restart_recoveries': 0,
        'halted': False,
        'events': [],
    }
    rng = random.Random(seed)
    rt.note(
        f'稳定性测试: tickets={rt.args.tickets}, until={deadline.isoformat(timespec="seconds")}, seed={seed}'
    )

    if rt.action('测试开始: 确保决战章节已重置', _reset_after_restart, rt, config) is rt.FAILED:
        report['halted'] = True
        report['events'].append('稳定性测试因初始章节状态恢复失败而停止')
        _write_report(rt, report)
        return False

    for ticket in range(1, rt.args.tickets + 1):
        if time.monotonic() >= report['deadline_monotonic']:
            break
        _run_ticket(rt, config, ticket, rng, report)
        if report['halted']:
            report['events'].append('稳定性测试因异常恢复失败而停止')
            break

    if report['halted']:
        _write_report(rt, report)
        return False

    if not rt.args.stop_after_tickets:
        while time.monotonic() < report['deadline_monotonic']:
            collected = rt.action('截止前定时远征检查', collect_expedition, rt.ctx)
            if collected is not rt.FAILED:
                report['expedition_collections'] += int(bool(collected))
            time.sleep(
                min(
                    float(rt.args.expedition_interval),
                    max(1.0, report['deadline_monotonic'] - time.monotonic()),
                )
            )

    _write_report(rt, report)
    return bool(report['tickets']) and all(
        item['status'] == 'clear' and item['leaves'] >= 3 and item['retreats'] >= 1
        for item in report['tickets']
    )
