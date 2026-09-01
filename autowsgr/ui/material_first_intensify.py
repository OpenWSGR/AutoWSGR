"""Fresh material-first intensify navigation.

This module intentionally owns its coordinates, visual predicates and state
machine. It does not depend on the legacy intensify page controller or the
generic page navigation graph.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import cv2
import numpy as np

from autowsgr.ui.tabbed_page import TabbedPageType, get_active_tab_index, identify_page_type


if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.emulator.controller import Controller


class MaterialFirstState(StrEnum):
    MAIN = 'main'
    SIDEBAR = 'sidebar'
    INTENSIFY_SUBMENU = 'intensify_submenu'
    INTENSIFY_HOME = 'intensify_home'
    MATERIAL_SELECTOR = 'material_selector'


class MaterialFirstNavigationError(RuntimeError):
    """Raised when a visual transition cannot be proven."""


@dataclass(frozen=True)
class MaterialSelectorEvidence:
    cyan_edge_pixels: int
    confirm_blue_ratio: float
    panel_dark_ratio: float


_CLICK_OPEN_SIDEBAR = (0.0490, 0.8981)
_CLICK_SIDEBAR_INTENSIFY = (0.1563, 0.5000)
_CLICK_INTENSIFY_SUBMENU = (0.3750, 0.5000)
_CLICK_MATERIAL_SLOT = (0.2630, 0.3380)

_MAIN_PROBES = (
    (0.6453, 0.9375, (52, 115, 168)),
    (0.8126, 0.8681, (213, 206, 180)),
    (0.9696, 0.8903, (121, 130, 135)),
    (0.0570, 0.8847, (251, 252, 255)),
)
_SIDEBAR_PROBES = (
    (0.0417, 0.0806),
    (0.0422, 0.2102),
    (0.0453, 0.3463),
    (0.0406, 0.4676),
    (0.0396, 0.6028),
    (0.0432, 0.7231),
)


def _pixel(screen: np.ndarray, x: float, y: float) -> np.ndarray:
    height, width = screen.shape[:2]
    return screen[min(height - 1, round(y * height)), min(width - 1, round(x * width))].astype(
        np.int16
    )


def _near(actual: np.ndarray, expected: tuple[int, int, int], tolerance: float) -> bool:
    return float(np.linalg.norm(actual - np.asarray(expected, dtype=np.int16))) <= tolerance


def is_main_screen(screen: np.ndarray) -> bool:
    """Recognize the clean main screen from four independent RGB probes."""
    if all(_near(_pixel(screen, x, y), color, 30.0) for x, y, color in _MAIN_PROBES):
        return True
    try:
        from autowsgr.ui.main_page import MainPage
        match = MainPage.is_current_page(screen)
        return bool(match.matched)
    except Exception:
        return False


def is_sidebar_screen(screen: np.ndarray) -> bool:
    """Recognize the six-item sidebar without importing its old controller."""
    matches = 0
    for x, y in _SIDEBAR_PROBES:
        value = _pixel(screen, x, y)
        if _near(value, (57, 57, 57), 30.0) or _near(value, (0, 160, 232), 30.0):
            matches += 1
    if matches >= 5:
        return True
    try:
        from autowsgr.ui.sidebar_page import SidebarPage
        return bool(SidebarPage.is_current_page(screen).matched)
    except Exception:
        return False


def is_intensify_submenu_screen(screen: np.ndarray) -> bool:
    """Recognize the open intensify submenu before its first option is clicked."""
    height, width = screen.shape[:2]
    first_option = screen[
        round(height * 0.46) : round(height * 0.54),
        round(width * 0.305) : round(width * 0.475),
    ]
    second_option = screen[
        round(height * 0.565) : round(height * 0.645),
        round(width * 0.305) : round(width * 0.475),
    ]
    first_white_ratio = float(np.mean(np.min(first_option, axis=2) > 200))
    second_white_ratio = float(np.mean(np.min(second_option, axis=2) > 200))
    return is_sidebar_screen(screen) and (first_white_ratio >= 0.40 and second_white_ratio >= 0.40)


def _enter_intensify_home_after_main(self) -> np.ndarray:
    """Continue the verified navigation after MAIN has already been proven."""
    self._ctrl.click(*_CLICK_OPEN_SIDEBAR)
    self._wait_stable(MaterialFirstState.SIDEBAR, is_sidebar_screen)

    self._ctrl.click(*_CLICK_SIDEBAR_INTENSIFY)
    self._wait_stable(
        MaterialFirstState.INTENSIFY_SUBMENU,
        is_intensify_submenu_screen,
    )
    self._ctrl.click(*_CLICK_INTENSIFY_SUBMENU)
    return self._wait_stable(MaterialFirstState.INTENSIFY_HOME, is_intensify_home_screen)


def is_intensify_home_screen(screen: np.ndarray) -> bool:
    """Recognize the first intensify tab before opening either selector."""
    return (
        identify_page_type(screen) == TabbedPageType.INTENSIFY
        and get_active_tab_index(screen) == 0
        and not is_material_selector_screen(screen)
    )


def material_selector_evidence(screen: np.ndarray) -> MaterialSelectorEvidence:
    """Measure visual evidence unique to the material selector."""
    height, width = screen.shape[:2]
    hsv = cv2.cvtColor(screen, cv2.COLOR_RGB2HSV)

    grid = hsv[round(height * 0.11) : round(height * 0.96), : round(width * 0.81)]
    cyan = cv2.inRange(
        grid,
        np.array((85, 120, 90), dtype=np.uint8),
        np.array((115, 255, 255), dtype=np.uint8),
    )

    confirm = hsv[
        round(height * 0.84) : round(height * 0.97),
        round(width * 0.84) : round(width * 0.98),
    ]
    confirm_blue = cv2.inRange(
        confirm,
        np.array((90, 100, 100), dtype=np.uint8),
        np.array((120, 255, 255), dtype=np.uint8),
    )

    panel = screen[
        round(height * 0.11) : round(height * 0.82),
        round(width * 0.83) : round(width * 0.99),
    ]
    panel_dark = np.max(panel, axis=2) < 100
    return MaterialSelectorEvidence(
        cyan_edge_pixels=int(np.count_nonzero(cyan)),
        confirm_blue_ratio=float(np.mean(confirm_blue > 0)),
        panel_dark_ratio=float(np.mean(panel_dark)),
    )


def is_material_selector_screen(screen: np.ndarray) -> bool:
    """Recognize material selection without OCR or ship identity work."""
    evidence = material_selector_evidence(screen)
    return (
        evidence.cyan_edge_pixels >= 4_000
        and evidence.confirm_blue_ratio >= 0.35
        and evidence.panel_dark_ratio >= 0.20
    )


class MaterialFirstIntensifyController:
    """Navigate from main screen to material selector, then stop."""

    def __init__(
        self,
        ctrl: Controller,
        *,
        timeout: float = 6.0,
        interval: float = 0.25,
        stable_frames: int = 2,
    ) -> None:
        self._ctrl = ctrl
        self._timeout = timeout
        self._interval = interval
        self._stable_frames = stable_frames

    def _wait_stable(
        self,
        state: MaterialFirstState,
        predicate: Callable[[np.ndarray], bool],
        *,
        initial_screen: np.ndarray | None = None,
    ) -> np.ndarray:
        deadline = time.monotonic() + self._timeout
        stable = 1 if initial_screen is not None and predicate(initial_screen) else 0
        last = initial_screen if stable else None
        if stable >= self._stable_frames:
            return last
        while time.monotonic() < deadline:
            screen = self._ctrl.screenshot()
            if predicate(screen):
                stable += 1
                last = screen
                if stable >= self._stable_frames:
                    return last
            else:
                stable = 0
                last = None
            time.sleep(self._interval)
        raise MaterialFirstNavigationError(f'未连续稳定识别页面: {state.value}')

    def enter_intensify_home_from_main(self) -> np.ndarray:
        """Execute only MAIN -> sidebar -> intensify home, then stop."""
        self._wait_stable(MaterialFirstState.MAIN, is_main_screen)

        return self._enter_intensify_home_after_main()

    def _enter_intensify_home_after_main(self) -> np.ndarray:
        """Continue the verified navigation after MAIN has already been proven."""
        deadline = time.monotonic() + self._timeout
        sidebar_ok = False
        while time.monotonic() < deadline:
            self._ctrl.click(*_CLICK_OPEN_SIDEBAR)
            time.sleep(0.5)
            screen = self._ctrl.screenshot()
            if is_sidebar_screen(screen):
                sidebar_ok = True
                break
        if not sidebar_ok:
            raise MaterialFirstNavigationError('未连续稳定识别页面: sidebar')

        self._ctrl.click(*_CLICK_SIDEBAR_INTENSIFY)
        time.sleep(0.5)
        self._wait_stable(
            MaterialFirstState.INTENSIFY_SUBMENU,
            is_intensify_submenu_screen,
        )
        self._ctrl.click(*_CLICK_INTENSIFY_SUBMENU)
        time.sleep(1.0)
        return self._wait_stable(MaterialFirstState.INTENSIFY_HOME, is_intensify_home_screen)

    def ensure_intensify_home(self, ctx: object | None = None) -> np.ndarray:
        """Accept an existing intensify home or use the verified MAIN navigation path."""
        screen = self._ctrl.screenshot()
        if is_intensify_home_screen(screen):
            return self._wait_stable(
                MaterialFirstState.INTENSIFY_HOME,
                is_intensify_home_screen,
                initial_screen=screen,
            )
        # 如果当前由于上次异常停留在选择页（目标页/素材页），先点击左上角返回强化首页
        from autowsgr.ui.live_intensify import is_target_selector
        if is_target_selector(screen) or is_material_selector_screen(screen):
            self._ctrl.click(0.048, 0.088)
            time.sleep(0.8)
            screen = self._ctrl.screenshot()
            if is_intensify_home_screen(screen):
                return self._wait_stable(
                    MaterialFirstState.INTENSIFY_HOME,
                    is_intensify_home_screen,
                    initial_screen=screen,
                )
        if is_main_screen(screen):
            self._wait_stable(MaterialFirstState.MAIN, is_main_screen, initial_screen=screen)
            return self._enter_intensify_home_after_main()
        if ctx is not None:
            from autowsgr.ops.navigate import goto_page
            from autowsgr.types import PageName
            goto_page(ctx, PageName.INTENSIFY)
            screen = self._ctrl.screenshot()
            if is_intensify_home_screen(screen):
                return self._wait_stable(
                    MaterialFirstState.INTENSIFY_HOME,
                    is_intensify_home_screen,
                    initial_screen=screen,
                )
        raise MaterialFirstNavigationError('强化扫描起始页面既不是 main 也不是 intensify_home')

    def enter_material_selector_from_main(self) -> MaterialSelectorEvidence:
        """Enter the material selector directly without requiring a target ship."""
        self.enter_intensify_home_from_main()
        self._ctrl.click(*_CLICK_MATERIAL_SLOT)
        screen = self._wait_stable(
            MaterialFirstState.MATERIAL_SELECTOR,
            is_material_selector_screen,
        )
        return material_selector_evidence(screen)
