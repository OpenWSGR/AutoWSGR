"""Collect on the round completion icon while excluding the long bonus badge."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import numpy as np
import pytest

import autowsgr.ops.expedition as expedition_ops
from autowsgr.context import GameContext
from autowsgr.emulator import AndroidController
from autowsgr.types import PageName
from autowsgr.ui.map.data import MapPanel
from autowsgr.ui.map.page import MapPage


def _main_frame(*, ready: bool) -> np.ndarray:
    screen = np.full((540, 960, 3), (22, 37, 62), dtype=np.uint8)
    if ready:
        screen[452:457, 931:936] = (255, 89, 45)
    return screen


def _map_frame(*, ready: bool) -> np.ndarray:
    screen = np.full((540, 960, 3), (22, 37, 62), dtype=np.uint8)
    if ready:
        ys, xs = np.ogrid[:540, :960]
        circle = (xs - 470) ** 2 + (ys - 11) ** 2 <= 12**2
        screen[circle] = (255, 89, 45)
        screen[253:258, 817:822] = (251, 227, 64)
    else:
        screen[7:16, 459:525] = (255, 89, 45)
    return screen


@pytest.mark.parametrize('collected', [0, 1])
def test_main_and_map_completion_notices_allow_collection(
    monkeypatch: pytest.MonkeyPatch, collected: int
) -> None:
    ctrl = MagicMock(spec=AndroidController)
    ctrl.screenshot.side_effect = [_main_frame(ready=True), _map_frame(ready=True)]
    ctx = GameContext(ctrl=ctrl, config=MagicMock(), ocr=None)
    page = MagicMock(spec=MapPage)
    page.collect_expedition.return_value = collected
    page_type = MagicMock(wraps=MapPage, return_value=page)
    goto = MagicMock()
    monkeypatch.setattr(expedition_ops, 'recover_to_main_or_restart', MagicMock())
    monkeypatch.setattr(expedition_ops, 'goto_page', goto)
    monkeypatch.setattr(expedition_ops, 'MapPage', page_type)

    assert expedition_ops.collect_expedition(ctx) is bool(collected)

    page.switch_panel.assert_called_once_with(MapPanel.EXPEDITION)
    page.collect_expedition.assert_called_once_with()
    assert goto.call_args_list == [
        call(ctx, PageName.MAIN),
        call(ctx, PageName.MAP),
        call(ctx, PageName.MAIN),
    ]


def test_main_notice_but_map_bonus_does_not_collect(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = MagicMock(spec=AndroidController)
    ctrl.screenshot.side_effect = [_main_frame(ready=True), _map_frame(ready=False)]
    ctx = GameContext(ctrl=ctrl, config=MagicMock(), ocr=None)
    page = MagicMock(spec=MapPage)
    page.collect_expedition.return_value = 1
    page_type = MagicMock(wraps=MapPage, return_value=page)
    goto = MagicMock()
    monkeypatch.setattr(expedition_ops, 'recover_to_main_or_restart', MagicMock())
    monkeypatch.setattr(expedition_ops, 'goto_page', goto)
    monkeypatch.setattr(expedition_ops, 'MapPage', page_type)

    assert expedition_ops.collect_expedition(ctx) is False

    page.switch_panel.assert_not_called()
    page.collect_expedition.assert_not_called()
    assert goto.call_args_list == [
        call(ctx, PageName.MAIN),
        call(ctx, PageName.MAP),
        call(ctx, PageName.MAIN),
    ]


def test_no_main_notice_does_not_enter_expedition(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = MagicMock(spec=AndroidController)
    ctrl.screenshot.return_value = _main_frame(ready=False)
    ctx = GameContext(ctrl=ctrl, config=MagicMock(), ocr=None)
    page_type = MagicMock(wraps=MapPage)
    goto = MagicMock()
    monkeypatch.setattr(expedition_ops, 'recover_to_main_or_restart', MagicMock())
    monkeypatch.setattr(expedition_ops, 'goto_page', goto)
    monkeypatch.setattr(expedition_ops, 'MapPage', page_type)

    assert expedition_ops.collect_expedition(ctx) is False

    page_type.assert_not_called()
    goto.assert_called_once_with(ctx, PageName.MAIN)
