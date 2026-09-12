"""Long-running decisive stability test with controlled leave/retreat injections."""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    import argparse


DESC = '决战稳定性长跑: 按参数插入暂离/撤退，并定时检查远征'


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--tickets', type=int, default=10, help='决战票数 (默认 10)')
    parser.add_argument(
        '--force-reset-start',
        action='store_true',
        help='测试开始时即使入口为 challenging 也尝试识别并重置章节',
    )
    parser.add_argument(
        '--leaves-per-ticket',
        type=int,
        default=3,
        help='每票注入暂离次数 (默认 3)',
    )
    parser.add_argument(
        '--retreats-per-ticket',
        type=int,
        default=1,
        help='每票注入撤退次数 (默认 1)',
    )
    parser.add_argument(
        '--retreat-node',
        default=None,
        help='指定节点注入一次撤退，例如 B；留空时沿用随机注入顺序',
    )
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
        help='运行期间远征检查间隔秒数 (默认 300)',
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


def _reset_after_restart(rt: Any, config: Any, force: bool = False) -> None:
    """Reset the chapter before reusing the device after a ticket error."""
    from autowsgr.types import DecisiveEntryStatus

    controller = _new_controller(rt, config)
    status = controller._battle_page.detect_entry_status(timeout=10.0)
    rt.note(f'异常恢复入口状态: {status.value}')
    if status is DecisiveEntryStatus.REFRESHED:
        return
    if status is DecisiveEntryStatus.CHALLENGING and not force:
        rt.note('决战仍在进行，保留当前进度并继续恢复，不执行章节重置')
        return
    if status not in {DecisiveEntryStatus.REFRESH, DecisiveEntryStatus.CHALLENGING}:
        raise RuntimeError(f'异常恢复无法重置章节，入口状态: {status.value}')
    if not controller._battle_page.reset_chapter():
        raise RuntimeError('异常恢复重置章节失败')
    status = controller._battle_page.detect_entry_status(timeout=10.0)
    if status is not DecisiveEntryStatus.REFRESHED:
        raise RuntimeError(f'异常恢复重置后状态异常: {status.value}')


def _new_controller(rt: Any, config: Any) -> Any:
    from autowsgr.ops import DecisiveController
    from autowsgr.types import DecisivePhase, PageName
    from autowsgr.ui import get_current_page
    from autowsgr.ui.battle.preparation import BattlePreparationPage
    from autowsgr.ui.decisive.battle_page import DecisiveBattlePage
    from autowsgr.ui.decisive.overlay import detect_decisive_overlay, is_decisive_map_page

    controller = DecisiveController(rt.ctx, config)

    screen = rt.ctx.ctrl.screenshot()
    current_page = get_current_page(screen)
    if is_decisive_map_page(screen) or detect_decisive_overlay(screen) is not None:
        raise RuntimeError(
            '当前处于决战地图或浮窗；进程外没有可靠的小节状态，拒绝猜测 stage 后继续'
        )
    if BattlePreparationPage.is_current_page(screen).matched:
        raise RuntimeError('当前处于决战编队页；缺少小节上下文，拒绝盲目恢复')

    if DecisiveBattlePage.is_current_page(screen).matched:
        rt.note('启动状态识别: 决战总览页')
        controller._battle_page.navigate_to_chapter(config.chapter)
    elif current_page in {PageName.MAIN.value, PageName.MAP.value}:
        rt.note(f'启动状态识别: {current_page or "未知页面"}，导航到决战总览')
        controller._prepare_entry_state()
        if not DecisiveBattlePage.is_current_page(rt.ctx.ctrl.screenshot()).matched:
            raise RuntimeError('导航到决战总览后仍未识别到决战入口')
    else:
        raise RuntimeError(f'启动状态无法安全接管: {current_page or "未知页面"}')

    # Only an observed overview may start a fresh controller context.
    controller._resume_mode = True
    controller._has_chosen_fleet = False
    controller._full_recovery_check = True
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
        f'- Leaves per ticket: {report["leaves_per_ticket"]}',
        f'- Retreats per ticket: {report["retreats_per_ticket"]}',
        f'- Retreat node: {report["retreat_node"] or "random"}',
        f'- Expedition interval: {report["expedition_interval"]}s',
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

    leaves_per_ticket = max(0, int(getattr(rt.args, 'leaves_per_ticket', 3)))
    retreats_per_ticket = max(0, int(getattr(rt.args, 'retreats_per_ticket', 1)))
    retreat_node = getattr(rt.args, 'retreat_node', None)
    injections = ['leave'] * leaves_per_ticket + ['retreat'] * retreats_per_ticket
    if retreat_node:
        injections = ['leave'] * leaves_per_ticket
    consecutive_system_retreats = 0

    def recover_and_reenter(label: str) -> None:
        if rt.action(label, controller._prepare_entry_state) is rt.FAILED:
            raise RuntimeError(label)
        controller._state.phase = DecisivePhase.ENTER_MAP
        controller._wait_deadline = time.monotonic() + 15.0

    def collect_expedition_if_due() -> None:
        interval = float(getattr(rt.args, 'expedition_interval', 900))
        now = time.monotonic()
        if now - report['last_expedition_check'] < interval:
            return
        collected = rt.action(
            f'票 {ticket}: 每 {int(interval)} 秒远征检查',
            collect_expedition,
            rt.ctx,
        )
        if collected is rt.FAILED:
            raise RuntimeError('定时远征收取失败')
        item['expeditions'] += int(bool(collected))
        report['expedition_collections'] += int(bool(collected))
        report['last_expedition_check'] = time.monotonic()

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
            collect_expedition_if_due()
            phase = controller._state.phase
            if phase is DecisivePhase.CHAPTER_CLEAR:
                item['status'] = 'clear'
                break
            if phase in {DecisivePhase.IN_COMBAT, DecisivePhase.STAGE_CLEAR}:
                consecutive_system_retreats = 0

            targeted_retreat = (
                phase is DecisivePhase.PREPARE_COMBAT
                and retreat_node
                and controller._state.node == retreat_node
                and item['retreats'] < retreats_per_ticket
            )
            if targeted_retreat or (phase is DecisivePhase.PREPARE_COMBAT and injections):
                injection = 'retreat' if targeted_retreat else injections.pop(0)
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
        'leaves_per_ticket': max(0, int(getattr(rt.args, 'leaves_per_ticket', 3))),
        'retreats_per_ticket': max(0, int(getattr(rt.args, 'retreats_per_ticket', 1))),
        'retreat_node': getattr(rt.args, 'retreat_node', None),
        'expedition_interval': int(getattr(rt.args, 'expedition_interval', 900)),
        'tickets': [],
        'expedition_collections': 0,
        'restart_recoveries': 0,
        'halted': False,
        'events': [],
        'last_expedition_check': time.monotonic(),
    }
    rng = random.Random(seed)
    rt.note(
        f'稳定性测试: tickets={rt.args.tickets}, until={deadline.isoformat(timespec="seconds")}, seed={seed}'
    )

    if (
        rt.action(
            '测试开始: 确保决战章节已重置',
            _reset_after_restart,
            rt,
            config,
            bool(getattr(rt.args, 'force_reset_start', False)),
        )
        is rt.FAILED
    ):
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
        item['status'] == 'clear'
        and item['leaves'] >= report['leaves_per_ticket']
        and item['retreats'] >= report['retreats_per_ticket']
        for item in report['tickets']
    )
