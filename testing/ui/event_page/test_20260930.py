"""0930 资源、导航、地图加载和舰种识别回归；无需设备或 OCR 模型。"""

from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from autowsgr.combat.node_tracker import MapNodeData
from autowsgr.infra.exceptions import ActionFailedError
from autowsgr.types import PageName, ShipType
from autowsgr.ui.build_page import BuildPage
from autowsgr.ui.event.event_page import BaseEventPage
from autowsgr.ui.event.popups import dismiss_quiz
from autowsgr.ui.main_page.event_nav import _try_navigate_to_event
from autowsgr.ui.page import get_current_page
from autowsgr.ui.utils.ship_list import extract_ship_type_from_text
from autowsgr.vision.ocr_rules import SHIP_TYPE_OCR_ALLOWLIST


_IMAGES = Path(__file__).resolve().parents[3] / 'autowsgr/data/images/event'


def _screen(name: str, width: int = 960) -> np.ndarray:
    screen = np.zeros((540, 960, 3), dtype=np.uint8)
    image = cv2.cvtColor(cv2.imread(str(_IMAGES / f'{name}_20260930_540p.png')), cv2.COLOR_BGR2RGB)
    h, w = image.shape[:2]
    screen[100 : 100 + h, 400 : 400 + w] = image
    if width != 960:
        screen = cv2.resize(screen, (width, width * 9 // 16))
    return screen


@pytest.mark.parametrize('width', [960, 1280])
@pytest.mark.parametrize('name', ['event_title', 'fight_button', 'quiz_prompt'])
def test_event_anchor_recognized_by_navigator(name: str, width: int) -> None:
    screen = _screen(name, width)
    assert BaseEventPage.is_current_page(screen)
    assert (
        get_current_page(screen, candidates=[PageName.EVENT_MAP, PageName.DECISIVE_BATTLE])
        == PageName.EVENT_MAP
    )


def test_blank_and_entry_icon_are_not_event_map() -> None:
    assert not BaseEventPage.is_current_page(np.zeros((540, 960, 3), dtype=np.uint8))
    assert not BaseEventPage.is_current_page(_screen('event_icon'))


def test_entry_uses_detected_icon_center(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = MagicMock()
    ctrl.screenshot.return_value = _screen('event_icon')
    monkeypatch.setattr('autowsgr.ui.main_page.event_nav.detect_overlay', lambda _: None)
    monkeypatch.setattr(
        'autowsgr.ui.main_page.event_nav.ImageChecker.template_exists', lambda *_a, **_k: True
    )
    monkeypatch.setattr('autowsgr.ui.main_page.event_nav.time.sleep', lambda _: None)
    assert _try_navigate_to_event(ctrl, lambda _: True)
    x, y = ctrl.click.call_args.args
    assert x == pytest.approx((400 + 131 / 2) / 960, abs=0.002)
    assert y == pytest.approx((100 + 207 / 2) / 540, abs=0.002)


def test_quiz_cancel_is_inside_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = MagicMock()
    ctrl.screenshot.side_effect = [_screen('quiz_prompt'), np.zeros((540, 960, 3), dtype=np.uint8)]
    monkeypatch.setattr('autowsgr.ui.event.popups.time.sleep', lambda _: None)
    dismiss_quiz(ctrl)
    x, y = ctrl.click.call_args.args
    assert 400 / 960 < x < 785 / 960
    assert 100 / 540 < y < 303 / 540
    assert ctrl.click.call_count == 1


def test_quiz_failure_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = MagicMock()
    ctrl.screenshot.return_value = _screen('quiz_prompt')
    monkeypatch.setattr('autowsgr.ui.event.popups.time.sleep', lambda _: None)
    with pytest.raises(ActionFailedError, match='三次'):
        dismiss_quiz(ctrl)
    assert ctrl.click.call_count == 3


@pytest.mark.parametrize('chapter', ['E', 'H'])
@pytest.mark.parametrize('map_id', range(1, 7))
def test_packaged_event_map_graph(chapter: str, map_id: int) -> None:
    data = MapNodeData.load_event('20260930', chapter, map_id)
    assert data is not None
    assert '0' in data
    for name in ['0', *data.node_names]:
        node = data.get(name)
        assert node is not None
        assert 0 <= node.x <= 1
        assert 0 <= node.y <= 1
        assert all(n in data for n in node.next_nodes)


@pytest.mark.parametrize('text', ['防战', '防 战（U国）', '(U国)防战'])
def test_air_defense_battleship_ocr(text: str) -> None:
    assert extract_ship_type_from_text(text) is ShipType.AABG
    assert ShipType('防战') is ShipType.AABG
    assert all(c in SHIP_TYPE_OCR_ALLOWLIST for c in '防战')
    assert extract_ship_type_from_text('导战') is ShipType.BG


def test_unverified_destroy_type_fails_before_clicking() -> None:
    ctx = MagicMock()
    page = BuildPage(ctx)
    with pytest.raises(ValueError, match='未校准'):
        page.destroy_ships([ShipType.AABG])
    ctx.ctrl.click.assert_not_called()


@pytest.mark.parametrize('map_code', ['E1', 'H6'])
def test_start_fight_uses_0930_layout_and_button(
    monkeypatch: pytest.MonkeyPatch,
    map_code: str,
) -> None:
    ctx = MagicMock()
    ctx.ctrl.screenshot.return_value = _screen('fight_button')
    page = BaseEventPage(ctx, event_name='20260930')
    monkeypatch.setattr(page, 'ensure_no_overlay', lambda: None)
    difficulty = MagicMock()
    monkeypatch.setattr(page, '_change_difficulty', difficulty)
    wait = MagicMock()
    monkeypatch.setattr('autowsgr.ui.event.event_page.click_and_wait_for_page', wait)
    page.start_fight(map_code)
    difficulty.assert_called_once_with(map_code[0])
    expected = (0.0879801735, 0.2251655629) if map_code == 'E1' else (0.7806691450, 0.7483443709)
    ctx.ctrl.click.assert_called_once_with(*expected)
    assert wait.call_args.kwargs['click_coord'] == pytest.approx(
        (499.5 / 960, 138.5 / 540), abs=0.002
    )


def test_0930_rejects_previous_event_entrance() -> None:
    ctx = MagicMock()
    with pytest.raises(ValueError, match='纯数字'):
        BaseEventPage(ctx, event_name='20260930').start_fight('E1', 'alpha')
    ctx.ctrl.click.assert_not_called()


def test_0930_example_plan_loads() -> None:
    from autowsgr.ops.normal_fight import get_normal_fight_plan

    plan = get_normal_fight_plan('20260930-E1')
    assert (plan.event_name, plan.chapter, plan.map_id, plan.entrance) == ('20260930', 'E', 1, None)
