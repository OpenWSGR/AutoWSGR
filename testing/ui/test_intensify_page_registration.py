from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import cv2

import autowsgr.ui  # noqa: F401
from autowsgr.types import PageName
from autowsgr.ui.intensify_page import IntensifyPage
from autowsgr.ui.page import get_current_page, get_registered_pages


if TYPE_CHECKING:
    import numpy as np


_FIXTURE = (
    Path(__file__).parents[1]
    / 'fixtures'
    / 'intensify-navigation'
    / 'cetus-intensify-home-empty.png'
)


def _screen() -> np.ndarray:
    return cv2.cvtColor(cv2.imread(str(_FIXTURE)), cv2.COLOR_BGR2RGB)


def test_empty_intensify_home_is_registered_as_intensify_page() -> None:
    screen = _screen()

    assert PageName.INTENSIFY.value in get_registered_pages()
    assert IntensifyPage.is_current_page(screen)
    assert get_current_page(screen, candidates={PageName.INTENSIFY.value}) == PageName.INTENSIFY.value
    assert get_current_page(screen) == PageName.INTENSIFY.value
