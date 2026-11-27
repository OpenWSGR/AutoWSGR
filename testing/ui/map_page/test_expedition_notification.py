"""Regression coverage for the expedition great-success x2 badge (PR #286)."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import numpy as np
import pytest

from autowsgr.context import GameContext
from autowsgr.emulator import AndroidController
from autowsgr.ui.map.page import MapPage
from autowsgr.ui.map.panels import expedition


def _badge_frame(width: int, height: int, kind: str) -> np.ndarray:
    """Draw the historical badge geometry independently of detector constants."""
    screen = np.full((height, width, 3), (22, 37, 62), dtype=np.uint8)
    if kind == 'notice':
        ys, xs = np.ogrid[:height, :width]
        circle = (xs * 960 / width - 470) ** 2 + (ys * 540 / height - 11) ** 2 <= 12**2
        screen[circle] = (255, 89, 45)
        return screen
    bounds = {'none': None, 'bonus': (459, 525), 'bonus_only': (510, 525)}
    band = bounds[kind]
    if band is not None:
        left, right = band
        screen[
            int(7 * height / 540) : int(16 * height / 540),
            int(left * width / 960) : int(right * width / 960),
        ] = (255, 89, 45)
    return screen


def _ready_slot_two(screen: np.ndarray) -> np.ndarray:
    screen = screen.copy()
    height, width = screen.shape[:2]
    x, y = int(0.8531 * width), int(0.4736 * height)
    screen[y - 2 : y + 3, x - 2 : x + 3] = (251, 227, 64)
    return screen


@pytest.mark.parametrize(('width', 'height'), [(960, 540), (1280, 720), (1600, 896)])
@pytest.mark.parametrize(
    ('kind', 'expected'),
    [('none', False), ('notice', True), ('bonus', False), ('bonus_only', False)],
)
def test_notice_excludes_long_bonus_badge(
    width: int, height: int, kind: str, expected: bool
) -> None:
    screen = _badge_frame(width, height, kind)

    assert MapPage.has_expedition_notification(screen) is expected


@pytest.mark.parametrize(('width', 'height'), [(960, 540), (1280, 720), (1600, 896)])
def test_ready_slot_has_round_completion_notice(width: int, height: int) -> None:
    screen = _ready_slot_two(_badge_frame(width, height, 'notice'))

    assert MapPage.has_expedition_notification(screen) is True
    assert MapPage.find_ready_expedition_slot(screen) == 1


@pytest.mark.parametrize(('width', 'height'), [(960, 540), (1280, 720), (1600, 896)])
def test_bonus_without_ready_slots_stops_without_waiting(
    monkeypatch: pytest.MonkeyPatch, width: int, height: int
) -> None:
    ctrl = MagicMock(spec=AndroidController)
    ctrl.screenshot.return_value = _badge_frame(width, height, 'bonus')
    page = MapPage(GameContext(ctrl=ctrl, config=MagicMock(), ocr=None))
    sleep = MagicMock(side_effect=AssertionError('Bonus badge must not start the refresh wait'))
    monkeypatch.setattr(expedition.time, 'sleep', sleep)

    assert page.collect_expedition() == 0

    ctrl.click.assert_not_called()
    sleep.assert_not_called()


def test_completion_notice_changes_to_bonus_after_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = _badge_frame(1600, 896, 'bonus')
    # A ready expedition's round icon takes precedence over the bonus banner.
    # Once collected, the bonus banner becomes visible again without a ready slot.
    ready = _ready_slot_two(_badge_frame(1600, 896, 'notice'))
    ctrl = MagicMock(spec=AndroidController)
    ctrl.screenshot.side_effect = [ready, ready, empty]
    page = MapPage(GameContext(ctrl=ctrl, config=MagicMock(), ocr=None))

    def sleep(seconds: float) -> None:
        if seconds == 0.1:
            pytest.fail('The remaining bonus badge must not start the refresh wait')

    monkeypatch.setattr(expedition.time, 'sleep', sleep)
    monkeypatch.setattr(expedition.ImageChecker, 'template_exists', lambda *_args: True)
    confirm = MagicMock(return_value=True)
    wait = MagicMock()
    monkeypatch.setattr(expedition, 'confirm_operation', confirm)
    monkeypatch.setattr(expedition, 'wait_for_page', wait)

    assert page.collect_expedition() == 1

    assert ctrl.click.call_args_list == [call(0.8531, 0.4736), call(0.76, 0.5)]
    confirm.assert_called_once()
    wait.assert_called_once()
