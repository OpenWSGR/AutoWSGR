"""决战编队和前进点页面导航。"""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from autowsgr.emulator.frame import CapturedFrame
from autowsgr.image_resources import Templates
from autowsgr.infra import ActionFailedError, DecisiveConfig
from autowsgr.types import DecisivePhase, ShipDamageState
from autowsgr.ui.battle.constants import CLICK_BACK as PREPARATION_BACK
from autowsgr.ui.choose_ship_page import ChooseShipPage
from autowsgr.ui.decisive import preparation
from autowsgr.ui.decisive.battle_page import DecisiveBattlePage
from autowsgr.ui.decisive.map_controller import DecisiveMapController
from autowsgr.ui.decisive.overlay import (
    ADVANCE_CHOICE_ROI,
    ADVANCE_CHOICE_THREE_ROI,
    CLICK_ADVANCE_CONFIRM,
    CLICK_LEAVE,
    CLICK_RETREAT_BUTTON,
    DecisiveOverlay,
)
from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage
from autowsgr.ui.utils.navigation import NavigationError, click_and_wait_for_page, wait_for_page


@pytest.mark.parametrize('count', [2, 3])
def test_leftmost_route_uses_visible_layout_when_hint_is_wrong(count: int) -> None:
    image = np.full((720, 1280, 3), 40, dtype=np.uint8)
    blank = image.copy()
    patch = Templates.Decisive.ADVANCE_CHOICE.image
    x, y = (143, 236) if count == 3 else (325, 238)
    h, w = patch.shape[:2]
    image[y : y + h, x : x + w] = patch
    ctx = SimpleNamespace(stop_event=threading.Event(), ctrl=MagicMock(), ocr=MagicMock())
    page = DecisiveMapController(ctx, DecisiveConfig())
    page.configure_route(2 if count == 3 else 3)
    ctx.ctrl.screenshot.side_effect = [image, blank]
    page.select_advance_card(0)
    area = ADVANCE_CHOICE_THREE_ROI if count == 3 else ADVANCE_CHOICE_ROI
    assert ctx.ctrl.click.call_args_list == [
        call(area.center[0], 0.5),
        call(*CLICK_ADVANCE_CONFIRM),
    ]


def test_fleet_candidates_read_only_the_first_visible_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = SimpleNamespace(stop_event=MagicMock(), ctrl=MagicMock(), ocr=MagicMock())
    ctx.stop_event.is_set.return_value = False
    page = DecisiveBattlePreparationPage(ctx, DecisiveConfig())
    preparing = np.zeros((2, 2, 3), np.uint8)
    opening = np.ones_like(preparing)
    expanded = np.full_like(preparing, 2)
    ctx.ctrl.screenshot.side_effect = [opening, expanded, preparing]
    monkeypatch.setattr(ChooseShipPage, 'is_current_page', lambda image: image is opening)
    monkeypatch.setattr(page, 'is_current_page', lambda image: image is preparing)

    def recognize_names(_ocr, image: np.ndarray) -> set[str]:
        ctx.stop_event.wait.assert_called_once_with(0.3)
        assert image is expanded
        return {'U-96', 'U-47'}

    recognize = MagicMock(side_effect=recognize_names)
    monkeypatch.setattr(preparation, 'recognize_ships_in_list', recognize)

    assert page.read_first_screen_candidates() == {'U-96', 'U-47'}
    recognize.assert_called_once_with(ctx.ocr, expanded)
    assert ctx.ctrl.click.call_count == 2
    ctx.ctrl.swipe.assert_not_called()


@pytest.mark.parametrize('duplicate', [False, True])
def test_inventory_registers_repair_marker_only_after_complete_formation(
    monkeypatch: pytest.MonkeyPatch, duplicate: bool
) -> None:
    ctx = SimpleNamespace(stop_event=threading.Event(), ctrl=MagicMock(), ocr=MagicMock())
    controller = DecisiveMapController(ctx, DecisiveConfig())
    controller.enter_formation = MagicMock()
    page = MagicMock()
    monkeypatch.setattr(
        'autowsgr.ui.decisive.map_controller.DecisiveBattlePreparationPage', lambda *_: page
    )
    damage = dict.fromkeys(range(6), ShipDamageState.NO_SHIP)
    damage.update({0: ShipDamageState.REPAIRING, 1: ShipDamageState.NORMAL})
    complete = ['351', 'U-96', None, None, None, None]
    incomplete = ['U-47', 'U-47' if duplicate else None, None, None, None, None]
    page.read_repair_snapshot.side_effect = [(incomplete, damage), (complete, damage)]
    page.read_first_screen_candidates.return_value = {'U-1206'}
    report = MagicMock()

    fleet, _, inventory = controller.check_fleet(report)
    assert fleet == complete
    assert inventory == {'351', 'U-96', 'U-1206'}
    assert page.read_repair_snapshot.call_args.kwargs['fresh']
    report.assert_called_once_with('351')


def test_map_classification_checks_each_obstruction_once(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = SimpleNamespace(stop_event=threading.Event(), ctrl=MagicMock(), ocr=MagicMock())
    page = DecisiveMapController(ctx, DecisiveConfig())
    image = np.zeros((2, 2, 3), np.uint8)
    page._has_stage_clear_choices = MagicMock(return_value=False)
    page._has_reward_drop = MagicMock(return_value=False)
    page._find_use_last = MagicMock(return_value=None)
    page.detect_overlay = MagicMock(return_value=None)
    page._has_map_controls = MagicMock(return_value=True)
    monkeypatch.setattr(
        'autowsgr.ui.decisive.map_controller.ImageChecker.template_exists', lambda *_a, **_kw: False
    )
    assert page.detect_decisive_phase(image) is DecisivePhase.PREPARE_COMBAT
    for checker in (
        page._has_stage_clear_choices,
        page._has_reward_drop,
        page._find_use_last,
        page._has_map_controls,
    ):
        checker.assert_called_once_with(image)
    page.detect_overlay.assert_called_once_with(image, advance_choice_roi=None)
    page.detect_overlay.return_value = DecisiveOverlay.CONFIRM_EXIT
    assert not page.is_map_page(image)


@pytest.mark.parametrize(
    ('start', 'text', 'confidence', 'after_clicks', 'error', 'clicks'),
    [
        (
            'prep',
            '主力决战舰队',
            0.99,
            ['map', 'exit', 'exit', 'overview'],
            None,
            [PREPARATION_BACK, CLICK_RETREAT_BUTTON, CLICK_LEAVE],
        ),
        ('map', '', 0.0, ['exit', 'exit', 'overview'], None, [CLICK_RETREAT_BUTTON, CLICK_LEAVE]),
        ('ordinary', '主力决战舰队', 1.0, [], None, []),
        ('other', '', 0.0, [], None, []),
        ('prep', '决战舰队', 0.99, [], ActionFailedError, []),
        ('prep', '主力决战舰队', 0.5, [], ActionFailedError, []),
        ('prep', '主力决战舰队', 1.0, ['other'], TimeoutError, [PREPARATION_BACK]),
        ('map', '', 0.0, ['exit', 'other'], TimeoutError, [CLICK_RETREAT_BUTTON]),
    ],
)
def test_cold_start_confirms_each_screen_before_leaving(
    monkeypatch: pytest.MonkeyPatch,
    start: str,
    text: str,
    confidence: float,
    after_clicks: list[str],
    error: type[Exception] | None,
    clicks: list[tuple[float, float]],
) -> None:
    screens = {
        name: np.zeros((720, 1280, 3), np.uint8)
        for name in ('prep', 'ordinary', 'other', 'map', 'exit', 'overview')
    }
    screens['prep'][87:144, 113:307] = 170
    screens['ordinary'][122:127, 94:99] = (16, 133, 228)  # 普通第一舰队的选中标签
    ctx = SimpleNamespace(ctrl=MagicMock(), ocr=MagicMock(), stop_event=threading.Event())
    page = DecisiveMapController(ctx, DecisiveConfig())
    page._wait_timeout = 0
    ctx.ctrl.capture_frame.return_value.image = screens[start]
    ctx.ctrl.screenshot.side_effect = [screens[name] for name in after_clicks]
    ctx.ocr.recognize_single.return_value = SimpleNamespace(text=text, confidence=confidence)
    monkeypatch.setattr(page, 'is_map_page', lambda s: s is screens['map'])
    monkeypatch.setattr(
        page, 'is_fleet_preparation', lambda s: s is screens['prep'] or s is screens['ordinary']
    )
    monkeypatch.setattr(
        page,
        'detect_overlay',
        lambda s: DecisiveOverlay.CONFIRM_EXIT if s is screens['exit'] else None,
    )
    monkeypatch.setattr(DecisiveBattlePage, 'is_current_page', lambda s: s is screens['overview'])

    monkeypatch.setattr('autowsgr.ui.page.get_current_page', lambda *_args, **_kwargs: None)
    monkeypatch.setattr('autowsgr.infra.logger.save_image', MagicMock())
    if error is None:
        assert page.try_leave_interrupted_sortie() is bool(clicks)
    else:
        with pytest.raises(error):
            page.try_leave_interrupted_sortie()
    assert ctx.ctrl.click.call_args_list == [call(*point) for point in clicks]
    if start == 'prep':
        ctx.ocr.recognize_single.assert_called_once()
        title = ctx.ocr.recognize_single.call_args.args[0]
        assert title.shape[:2] == (57, 194)
        assert np.all(title == 170)
    else:
        ctx.ocr.recognize_single.assert_not_called()


@pytest.mark.parametrize(
    ('states', 'expected', 'success'),
    [
        (['overview'], [], True),
        (
            ['map', 'map', 'exit', 'other', 'exit', 'other', 'overview'],
            [CLICK_RETREAT_BUTTON, CLICK_LEAVE],
            True,
        ),
        (['exit', 'exit', 'other', 'overview'], [CLICK_LEAVE], True),
        (['exit'], [CLICK_LEAVE], False),
        (['map'], [CLICK_RETREAT_BUTTON], False),
        (['other'], [], False),
    ],
)
def test_scheduled_leave_clicks_only_confirmed_controls_and_waits_for_overview(
    monkeypatch: pytest.MonkeyPatch, states: list[str], expected: list, success: bool
) -> None:
    screens = {k: np.full((2, 2, 3), i, np.uint8) for i, k in enumerate(set(states))}
    ctx = SimpleNamespace(ctrl=MagicMock(), ocr=MagicMock(), stop_event=threading.Event())
    page = DecisiveMapController(ctx, DecisiveConfig(), wait_timeout=0.8)
    tick = 0

    def capture() -> CapturedFrame:
        screen = screens[states[min(tick, len(states) - 1)]]
        return CapturedFrame(screen, tick, tick * 0.3)

    def advance(_seconds: float) -> None:
        nonlocal tick
        tick += 1

    ctx.ctrl.capture_frame.side_effect = capture
    monkeypatch.setattr(ctx.stop_event, 'wait', advance)
    monkeypatch.setattr('autowsgr.ui.decisive.map_controller.time.monotonic', lambda: tick * 0.3)
    monkeypatch.setattr(page, 'is_map_page', lambda s: s is screens.get('map'))
    monkeypatch.setattr(
        DecisiveBattlePage, 'is_current_page', lambda s: s is screens.get('overview')
    )
    monkeypatch.setattr(
        page,
        'detect_overlay',
        lambda s: DecisiveOverlay.CONFIRM_EXIT if s is screens.get('exit') else None,
    )
    if success:
        page.leave_to_overview()
    else:
        with pytest.raises(ActionFailedError, match='未能确认已返回决战总览'):
            page.leave_to_overview()
    assert ctx.ctrl.click.call_args_list == [call(*point) for point in expected]


@pytest.mark.parametrize('stop_at', ['before_click', 'capture', 'interval'])
def test_page_wait_honors_stop_before_next_ui_action(
    monkeypatch: pytest.MonkeyPatch, stop_at: str
) -> None:
    ctrl = MagicMock()
    event = threading.Event()
    screen = np.zeros((2, 2, 3), np.uint8)
    checker = MagicMock(return_value=False)
    if stop_at == 'before_click':
        event.set()

    def capture() -> np.ndarray:
        if stop_at == 'capture':
            event.set()
        return screen

    ctrl.screenshot.side_effect = capture
    monkeypatch.setattr('autowsgr.ui.page.get_current_page', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(event, 'wait', lambda _interval: event.set())
    with pytest.raises(InterruptedError):
        click_and_wait_for_page(ctrl, (0.5, 0.5), checker, stop_event=event)

    assert ctrl.click.call_count == int(stop_at != 'before_click')
    assert ctrl.screenshot.call_count == int(stop_at != 'before_click')
    assert checker.call_count == int(stop_at == 'interval')


def test_wait_timeout_preserves_navigation_evidence_and_default_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl = MagicMock()
    screen = np.zeros((2, 2, 3), np.uint8)
    ctrl.screenshot.return_value = screen
    monkeypatch.setattr('autowsgr.ui.page.get_current_page', lambda *_args, **_kwargs: None)
    save = MagicMock()
    monkeypatch.setattr('autowsgr.infra.logger.save_image', save)
    with pytest.raises(NavigationError):
        wait_for_page(ctrl, lambda _: False, timeout=0)
    save.assert_called_once_with(screen, tag='NavError')
    save.reset_mock()
    with pytest.raises(TimeoutError) as timeout:
        wait_for_page(ctrl, lambda _: False, timeout=0, timeout_error=TimeoutError)
    assert isinstance(timeout.value.__cause__, NavigationError)
    save.assert_called_once_with(screen, tag='NavError')
