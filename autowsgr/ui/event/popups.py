"""活动答题浮层：识别完整提示后，在浮层内定位取消按钮。"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import TYPE_CHECKING

from autowsgr.image_resources._lazy import load_template
from autowsgr.infra.exceptions import ActionFailedError
from autowsgr.vision import ROI, ImageChecker


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.emulator import AndroidController
    from autowsgr.vision import ImageMatchDetail, ImageTemplate


@lru_cache(maxsize=1)
def _quiz_templates() -> tuple[ImageTemplate, ImageTemplate]:
    return (
        load_template('event/quiz_prompt_20260930_540p.png', name='event_quiz_20260930'),
        load_template('event/quiz_cancel_20260930_540p.png', name='event_quiz_cancel_20260930'),
    )


def quiz_prompt_detail(screen: np.ndarray) -> ImageMatchDetail | None:
    return ImageChecker.find_template(screen, _quiz_templates()[0], confidence=0.85)


def dismiss_quiz(ctrl: AndroidController) -> None:
    """最多取消三次，消失后才继续；不执行自动答题或点击其他取消按钮。"""
    for _ in range(3):
        screen = ctrl.screenshot()
        prompt = quiz_prompt_detail(screen)
        if prompt is None:
            return
        x1, y1 = prompt.top_left
        x2, y2 = prompt.bottom_right
        cancel = ImageChecker.find_template(
            screen,
            _quiz_templates()[1],
            roi=ROI(x1, y1, x2, y2),
            confidence=0.8,
        )
        if cancel is None:
            raise ActionFailedError('活动答题提示已出现，但未找到取消按钮')
        ctrl.click(*cancel.center)
        time.sleep(0.3)
    if quiz_prompt_detail(ctrl.screenshot()) is not None:
        raise ActionFailedError('活动答题提示取消三次后仍未关闭')
