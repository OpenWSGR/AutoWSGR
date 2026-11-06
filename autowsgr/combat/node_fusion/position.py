"""仅检测本帧黄色船标的位置，不持有当前节点或航行状态。"""

from __future__ import annotations

import cv2
import numpy as np

from autowsgr.combat.recognizer import CombatRecognizer
from autowsgr.combat.state import CombatPhase
from autowsgr.infra.logger import get_logger
from autowsgr.vision import MatchStrategy, PixelChecker, PixelRule, PixelSignature


_log = get_logger('combat.tracker')


class ShipPositionDetector:
    """通过黄色像素簇和邻域像素验证，返回当前帧的船位。"""

    def __init__(self) -> None:
        self._detection_status = 'unseen'

    @property
    def detection_status(self) -> str:
        """当前检测状态，区分页面遮挡、无候选簇、像素校验失败及成功。"""
        return self._detection_status

    def _recheck_pixel(self, center: tuple[float, float], screen: np.ndarray) -> bool:
        """验证中心及其左右两侧的像素特征。
        返回值
        -------
        bool
            三个位置都满足像素特征时返回 ``True``。
        """
        cx, cy = center

        # 定义三个检查位置的像素规则
        rules = [
            PixelRule.of(cx, cy, (239, 219, 106), tolerance=40.0),  # 中心
            PixelRule.of(cx - 0.03, cy, (231, 222, 101), tolerance=40.0),  # 左侧
            PixelRule.of(cx + 0.03, cy, (231, 222, 101), tolerance=40.0),  # 右侧
        ]

        sig = PixelSignature(
            name='小船像素验证',
            strategy=MatchStrategy.ALL,
            rules=rules,
        )
        return PixelChecker.check_signature(screen, sig).matched

    @staticmethod
    def _find_yellow_cluster(screen: np.ndarray) -> tuple[float, float] | None:
        """在截图中查找最大的黄色像素簇，返回其质心的相对坐标。
        返回值
        -------
        tuple[float, float] | None
            最大黄色簇质心 ``(rel_x, rel_y)``；未找到返回 ``None``。
        """
        r, g, b = screen[:, :, 0], screen[:, :, 1], screen[:, :, 2]
        mask = (
            (r.astype(np.int16) > 200)
            & (g.astype(np.int16) > 180)
            & (b.astype(np.int16) > 50)
            & (b.astype(np.int16) < 150)
        ).astype(np.uint8)

        num_labels, _labels, stats, centroids = cv2.connectedComponentsWithStats(
            mask,
            connectivity=8,
        )
        # 标签 0 是背景，跳过
        if num_labels <= 1:
            return None

        # 按面积降序排列（排除背景标签 0）
        _min_area = 200
        best_label = -1
        best_area = 0
        for label_id in range(1, num_labels):
            area = int(stats[label_id, cv2.CC_STAT_AREA])
            if area >= _min_area and area > best_area:
                best_area = area
                best_label = label_id

        if best_label < 0:
            return None

        h, w = screen.shape[:2]
        cx_abs, cy_abs = centroids[best_label]
        return (cx_abs / w, cy_abs / h)

    def is_spot_page(self, screen: np.ndarray) -> bool:
        return (
            CombatRecognizer.identify_current(screen, [CombatPhase.SPOT_ENEMY_SUCCESS]) is not None
        )

    def detect(self, screen: np.ndarray) -> tuple[float, float] | None:
        """在战斗移动界面检测黄色小船图标的位置。
        返回值
        -------
        tuple[float, float] | None
            检测到的相对坐标 ``(x, y)``；未检测到或像素验证失败返回 ``None``。
        """
        # 检查是否为索敌页面，如果是索敌页面，则返回None
        if self.is_spot_page(screen):
            self._detection_status = 'spot_enemy'
            _log.debug(
                '[船位检测] 检测到是索敌页面，不更新位置',
            )
            return None

        center = self._find_yellow_cluster(screen)
        if center is None:
            self._detection_status = 'no_cluster'
            return None
        if self._recheck_pixel(center, screen):
            self._detection_status = 'detected'
            _log.debug(
                '[船位检测] 小船位置更新: ({:.3f}, {:.3f}) [黄色簇检测+像素验证]',
                center[0],
                center[1],
            )
            return center

        self._detection_status = 'pixel_rejected'
        _log.debug(
            '[船位检测] 黄色簇检测到但像素验证失败: ({:.3f}, {:.3f})',
            center[0],
            center[1],
        )
        return None
