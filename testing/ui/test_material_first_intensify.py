from __future__ import annotations

from collections import deque
from pathlib import Path

import cv2
import numpy as np
import pytest

from autowsgr.ui.material_first_intensify import (
    MaterialFirstIntensifyController,
    MaterialFirstNavigationError,
    is_intensify_home_screen,
    is_intensify_submenu_screen,
    is_main_screen,
    is_material_selector_screen,
    is_sidebar_screen,
    material_selector_evidence,
)


_FIXTURES = Path(__file__).parents[1] / 'fixtures' / 'intensify-navigation'


def _fixture(name: str) -> np.ndarray:
    screen = cv2.imread(str(_FIXTURES / name), cv2.IMREAD_COLOR)
    assert screen is not None
    return cv2.cvtColor(screen, cv2.COLOR_BGR2RGB)


def _screen(kind: str) -> np.ndarray:
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    if kind == 'main':
        for x, y, color in (
            (0.6453, 0.9375, (52, 115, 168)),
            (0.8126, 0.8681, (213, 206, 180)),
            (0.9696, 0.8903, (121, 130, 135)),
            (0.0570, 0.8847, (251, 252, 255)),
        ):
            screen[round(y * 1080), round(x * 1920)] = color
    elif kind == 'sidebar':
        for x, y in (
            (0.0417, 0.0806),
            (0.0422, 0.2102),
            (0.0453, 0.3463),
            (0.0406, 0.4676),
            (0.0396, 0.6028),
            (0.0432, 0.7231),
        ):
            screen[round(y * 1080), round(x * 1920)] = (57, 57, 57)
    elif kind == 'intensify':
        screen[round(0.0472 * 1080), round(0.1539 * 1920)] = (15, 132, 228)
        screen[round(0.0625 * 1080), round(0.2719 * 1920)] = (22, 37, 62)
        screen[round(0.0528 * 1080), round(0.4039 * 1920)] = (22, 37, 62)
    elif kind == 'material':
        screen[120:1030, :1550] = (15, 45, 70)
        for x in range(86, 1546, 211):
            screen[145:1010, x : x + 4] = (0, 170, 235)
        screen[929:1026, 1613:1882] = (20, 135, 225)
        screen[120:886, 1594:1900] = (35, 45, 55)
    return screen


class _Controller:
    def __init__(self, screens: list[np.ndarray]) -> None:
        self.screens = deque(screens)
        self.clicks: list[tuple[float, float]] = []

    def screenshot(self) -> np.ndarray:
        if len(self.screens) > 1:
            return self.screens.popleft()
        return self.screens[0]

    def click(self, x: float, y: float) -> None:
        self.clicks.append((x, y))


def test_cetus_main_fixture_is_accepted_as_the_only_start_state() -> None:
    screen = _fixture('cetus-main.png')

    assert is_main_screen(screen)
    assert not is_sidebar_screen(screen)
    assert not is_intensify_home_screen(screen)
    assert not is_material_selector_screen(screen)


def test_cetus_sidebar_and_intensify_submenu_fixtures_are_distinct() -> None:
    sidebar = _fixture('cetus-sidebar.png')
    submenu = _fixture('cetus-intensify-submenu.png')

    assert is_sidebar_screen(sidebar)
    assert not is_intensify_submenu_screen(sidebar)
    assert is_sidebar_screen(submenu)
    assert is_intensify_submenu_screen(submenu)


def test_cetus_intensify_home_fixture_requires_the_intensify_page_type() -> None:
    screen = _fixture('cetus-intensify-home.png')
    generic_tabs = np.zeros_like(screen)
    for x, y, color in (
        (0.1539, 0.0472, (15, 132, 228)),
        (0.2719, 0.0625, (22, 37, 62)),
        (0.4039, 0.0528, (22, 37, 62)),
    ):
        generic_tabs[round(y * screen.shape[0]), round(x * screen.shape[1])] = color

    assert is_intensify_home_screen(screen)
    assert not is_intensify_home_screen(generic_tabs)


def test_empty_cetus_intensify_home_is_directly_recognized() -> None:
    screen = _fixture('cetus-intensify-home-empty.png')

    assert is_intensify_home_screen(screen)
    assert not is_main_screen(screen)
    assert not is_sidebar_screen(screen)
    assert not is_material_selector_screen(screen)


def test_cetus_material_selector_fixture_has_strong_positive_evidence() -> None:
    screen = _fixture('cetus-material-selector.png')
    evidence = material_selector_evidence(screen)

    assert is_material_selector_screen(screen)
    assert not is_main_screen(screen)
    assert not is_sidebar_screen(screen)
    assert not is_intensify_home_screen(screen)
    assert evidence.cyan_edge_pixels == 697_112
    assert evidence.confirm_blue_ratio == pytest.approx(0.508634554035171)
    assert evidence.panel_dark_ratio == pytest.approx(0.8955318959183587)


def test_enters_intensify_home_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _Controller(
        [
            _fixture('cetus-main.png'),
            _fixture('cetus-main.png'),
            _fixture('cetus-sidebar.png'),
            _fixture('cetus-sidebar.png'),
            _fixture('cetus-intensify-submenu.png'),
            _fixture('cetus-intensify-submenu.png'),
            _fixture('cetus-intensify-home.png'),
            _fixture('cetus-intensify-home.png'),
        ]
    )
    monkeypatch.setattr('autowsgr.ui.material_first_intensify.time.sleep', lambda _seconds: None)

    MaterialFirstIntensifyController(ctrl).enter_intensify_home_from_main()

    assert ctrl.clicks == [
        (0.0490, 0.8981),
        (0.1563, 0.5000),
        (0.3750, 0.5000),
    ]
    assert len(ctrl.screens) == 1


def test_accepts_existing_intensify_home_without_input(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _Controller(
        [
            _fixture('cetus-intensify-home.png'),
            _fixture('cetus-intensify-home.png'),
        ]
    )
    monkeypatch.setattr('autowsgr.ui.material_first_intensify.time.sleep', lambda _seconds: None)

    MaterialFirstIntensifyController(ctrl).ensure_intensify_home()

    assert ctrl.clicks == []


def test_accepts_existing_empty_intensify_home_without_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl = _Controller(
        [
            _fixture('cetus-intensify-home-empty.png'),
            _fixture('cetus-intensify-home-empty.png'),
        ]
    )
    monkeypatch.setattr('autowsgr.ui.material_first_intensify.time.sleep', lambda _seconds: None)

    MaterialFirstIntensifyController(ctrl).ensure_intensify_home()

    assert ctrl.clicks == []


def test_ensure_intensify_home_preserves_verified_main_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl = _Controller(
        [
            _fixture('cetus-main.png'),
            _fixture('cetus-main.png'),
            _fixture('cetus-sidebar.png'),
            _fixture('cetus-sidebar.png'),
            _fixture('cetus-intensify-submenu.png'),
            _fixture('cetus-intensify-submenu.png'),
            _fixture('cetus-intensify-home.png'),
            _fixture('cetus-intensify-home.png'),
        ]
    )
    monkeypatch.setattr('autowsgr.ui.material_first_intensify.time.sleep', lambda _seconds: None)

    MaterialFirstIntensifyController(ctrl).ensure_intensify_home()

    assert ctrl.clicks == [
        (0.0490, 0.8981),
        (0.1563, 0.5000),
        (0.3750, 0.5000),
    ]


def test_enters_material_selector_without_target(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _Controller(
        [
            _fixture('cetus-main.png'),
            _fixture('cetus-main.png'),
            _fixture('cetus-sidebar.png'),
            _fixture('cetus-sidebar.png'),
            _fixture('cetus-intensify-submenu.png'),
            _fixture('cetus-intensify-submenu.png'),
            _fixture('cetus-intensify-home.png'),
            _fixture('cetus-intensify-home.png'),
            _fixture('cetus-material-selector.png'),
            _fixture('cetus-material-selector.png'),
        ]
    )
    monkeypatch.setattr('autowsgr.ui.material_first_intensify.time.sleep', lambda _seconds: None)

    evidence = MaterialFirstIntensifyController(ctrl).enter_material_selector_from_main()

    assert ctrl.clicks[-1] == (0.2630, 0.3380)
    assert evidence.confirm_blue_ratio >= 0.35


def test_material_selector_requires_confirm_button() -> None:
    screen = _screen('material')
    screen[929:1026, 1613:1882] = 0

    assert not is_material_selector_screen(screen)


def test_target_selector_is_not_material_selector() -> None:
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    screen[135:1034, :1550] = (15, 45, 70)
    screen[135:260, 1580] = (192, 193, 195)

    assert not is_material_selector_screen(screen)


def test_fails_closed_before_submenu_click_when_submenu_is_not_proven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl = _Controller(
        [
            _fixture('cetus-main.png'),
            _fixture('cetus-main.png'),
            _fixture('cetus-sidebar.png'),
            _fixture('cetus-sidebar.png'),
            _fixture('cetus-sidebar.png'),
        ]
    )
    ticks = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 10.0])
    monkeypatch.setattr('autowsgr.ui.material_first_intensify.time.monotonic', lambda: next(ticks))
    monkeypatch.setattr('autowsgr.ui.material_first_intensify.time.sleep', lambda _seconds: None)

    with pytest.raises(MaterialFirstNavigationError, match='intensify_submenu'):
        MaterialFirstIntensifyController(ctrl, timeout=1.0).enter_intensify_home_from_main()

    assert ctrl.clicks == [
        (0.0490, 0.8981),
        (0.1563, 0.5000),
    ]


def test_fails_closed_before_any_click_when_main_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl = _Controller([_screen('unknown')])
    ticks = iter([0.0, 0.1, 10.0])
    monkeypatch.setattr('autowsgr.ui.material_first_intensify.time.monotonic', lambda: next(ticks))
    monkeypatch.setattr('autowsgr.ui.material_first_intensify.time.sleep', lambda _seconds: None)

    with pytest.raises(MaterialFirstNavigationError, match='main'):
        MaterialFirstIntensifyController(ctrl, timeout=1.0).enter_intensify_home_from_main()

    assert ctrl.clicks == []
