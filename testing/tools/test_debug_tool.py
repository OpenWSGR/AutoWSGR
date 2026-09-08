"""Tests for the unified debug command helpers."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pytest

from tools.debug_toolkit.function.roi import _parse_roi
from tools.debug_toolkit.function.roi import run as run_roi


if TYPE_CHECKING:
    from pathlib import Path


def test_parse_roi_rejects_invalid_order() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match='upper-left'):
        _parse_roi('0.5,0.5,0.4,0.6')


def test_crop_roi_writes_requested_region(tmp_path: Path) -> None:
    source = np.zeros((100, 200, 3), dtype=np.uint8)
    source[20:60, 50:150] = (10, 20, 30)
    source_path = tmp_path / 'screen.png'
    cv2.imwrite(str(source_path), source)

    assert (
        run_roi(
            type(
                'Args',
                (),
                {
                    'image': source_path,
                    'roi': (0.25, 0.2, 0.75, 0.6),
                    'output_root': tmp_path / 'result',
                },
            )()
        )
        == 0
    )
    result = cv2.imread(str(tmp_path / 'result' / 'screen' / '1x' / 'screen_roi_1x.png'))
    assert result is not None
    assert result.shape == (40, 100, 3)
