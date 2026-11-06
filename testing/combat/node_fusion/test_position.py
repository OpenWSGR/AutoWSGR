"""纯船位检测器不缓存旧位置，也不进行节点预测。"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.combat.node_fusion.position import ShipPositionDetector


@pytest.fixture
def screen() -> np.ndarray:
    return np.zeros((540, 960, 3), dtype=np.uint8)


def test_same_position_is_fresh_but_missing_frame_returns_none(
    monkeypatch: pytest.MonkeyPatch, screen: np.ndarray
) -> None:
    detector = ShipPositionDetector()
    monkeypatch.setattr(detector, 'is_spot_page', lambda _: False)
    monkeypatch.setattr(
        detector, '_find_yellow_cluster', MagicMock(side_effect=[(0.3, 0.5), (0.3, 0.5), None])
    )
    monkeypatch.setattr(detector, '_recheck_pixel', lambda *_: True)
    assert detector.detect(screen) == (0.3, 0.5)
    assert detector.detect(screen) == (0.3, 0.5)
    assert detector.detection_status == 'detected'
    assert detector.detect(screen) is None
    assert detector.detection_status == 'no_cluster'


def test_spot_page_never_provides_ship_position(
    monkeypatch: pytest.MonkeyPatch, screen: np.ndarray
) -> None:
    detector = ShipPositionDetector()
    monkeypatch.setattr(detector, 'is_spot_page', lambda _: True)
    find = MagicMock()
    monkeypatch.setattr(detector, '_find_yellow_cluster', find)
    assert detector.detect(screen) is None
    assert detector.detection_status == 'spot_enemy'
    find.assert_not_called()


def test_pixel_rejection_has_its_own_status(
    monkeypatch: pytest.MonkeyPatch, screen: np.ndarray
) -> None:
    detector = ShipPositionDetector()
    monkeypatch.setattr(detector, 'is_spot_page', lambda _: False)
    monkeypatch.setattr(detector, '_find_yellow_cluster', lambda _: (0.4, 0.5))
    monkeypatch.setattr(detector, '_recheck_pixel', lambda *_: False)
    assert detector.detect(screen) is None
    assert detector.detection_status == 'pixel_rejected'


def test_yellow_cluster_requires_minimum_area(screen: np.ndarray) -> None:
    screen[100:110, 200:210] = (239, 219, 106)
    assert ShipPositionDetector._find_yellow_cluster(screen) is None
    screen[200:220, 400:420] = (239, 219, 106)
    assert ShipPositionDetector._find_yellow_cluster(screen) == pytest.approx(
        (409.5 / 960, 209.5 / 540)
    )
