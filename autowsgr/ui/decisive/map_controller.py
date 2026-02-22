"""决战地图页控制器。

封装所有与决战地图页面的直接交互，包括：

- **页面状态检测**: overlay 检测、地图页确认、dock_full / use_last_fleet
- **Overlay 操作**: 战备舰队获取、前进点选择、确认退出
- **地图操作**: 出征、返回地图、小关通关确认
- **节点间修理**: 进入准备页 → 修理 → 返回地图

``DecisiveController`` 通过本类执行所有地图页层面的 UI 操作，
自身仅负责状态机调度与逻辑决策。
"""

from __future__ import annotations

import time

import numpy as np
from loguru import logger

import autowsgr.ui.decisive.fleet_ocr as _fleet_ocr
from autowsgr.ui.decisive.overlay import (
    ADVANCE_CARD_POSITIONS,
    CLICK_ADVANCE_CONFIRM,
    CLICK_FLEET_CLOSE,
    CLICK_FLEET_REFRESH,
    CLICK_LEAVE,
    CLICK_FORMATION,
    CLICK_RETREAT_BUTTON,
    CLICK_RETREAT_CONFIRM,
    CLICK_SORTIE,
    DecisiveOverlay,
    detect_decisive_overlay,
    get_overlay_signature,
    is_decisive_map_page,
)
from ..page import click_and_wait_for_page
from autowsgr.ui.battle.preparation import BattlePreparationPage, RepairStrategy
from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage
from autowsgr.vision import PixelChecker, ROI, get_api_dll, OCREngine, ImageChecker, PixelSignature, PixelRule, MatchStrategy
from autowsgr.types import FleetSelection, DecisivePhase
from autowsgr.infra import DecisiveConfig
from collections.abc import Callable
from autowsgr.emulator import AndroidController

SKILL_USED = PixelSignature(
    name="skill_used",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1977, 0.9361, (245, 245, 245), tolerance=30.0),
    ],
)


class DecisiveMapController:
    """决战地图页控制器。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    config:
        决战配置。
    ocr:
        OCR 引擎。
    image_matcher:
        图像匹配函数 (可选)。
    """

    def __init__(
        self,
        ctrl: AndroidController,
        config: DecisiveConfig,
        *,
        ocr: OCREngine,
        image_matcher: Callable[[np.ndarray], str | None] | None = None,
    ) -> None:
        self._ctrl = ctrl
        self._config = config
        self._ocr = ocr
        self._image_matcher = image_matcher

    # ══════════════════════════════════════════════════════════════════════
    # 页面状态检测
    # ══════════════════════════════════════════════════════════════════════

    def screenshot(self) -> np.ndarray:
        """获取当前截图。"""
        return self._ctrl.screenshot()

    def detect_overlay(self, screen: np.ndarray | None = None) -> DecisiveOverlay | None:
        """检测当前地图页上的 overlay 类型。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        return detect_decisive_overlay(screen)

    def is_map_page(self, screen: np.ndarray | None = None) -> bool:
        """判断截图是否为决战地图页 (无 overlay 遮挡)。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        return is_decisive_map_page(screen)

    def is_skill_used(self) -> bool:
        screen = self._ctrl.screenshot()
        return PixelChecker.check_signature(screen, SKILL_USED).matched

    def detect_decisive_phase(
        self, screen: np.ndarray | None = None,
    ) -> DecisivePhase | None:
        """单次截图检测当前决战页面状态。

        按以下优先级检测::

            1. dock_full      — 弹窗存活时间极短 (~2s)
            2. use_last_fleet — 进入已有进度章节时弹出
            3. 地图页 (无 overlay)
            4. overlay (战备舰队 / 前进点)

        Returns
        -------
        DecisivePhase | None
            检测到的阶段；过场动画中等未知状态返回 ``None``。
        """
        from autowsgr.image_resources import Templates

        if screen is None:
            screen = self._ctrl.screenshot()

        if ImageChecker.template_exists(
            screen, Templates.Build.SHIP_FULL_DEPOT, confidence=0.8,
        ):
            logger.warning("[地图控制器] 检测到船坞已满弹窗")
            return DecisivePhase.DOCK_FULL

        if ImageChecker.template_exists(
            screen, Templates.Decisive.USE_LAST_FLEET, confidence=0.8,
        ):
            logger.info("[地图控制器] 检测到「使用上次舰队」按钮")
            return DecisivePhase.USE_LAST_FLEET

        if is_decisive_map_page(screen):
            return DecisivePhase.PREPARE_COMBAT

        overlay = detect_decisive_overlay(screen)
        if overlay is not None:
            if overlay == DecisiveOverlay.ADVANCE_CHOICE:
                return DecisivePhase.ADVANCE_CHOICE
            if overlay == DecisiveOverlay.FLEET_ACQUISITION:
                return DecisivePhase.CHOOSE_FLEET

        return None

    def recognize_node(
        self, screen: np.ndarray | None = None, fallback: str = "A",
    ) -> str:
        """DLL 识别当前决战节点字母 (如 'A', 'B')。"""
        if screen is None:
            screen = self._ctrl.screenshot()

        dll = get_api_dll()

        if self._image_matcher is not None:
            match_result = self._image_matcher(screen)
            if match_result is not None:
                logger.debug("[地图控制器] 图标匹配结果: {}", match_result)

        h, w = screen.shape[:2]
        x_center, col_width = 0.47, 0.042
        x1 = max(0, int((x_center - col_width / 2) * w))
        x2 = min(w, int((x_center + col_width / 2) * w))
        col_crop = screen[0:h, x1:x2]

        try:
            result = dll.recognize_map(col_crop)
            if result != "0":
                logger.info("[地图控制器] DLL 节点识别: {}", result)
                return result
        except Exception:
            logger.warning("[地图控制器] DLL 节点识别异常", exc_info=True)

        logger.debug("[地图控制器] 节点识别失败, 回退: {}", fallback)
        return fallback

    # ══════════════════════════════════════════════════════════════════════
    # 战备舰队获取 overlay
    # ══════════════════════════════════════════════════════════════════════

    def recognize_fleet_options(
        self, screen: np.ndarray | None = None,
    ) -> tuple[int, dict[str, FleetSelection]]:
        """OCR 识别战备舰队获取界面的可选项。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        return _fleet_ocr.recognize_fleet_options(self._ocr, self._config, screen)

    def detect_last_offer_name(
        self, screen: np.ndarray | None = None,
    ) -> str | None:
        """读取战备舰队最后一张卡的名称，用于首节点判定修正。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        return _fleet_ocr.detect_last_offer_name(self._ocr, self._config, screen)

    def buy_fleet_option(self, click_position: tuple[float, float]) -> None:
        """点击购买一个舰船/技能卡。"""
        self._ctrl.click(*click_position)
        time.sleep(0.3)

    def refresh_fleet(self) -> None:
        """点击「刷新」按钮，刷新备选舰船。"""
        self._ctrl.click(*CLICK_FLEET_REFRESH)
        time.sleep(1.5)

    def close_fleet_overlay(self) -> None:
        """关闭战备舰队获取 overlay。"""
        self._ctrl.click(*CLICK_FLEET_CLOSE)
        time.sleep(1.0)

    def check_dock_full(self) -> bool:
        """检查当前界面是否出现船坞已满提示。"""
        from autowsgr.image_resources import Templates

        screen = self._ctrl.screenshot()
        return ImageChecker.template_exists(
            screen, Templates.Build.SHIP_FULL_DEPOT, confidence=0.8,
        )

    def click_use_last_fleet(self) -> None:
        """单次尝试点击「使用上次舰队」按钮并确认。

        对应 Legacy ``decisive_battle_image[7]`` + ``click(873, 500)``。
        由状态机多次调度实现重试。
        """
        from autowsgr.image_resources import Templates

        CLICK_CONFIRM_POS: tuple[float, float] = (873 / 960, 500 / 540)

        screen = self._ctrl.screenshot()
        match = ImageChecker.find_template(
            screen, Templates.Decisive.USE_LAST_FLEET, confidence=0.8,
        )
        if match is not None:
            self._ctrl.click(*match.center)
            time.sleep(0.5)

        self._ctrl.click(*CLICK_CONFIRM_POS)
        time.sleep(1.0)

    def use_skill(self) -> list[str]:
        """在地图页使用一次副官技能并返回识别到的舰船。"""
        return _fleet_ocr.use_skill(self._ctrl, self._ocr, self._config)

    def scan_available_ships(self) -> set[str]:
        """在出征准备页通过选船列表扫描可用舰船。"""
        return _fleet_ocr.scan_available_ships(self._ctrl, self._ocr, self._config)

    # ══════════════════════════════════════════════════════════════════════
    # 选择前进点 overlay
    # ══════════════════════════════════════════════════════════════════════

    def select_advance_card(self, index: int) -> None:
        """选择前进点卡片并确认。"""
        if index < len(ADVANCE_CARD_POSITIONS):
            self._ctrl.click(*ADVANCE_CARD_POSITIONS[index])
            time.sleep(0.5)
        self._ctrl.click(*CLICK_ADVANCE_CONFIRM)
        time.sleep(1.5)

    # ══════════════════════════════════════════════════════════════════════
    # 地图操作
    # ══════════════════════════════════════════════════════════════════════

    def enter_formation(self) -> None:
        """点击右下角「编队」按钮。"""
        # TODO: 改进鲁棒性
        time.sleep(1)
        click_and_wait_for_page(
            self._ctrl,
            CLICK_FORMATION,
            BattlePreparationPage.is_current_page,
        )

    def click_sortie(self) -> None:
        """点击右下角「出征」按钮。"""
        self._ctrl.click(*CLICK_SORTIE)
        time.sleep(2.0)

    def go_to_map_page(self) -> None:
        """确保当前在决战地图页（若在准备页则点击左上角返回）。"""
        screen = self._ctrl.screenshot()
        if is_decisive_map_page(screen):
            return
        self._ctrl.click(0.03, 0.06)
        time.sleep(1.0)
        if not is_decisive_map_page(self._ctrl.screenshot()):
            logger.warning("[地图控制器] 无法确认已回到地图页")

    def open_retreat_dialog(self) -> None:
        """点击左上角撤退按钮，打开确认退出 overlay。"""
        self.go_to_map_page()
        self._ctrl.click(*CLICK_RETREAT_BUTTON)
        time.sleep(1.0)
        self.wait_for_overlay(DecisiveOverlay.CONFIRM_EXIT, timeout=5.0)

    def confirm_retreat(self) -> None:
        """在确认退出 overlay 中点击「撤退」。"""
        self._ctrl.click(*CLICK_RETREAT_CONFIRM)
        time.sleep(2.0)

    def confirm_leave(self) -> None:
        """在确认退出 overlay 中点击「暂离」。"""
        self._ctrl.click(*CLICK_LEAVE)
        time.sleep(2.0)

    def confirm_stage_clear(self) -> list[str]:
        """小关通关后确认弹窗并收集掉落舰船。"""
        from autowsgr.image_resources import Templates
        from autowsgr.ui.page import confirm_operation

        confirm_operation(self._ctrl, must_confirm=True, timeout=5.0)
        confirm_operation(self._ctrl, must_confirm=True, timeout=5.0)

        ship_templates = [
            Templates.Symbol.GET_SHIP,
            Templates.Symbol.GET_ITEM,
        ]
        collected: list[str] = []

        while True:
            screen = self._ctrl.screenshot()
            detail = ImageChecker.find_any(
                screen, ship_templates, confidence=0.8,
            )
            if detail is None:
                time.sleep(1.0)
                screen = self._ctrl.screenshot()
                detail = ImageChecker.find_any(
                    screen, ship_templates, confidence=0.8,
                )
                if detail is None:
                    break

            logger.info("[地图控制器] 检测到掉落: '{}'", detail.template_name)
            collected.append(detail.template_name)
            self._ctrl.click(0.953, 0.954)
            time.sleep(0.5)
            confirm_operation(self._ctrl, timeout=1.0)

        if collected:
            logger.info("[地图控制器] 小关通关共收集 {} 个掉落", len(collected))
        return collected

    # ══════════════════════════════════════════════════════════════════════
    # 节点间修理
    # ══════════════════════════════════════════════════════════════════════

    def repair_at_node(self, repair_level: int) -> list[int]:
        """进入出征准备页 → 执行快速修理 → 返回地图页。"""
        logger.info("[地图控制器] 节点间修理 (等级: {})", repair_level)

        self._ctrl.click(*CLICK_SORTIE)
        time.sleep(2.0)

        page = BattlePreparationPage(self._ctrl)
        strategy = RepairStrategy.MODERATE if repair_level <= 1 else RepairStrategy.SEVERE
        repaired = page.apply_repair(strategy)

        if repaired:
            logger.info("[地图控制器] 修理完成, 修理槽位: {}", repaired)
        else:
            logger.debug("[地图控制器] 无需修理")

        page.go_back()
        time.sleep(1.0)
        return repaired

    def change_fleet(
        self,
        fleet_id: int | None,
        ship_names: list[str | None],
    ) -> None:
        """进入出征准备页 → 执行决战专用换船 → 保持在准备页。

        使用 :class:`~autowsgr.ui.decisive.preparation.DecisiveBattlePreparationPage`
        执行换船，原理是 OCR 选船列表直接点击目标，无需输入搜索框。

        Parameters
        ----------
        fleet_id:
            舰队编号 (2–4)；``None`` 代表不指定舰队。1 队不支持更换。
        ship_names:
            目标舰船名列表 (按槽位 0–5)；``None``/``""`` 表示该位留空。
        """
        logger.info("[地图控制器] 进入准备页换船: {} 队 → {}", fleet_id, ship_names)
        page = DecisiveBattlePreparationPage(self._ctrl, self._config, self._ocr)
        page.change_fleet(fleet_id, ship_names)

    # ══════════════════════════════════════════════════════════════════════
    # 等待方法
    # ══════════════════════════════════════════════════════════════════════

    def wait_for_overlay(
        self,
        target: DecisiveOverlay,
        timeout: float = 5.0,
        interval: float = 0.3,
    ) -> np.ndarray:
        """反复截图直到指定 overlay 出现。"""
        sig = get_overlay_signature(target)
        deadline = time.monotonic() + timeout
        while True:
            screen = self._ctrl.screenshot()
            if PixelChecker.check_signature(screen, sig):
                return screen
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"等待 overlay {target.value} 超时 ({timeout}s)"
                )
            time.sleep(interval)
