"""远征面板 Mixin — 远征收取操作。"""

from __future__ import annotations

import time

from loguru import logger

from autowsgr.image_resources import Templates
from autowsgr.ui.map.base import BaseMapPage
from autowsgr.ui.map.data import (
    EXPEDITION_READY_COLOR,
    EXPEDITION_SLOT_PROBES,
    EXPEDITION_SLOT_TOLERANCE,
    MapPanel,
)
from autowsgr.ui.page import confirm_operation, wait_for_page
from autowsgr.types import PageName
from autowsgr.vision import ImageChecker, PixelChecker


class ExpeditionPanelMixin(BaseMapPage):
    """Mixin: 远征面板操作 — 远征收取。"""

    # ── 查询 ─────────────────────────────────────────────────────────────

    @staticmethod
    def find_ready_expedition_slot(screen) -> int | None:
        """检测 4 个远征槽位，返回第一个已完成 (黄色) 的槽位索引。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)。

        Returns
        -------
        int | None
            就绪槽位索引 (0–3)，无就绪则返回 ``None``。
        """
        for i, (px, py) in enumerate(EXPEDITION_SLOT_PROBES):
            actual = PixelChecker.get_pixel(screen, px, py)
            if actual.near(EXPEDITION_READY_COLOR, EXPEDITION_SLOT_TOLERANCE):
                logger.debug(
                    "[UI] 远征槽位 {} 就绪: 实际颜色 {} ≈ 黄色",
                    i + 1,
                    actual.as_rgb_tuple(),
                )
                return i
        return None

    # ── 操作 ─────────────────────────────────────────────────────────────

    def collect_expedition(self) -> int:
        """在远征面板收取已完成的远征。

        Returns
        -------
        int
            收取的远征数量。

        Raises
        ------
        NavigationError
            远征通知仍在但 10s 内无法检测到就绪槽位。
        """
        collected = 0
        for _ in range(8):
            # ── 检测就绪槽位 (含等待逻辑) ──
            screen = self._ctrl.screenshot()
            slot_idx = self.find_ready_expedition_slot(screen)
            if slot_idx is None:
                # 无黄色槽位 — 检查上方探测点是否仍报告有远征
                if not self.has_expedition_notification(screen):
                    logger.debug("[UI] 远征收取: 无就绪槽位且无通知，结束")
                    break

                # 上方探测点仍亮 — 等待槽位刷新 (最多 10s)
                logger.debug("[UI] 远征收取: 通知仍在，等待槽位刷新…")
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline:
                    time.sleep(0.1)
                    screen = self._ctrl.screenshot()
                    slot_idx = self.find_ready_expedition_slot(screen)
                    if slot_idx is not None:
                        break
                    if not self.has_expedition_notification(screen):
                        logger.debug("[UI] 远征收取: 通知消失，结束")
                        break
                else:
                    from autowsgr.ui.page import NavigationError

                    raise NavigationError(
                        "远征收取超时: 通知仍在但 10s 内未检测到就绪槽位"
                    )

                if slot_idx is None:
                    break

            slot_pos = EXPEDITION_SLOT_PROBES[slot_idx]
            logger.info(
                "[UI] 远征收取: 点击槽位 {} ({:.4f}, {:.4f})",
                slot_idx + 1,
                *slot_pos,
            )

            # 1. 点击就绪槽位
            self._ctrl.click(*slot_pos)
            time.sleep(1.0)

            # 2. 等待远征结果画面
            _result_templates = [Templates.Symbol.CLICK_TO_CONTINUE]
            _wait_deadline = time.monotonic() + 5.0
            while time.monotonic() < _wait_deadline:
                screen = self._ctrl.screenshot()
                if ImageChecker.template_exists(screen, _result_templates):
                    break
            time.sleep(0.25)

            # 3. 点击屏幕中央跳过动画
            self.click_screen_center()
            time.sleep(1.0)

            # 4. 确认弹窗
            confirm_operation(
                self._ctrl,
                must_confirm=True,
                delay=0.5,
                confidence=0.9,
                timeout=5.0,
            )

            # 5. 等待回到地图页面
            wait_for_page(
                self._ctrl,
                checker=self.is_current_page,
                source="远征收取",
                target=PageName.MAP,
            )

            collected += 1

        logger.info("[UI] 远征收取: {} 支", collected)
        return collected
