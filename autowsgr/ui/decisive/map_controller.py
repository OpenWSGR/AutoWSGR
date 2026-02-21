"""决战地图页控制器。

封装所有与决战地图页面的直接交互，包括：

- **页面状态识别**: overlay 检测、地图页确认、节点 DLL 识别
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

from autowsgr.ui.decisive.overlay import (
    ADVANCE_CARD_POSITIONS,
    CLICK_ADVANCE_CONFIRM,
    CLICK_FLEET_CLOSE,
    CLICK_FLEET_REFRESH,
    CLICK_LEAVE,
    CLICK_RETREAT_BUTTON,
    CLICK_RETREAT_CONFIRM,
    CLICK_SORTIE,
    COST_AREA,
    FLEET_CARD_CLICK_Y,
    FLEET_CARD_X_POSITIONS,
    RESOURCE_AREA,
    SHIP_NAME_X_RANGES,
    SHIP_NAME_Y_RANGE,
    DecisiveOverlay,
    detect_decisive_overlay,
    get_overlay_signature,
    is_advance_choice,
    is_decisive_map_page,
)
from autowsgr.ui.battle.preparation import BattlePreparationPage, RepairStrategy
from autowsgr.vision import ApiDll, PixelChecker, ROI, get_api_dll, OCREngine
from autowsgr.types import FleetSelection
from autowsgr.infra import DecisiveConfig
from collections.abc import Callable
from autowsgr.emulator import AndroidController


class DecisiveMapController:
    """决战地图页控制器。

    将所有地图页 UI 交互（截图检测、点击操作、OCR 识别）
    封装为语义化方法，供 :class:`DecisiveController` 调用。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    config:
        决战配置。
    ocr:
        OCR 引擎 (可选，影响舰队选择识别)。
    dll:
        API DLL (可选，影响节点识别)。
    image_matcher:
        图像匹配函数 (可选，影响船图标定位)。
        签名: ``(screen: ndarray) -> str | None``。
    """

    def __init__(
        self,
        ctrl: AndroidController,
        config: DecisiveConfig,
        *,
        ocr: OCREngine | None = None,
        dll: ApiDll | None = None,
        image_matcher: Callable[[np.ndarray], str | None] | None = None,
    ) -> None:
        self._ctrl = ctrl
        self._config = config
        self._ocr = ocr
        self._dll = dll
        self._image_matcher = image_matcher

    # ══════════════════════════════════════════════════════════════════════
    # 页面状态识别
    # ══════════════════════════════════════════════════════════════════════

    def screenshot(self) -> np.ndarray:
        """获取当前截图。"""
        return self._ctrl.screenshot()

    def detect_overlay(self, screen: np.ndarray | None = None) -> DecisiveOverlay | None:
        """检测当前地图页上的 overlay 类型。

        Returns
        -------
        DecisiveOverlay | None
            命中的 overlay 类型；无 overlay 返回 ``None``。
        """
        if screen is None:
            screen = self._ctrl.screenshot()
        return detect_decisive_overlay(screen)

    def is_map_page(self, screen: np.ndarray | None = None) -> bool:
        """判断截图是否为决战地图页 (无 overlay 遮挡)。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        return is_decisive_map_page(screen)

    def is_advance_choice(self, screen: np.ndarray | None = None) -> bool:
        """判断截图是否为选择前进点 overlay。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        return is_advance_choice(screen)

    def recognize_node(self, screen: np.ndarray | None = None, fallback: str = "A") -> str:
        """DLL 识别当前决战节点字母 (如 'A', 'B')。

        Parameters
        ----------
        screen:
            截图；为 ``None`` 时自动截取。
        fallback:
            识别失败时的回退值。

        Returns
        -------
        str
            节点字母；识别失败时返回 *fallback*。
        """
        if screen is None:
            screen = self._ctrl.screenshot()

        dll = self._dll
        if dll is None:
            try:
                dll = get_api_dll()
            except FileNotFoundError:
                logger.warning("[地图控制器] 无 DLL, 跳过节点识别")
                return fallback

        # 使用 image_matcher 查找舰船图标位置 (辅助定位列区域)
        if self._image_matcher is not None:
            match_result = self._image_matcher(screen)
            if match_result is not None:
                logger.debug("[地图控制器] 图标匹配结果: {}", match_result)

        # 裁切整列图像用于 DLL 识别
        h, w = screen.shape[:2]
        x_center = 0.47
        col_width = 0.042
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
        self,
        screen: np.ndarray | None = None,
    ) -> tuple[int, dict[str, FleetSelection]]:
        """OCR 识别战备舰队获取界面的可选项。

        Returns
        -------
        tuple[int, dict[str, FleetSelection]]
            ``(score, selections)`` — 当前可用分数与可购买项字典。
            无 OCR 引擎时返回 ``(0, {})``。
        """
        if self._ocr is None:
            logger.warning("[地图控制器] 无 OCR 引擎, 跳过舰队选择")
            return (0, {})

        if screen is None:
            screen = self._ctrl.screenshot()

        # 1. 识别可用分数
        res_roi = ROI(
            x1=RESOURCE_AREA[0][0], y1=RESOURCE_AREA[1][1],
            x2=RESOURCE_AREA[1][0], y2=RESOURCE_AREA[0][1],
        )
        score_img = res_roi.crop(screen)
        score_val = self._ocr.recognize_number(score_img)
        score = score_val if score_val is not None else 0
        if score_val is not None:
            logger.debug("[地图控制器] 可用分数: {}", score_val)
        else:
            logger.warning("[地图控制器] 分数 OCR 失败")

        # 2. 识别费用整行
        cost_roi = ROI(
            x1=COST_AREA[0][0], y1=COST_AREA[1][1],
            x2=COST_AREA[1][0], y2=COST_AREA[0][1],
        )
        cost_img = cost_roi.crop(screen)
        cost_results = self._ocr.recognize(cost_img, allowlist="0123456789x")

        costs: list[int] = []
        for r in cost_results:
            text = r.text.strip().lstrip("xX")
            try:
                costs.append(int(text))
            except (ValueError, TypeError):
                logger.debug("[地图控制器] 费用解析跳过: '{}'", r.text)
        logger.debug("[地图控制器] 识别到 {} 项费用: {}", len(costs), costs)

        # 3. 对可负担的卡识别舰船名
        ship_names = self._config.level1 + self._config.level2 + [
            "长跑训练", "肌肉记忆", "黑科技",
        ]
        selections: dict[str, FleetSelection] = {}
        for i, cost in enumerate(costs):
            if cost > score:
                continue
            if i >= len(SHIP_NAME_X_RANGES):
                break

            x_range = SHIP_NAME_X_RANGES[i]
            y_range = SHIP_NAME_Y_RANGE
            name_roi = ROI(x1=x_range[0], y1=y_range[0], x2=x_range[1], y2=y_range[1])
            name_img = name_roi.crop(screen)

            name = self._ocr.recognize_ship_name(name_img, ship_names)
            if name is None:
                raw = self._ocr.recognize_single(name_img)
                name = raw.text.strip() if raw.text.strip() else f"未识别_{i}"
                logger.debug("[地图控制器] 舰船名模糊匹配失败, 原文: '{}'", name)

            click_x = FLEET_CARD_X_POSITIONS[i] if i < len(FLEET_CARD_X_POSITIONS) else 0.5
            click_y = FLEET_CARD_CLICK_Y

            selections[name] = FleetSelection(
                name=name,
                cost=cost,
                click_position=(click_x, click_y),
            )

        logger.info("[地图控制器] 舰队选项: {}", {k: v.cost for k, v in selections.items()})
        return (score, selections)

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

    # ══════════════════════════════════════════════════════════════════════
    # 选择前进点 overlay
    # ══════════════════════════════════════════════════════════════════════

    def select_advance_card(self, index: int) -> None:
        """选择前进点卡片并确认。

        Parameters
        ----------
        index:
            卡片索引 (0-based)。
        """
        if index < len(ADVANCE_CARD_POSITIONS):
            self._ctrl.click(*ADVANCE_CARD_POSITIONS[index])
            time.sleep(0.5)
        self._ctrl.click(*CLICK_ADVANCE_CONFIRM)
        time.sleep(1.5)

    # ══════════════════════════════════════════════════════════════════════
    # 地图操作
    # ══════════════════════════════════════════════════════════════════════

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

    def confirm_stage_clear(self, click_count: int = 3) -> None:
        """小关通关后确认奖励弹窗。

        Parameters
        ----------
        click_count:
            连续点击次数，用于确认多层弹窗。
        """
        for _ in range(click_count):
            self._ctrl.click(0.5, 0.5)
            time.sleep(1.5)

    # ══════════════════════════════════════════════════════════════════════
    # 节点间修理
    # ══════════════════════════════════════════════════════════════════════

    def repair_at_node(self, repair_level: int) -> list[int]:
        """在节点间执行修理操作。

        进入出征准备页 → 执行快速修理 → 返回地图页。

        Parameters
        ----------
        repair_level:
            修理等级 (1=中破修, 2=大破修)。

        Returns
        -------
        list[int]
            被修理的槽位列表。
        """
        logger.info("[地图控制器] 节点间修理 (等级: {})", repair_level)

        # 点击出征按钮进入准备页
        self._ctrl.click(*CLICK_SORTIE)
        time.sleep(2.0)

        # 创建准备页控制器并执行修理
        page = BattlePreparationPage(self._ctrl)
        strategy = RepairStrategy.MODERATE if repair_level <= 1 else RepairStrategy.SEVERE
        repaired = page.apply_repair(strategy)

        if repaired:
            logger.info("[地图控制器] 修理完成, 修理槽位: {}", repaired)
        else:
            logger.debug("[地图控制器] 无需修理")

        # 返回地图页
        page.go_back()
        time.sleep(1.0)

        return repaired

    # ══════════════════════════════════════════════════════════════════════
    # 等待方法
    # ══════════════════════════════════════════════════════════════════════

    def poll_for_map_or_overlay(
        self,
        timeout: float = 15.0,
        interval: float = 0.5,
    ) -> np.ndarray:
        """轮询截图，直到出现地图页或任意 overlay。

        Returns
        -------
        np.ndarray
            命中时的截图。超时时返回最后一张截图。
        """
        deadline = time.monotonic() + timeout
        while True:
            screen = self._ctrl.screenshot()
            if is_decisive_map_page(screen) or detect_decisive_overlay(screen) is not None:
                return screen
            if time.monotonic() >= deadline:
                logger.warning("[地图控制器] 等待地图页/overlay 超时")
                return screen
            time.sleep(interval)

    def wait_for_overlay(
        self,
        target: DecisiveOverlay,
        timeout: float = 5.0,
        interval: float = 0.3,
    ) -> np.ndarray:
        """反复截图直到指定 overlay 出现。

        Raises
        ------
        TimeoutError
            超时未出现。
        """
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
