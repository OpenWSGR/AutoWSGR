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

import re
import time
from typing import TYPE_CHECKING

import cv2
import numpy as np

import autowsgr.ui.decisive.fleet_ocr as _fleet_ocr
from autowsgr.infra.logger import get_logger
from autowsgr.types import DecisivePhase, FleetSelection, ShipDamageState
from autowsgr.ui.battle.preparation import BattlePreparationPage, RepairStrategy
from autowsgr.ui.decisive.overlay import (
    ADVANCE_CARD_POSITIONS,
    CLICK_ADVANCE_CONFIRM,
    CLICK_FLEET_CLOSE,
    CLICK_FLEET_REFRESH,
    CLICK_FORMATION,
    CLICK_LEAVE,
    CLICK_RETREAT_BUTTON,
    CLICK_RETREAT_CONFIRM,
    CLICK_SORTIE,
    DecisiveOverlay,
    detect_decisive_overlay,
    get_overlay_signature,
    is_decisive_map_page,
    is_fleet_acquisition,
)
from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage
from autowsgr.ui.utils.ship_list import recognize_ships_in_list as _recognize_ships
from autowsgr.vision import (
    ImageChecker,
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)
from autowsgr.vision.ocr import OCREngine

from ..page import click_and_wait_for_page


if TYPE_CHECKING:
    from autowsgr.context import GameContext
    from autowsgr.infra import DecisiveConfig


_log = get_logger('ui.decisive')

SKILL_USED = PixelSignature(
    name='skill_used',
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
        ctx: GameContext,
        config: DecisiveConfig,
    ) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._config = config
        self._ocr = ctx.ocr

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
        self,
        screen: np.ndarray | None = None,
    ) -> DecisivePhase | None:
        """单次截图检测当前决战页面状态。

        按以下优先级检测::

            1. dock_full      — 弹窗存活时间极短 (~2s)
            2. use_last_fleet — 进入已有进度章节时弹出
            3. overlay        — 战备舰队 / 前进点（必须先于地图页判断）
            4. 地图页         — 无 overlay 的正常决战地图页

        Returns
        -------
        DecisivePhase | None
            检测到的阶段；过场动画中等未知状态返回 ``None``。
        """
        from autowsgr.image_resources import Templates

        if screen is None:
            screen = self._ctrl.screenshot()

        if ImageChecker.template_exists(
            screen,
            Templates.Build.SHIP_FULL_DEPOT,
            confidence=0.8,
        ):
            _log.warning('[地图控制器] 检测到船坞已满弹窗')
            return DecisivePhase.DOCK_FULL

        if ImageChecker.template_exists(
            screen,
            Templates.Decisive.USE_LAST_FLEET,
            confidence=0.8,
        ):
            _log.info('[地图控制器] 检测到「使用上次舰队」按钮')
            return DecisivePhase.USE_LAST_FLEET

        overlay = detect_decisive_overlay(screen)
        if overlay is not None:
            if overlay == DecisiveOverlay.ADVANCE_CHOICE:
                return DecisivePhase.ADVANCE_CHOICE
            if overlay == DecisiveOverlay.FLEET_ACQUISITION:
                return DecisivePhase.CHOOSE_FLEET

        if is_decisive_map_page(screen):
            # 进图后的首个稳定帧有时会短暂满足“地图页”特征，但战备舰队
            # overlay 会在随后 1-2 帧内出现。这里补一次短延迟复检，只把
            # 连续两次都稳定为地图页的结果视为 PREPARE_COMBAT。
            time.sleep(0.2)
            confirm_screen = self._ctrl.screenshot()

            overlay = detect_decisive_overlay(confirm_screen)
            if overlay is not None:
                if overlay == DecisiveOverlay.ADVANCE_CHOICE:
                    _log.debug('[地图控制器] 地图页复检修正为 overlay: advance_choice')
                    return DecisivePhase.ADVANCE_CHOICE
                if overlay == DecisiveOverlay.FLEET_ACQUISITION:
                    _log.debug('[地图控制器] 地图页复检修正为 overlay: fleet_acquisition')
                    return DecisivePhase.CHOOSE_FLEET

            if is_decisive_map_page(confirm_screen):
                return DecisivePhase.PREPARE_COMBAT

        return None

    # ── 舰船图标颜色检测参数 (HSV, BGR 输入) ──────────────────────
    # 决战地图上的舰船指示器呈橙黄色高亮，是该色段面积最大的连通区域
    _SHIP_HSV_LO = np.array([18, 100, 200], dtype=np.uint8)
    _SHIP_HSV_HI = np.array([32, 180, 255], dtype=np.uint8)
    _SHIP_MIN_AREA = 500  # 真实舰标面积远大于地图杂色 (通常 >2000)

    @staticmethod
    def _locate_ship_icon(bgr: np.ndarray) -> float | None:
        """通过 HSV 颜色分割定位舰船指示器的 **相对** X 中心。

        不依赖任何图像模板，仅利用舰船指示器在决战地图上独特的
        橙黄色高亮面积远大于其它同色碎片这一视觉特征。

        Returns
        -------
        float | None
            舰标中心 X 占图像宽度比例 (0-1)；检测失败返回 ``None``。
        """
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(
            hsv, DecisiveMapController._SHIP_HSV_LO, DecisiveMapController._SHIP_HSV_HI
        )
        # 闭运算连接临近像素
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        n_labels, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
        if n_labels < 2:
            return None

        # 跳过背景 (label 0)，取面积最大的连通区域
        areas = stats[1:, cv2.CC_STAT_AREA]
        best = int(areas.argmax()) + 1
        if stats[best, cv2.CC_STAT_AREA] < DecisiveMapController._SHIP_MIN_AREA:
            return None
        return float(centroids[best][0]) / bgr.shape[1]

    def recognize_node(
        self,
        screen: np.ndarray | None = None,
        fallback: str = 'A',
        chapter: int = 6,
        stage: int = 1,
    ) -> str:
        """OCR 识别当前决战节点字母 (如 ``'A'``, ``'B'``)。

        算法 (无模板依赖):

        1. 轮询截图，通过 **HSV 颜色分割** 定位舰船指示器 X 坐标
           (地图上最大的橙黄色连通区域)。
        2. 以舰标 X 为参考裁剪竖列，使用 OCR 识别节点字母。
        3. OCR 失败时重试 (最多 3 次)，全部失败返回 fallback。

        Parameters
        ----------
        chapter:
            当前章节 (1-6)，用于确定OCR字符集范围。
        stage:
            当前小关 (1-3)，用于确定OCR字符集范围。
        """
        from autowsgr.ops.decisive.config import MapData

        # 根据章节小关确定可能的节点范围 (A到终点)
        end_node = MapData.get_stage_end_node(chapter, stage)
        end_ord = ord(end_node)
        # 生成字符集 A到终点 (如A-F, A-H, A-J)
        allowlist = ''.join(chr(i) for i in range(ord('A'), end_ord + 1))
        _log.debug('[地图控制器] 章节{}小关{}节点范围: A-{}', chapter, stage, end_node)

        _MAX_RETRY = 3
        _ICON_TIMEOUT = 10.0
        _ICON_GAP = 0.15

        for retry in range(_MAX_RETRY + 1):
            # 1. 轮询等待舰船指示器出现
            deadline = time.monotonic() + _ICON_TIMEOUT
            icon_rel_x: float | None = None
            while time.monotonic() < deadline:
                detect_screen = self._ctrl.screenshot()
                # _locate_ship_icon 需要 BGR；screenshot() 返回 RGB
                bgr = cv2.cvtColor(detect_screen, cv2.COLOR_RGB2BGR)
                icon_rel_x = self._locate_ship_icon(bgr)
                if icon_rel_x is not None:
                    break
                time.sleep(_ICON_GAP)

            if icon_rel_x is None:
                raise RuntimeError('决战节点识别失败: 舰船指示器超时未出现')

            _log.debug('[地图控制器] 舰船指示器位置: X={:.3f}', icon_rel_x)

            # 2. 取新截图，按舰标 X 裁剪竖列（聚焦节点字母区域）
            fresh_screen = self._ctrl.screenshot()
            h, w = fresh_screen.shape[:2]

            # 裁剪范围：舰标上方区域（有颜色过滤，范围可以稍宽）
            # 节点字母在舰标上方约0.08-0.20处
            y1 = int(0.35 * h)
            y2 = int(0.55 * h)
            x1 = max(0, int((icon_rel_x - 0.05) * w))
            x2 = min(w, int((icon_rel_x + 0.05) * w))
            node_crop = fresh_screen[y1:y2, x1:x2]

            _log.debug(
                '[地图控制器] 裁剪区域: Y={}-{}, X={}-{}, shape={}', y1, y2, x1, x2, node_crop.shape
            )

            # 图像增强：提升对比度和锐化，突出白色文字
            # 节点字母颜色近似白色 (RGB 213-231)
            gray = cv2.cvtColor(node_crop, cv2.COLOR_RGB2GRAY)

            # 自适应直方图均衡化（CLAHE）增强对比度
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)

            # 锐化滤波
            kernel_sharpen = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
            sharpened = cv2.filter2D(enhanced, -1, kernel_sharpen)

            # 二值化（使用Otsu自动阈值）
            _, binary = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # 检查是否有足够的白色像素
            white_ratio = np.sum(binary > 0) / binary.size
            _log.debug('[地图控制器] 白色像素比例: {:.2%}', white_ratio)

            if white_ratio < 0.005:  # 白色像素太少，可能没裁到字母
                _log.warning('[地图控制器] 白色像素过少，可能未定位到节点字母')
                if retry >= _MAX_RETRY:
                    break
                continue

            # 使用增强后的图像进行OCR
            node_crop_processed = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2RGB)

            # 防御性检查
            if x1 >= x2 or node_crop.size == 0 or (x2 - x1) < 30:
                _log.warning(
                    '[地图控制器] 裁剪区域无效: x1={}, x2={}, width={}, shape={}',
                    x1,
                    x2,
                    x2 - x1,
                    node_crop.shape,
                )
                if retry >= _MAX_RETRY:
                    break
                _log.warning(
                    '[地图控制器] 节点识别失败, 正在重试第 {} 次',
                    retry + 1,
                )
                continue

            # 3. OCR 识别节点字母
            try:
                ocr = OCREngine.create('easyocr', gpu=False)
                # 使用动态字符集（根据章节小关确定范围）
                result = ocr.recognize_single(node_crop_processed, allowlist=allowlist)
                text = result.text.strip().upper()

                _log.debug(
                    '[地图控制器] OCR原始结果: "{}" (置信度={:.2f})', text, result.confidence
                )

                # 提取单个字母（在允许范围内）
                match = re.search(rf'[{allowlist}]', text)
                if match:
                    node_letter = match.group(0)
                    _log.info('[地图控制器] OCR识别节点: {}', node_letter)
                    return node_letter
                else:
                    _log.warning('[地图控制器] OCR未识别到有效节点字母: "{}"', text)
                    if retry >= _MAX_RETRY:
                        break
                    continue

            except Exception as e:
                _log.warning('[地图控制器] OCR识别失败: {}', e)
                if retry >= _MAX_RETRY:
                    break
                time.sleep(0.5)
                continue

        _log.error('[地图控制器] 节点识别失败，返回 fallback: {}', fallback)
        return fallback

    # ══════════════════════════════════════════════════════════════════════
    # 战备舰队获取 overlay
    # ══════════════════════════════════════════════════════════════════════

    def recognize_fleet_options(
        self,
        screen: np.ndarray | None = None,
        fallback_score: int | None = None,
    ) -> tuple[int, dict[str, FleetSelection]]:
        """OCR 识别战备舰队获取界面的可选项。"""
        if screen is None:
            screen = self.wait_for_fleet_overlay_stable()
        return _fleet_ocr.recognize_fleet_options(
            self._ocr,
            screen,
            fallback_score=fallback_score,
        )

    def wait_for_fleet_overlay_stable(
        self,
        screen: np.ndarray | None = None,
        timeout: float = 8.0,
    ) -> np.ndarray:
        """等待战备舰队弹窗稳定后返回截图。

        当上层已通过阶段纠偏进入 ``CHOOSE_FLEET`` 时，当前截图本身就可能是
        首进购买界面，此时不要再次强依赖旧的 overlay 像素签名；直接以当前截图
        为起点做短暂稳定等待即可。
        """
        if screen is None:
            screen = self.wait_for_overlay(DecisiveOverlay.FLEET_ACQUISITION, timeout=timeout)

        stable_deadline = time.monotonic() + 1.0
        last_screen = screen
        while time.monotonic() < stable_deadline:
            time.sleep(0.25)
            last_screen = self._ctrl.screenshot()
        return last_screen

    def detect_last_offer_name(
        self,
        screen: np.ndarray | None = None,
    ) -> str | None:
        """读取战备舰队最后一张卡的名称，用于首节点判定修正。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        return _fleet_ocr.detect_last_offer_name(self._ocr, screen)

    def buy_fleet_option(self, click_position: tuple[float, float]) -> None:
        """点击购买一个舰船/技能卡。"""
        self._ctrl.click(*click_position)
        time.sleep(0.3)

    def refresh_fleet(self) -> None:
        """点击「刷新」按钮，刷新备选舰船。"""
        self._ctrl.click(*CLICK_FLEET_REFRESH)
        time.sleep(1.5)

    def close_fleet_overlay(self) -> bool:
        """关闭战备舰队获取 overlay，并确认已离开该弹窗。"""
        self._ctrl.click(*CLICK_FLEET_CLOSE)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            screen = self._ctrl.screenshot()
            if not is_fleet_acquisition(screen):
                return True
            time.sleep(0.2)
        _log.warning('[地图控制器] 关闭战备舰队弹窗后仍停留在原界面')
        return False

    def is_fleet_overlay_open(self) -> bool:
        """当前是否仍停留在战备舰队获取界面。"""
        return is_fleet_acquisition(self._ctrl.screenshot())

    def check_dock_full(self) -> bool:
        """检查当前界面是否出现船坞已满提示。"""
        from autowsgr.image_resources import Templates

        screen = self._ctrl.screenshot()
        return ImageChecker.template_exists(
            screen,
            Templates.Build.SHIP_FULL_DEPOT,
            confidence=0.8,
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
            screen,
            Templates.Decisive.USE_LAST_FLEET,
            confidence=0.8,
        )
        if match is not None:
            self._ctrl.click(*match.center)
            time.sleep(0.5)

        self._ctrl.click(*CLICK_CONFIRM_POS)
        time.sleep(1.0)

    def use_skill(self) -> list[str]:
        """在地图页使用一次副官技能并返回识别到的舰船。"""
        return _fleet_ocr.use_skill(self._ctrl, self._ocr)

    def check_fleet(
        self,
    ) -> tuple[list[str | None], dict[int, ShipDamageState], set[str]]:
        """恢复进度时在编队页面扫描当前编队及所有可用舰船。

        完整 UI 流程:

        1. 进入编队页 (preparation page)
        2. OCR 识别当前编队成员 + 像素检测血量
        3. 进入选船列表扫描所有可用舰船
        4. 返回地图页

        对齐 legacy ``_check_fleet``: 同时收集编队成员与列表中的舰船。

        Returns
        -------
        tuple[list[str | None], dict[int, ShipDamageState], set[str]]
            ``(fleet, damage, all_ships)``:

            - *fleet*: 当前 6 槽位舰船名 (``None`` 为空)
            - *damage*: 各槽位血量状态
            - *all_ships*: 所有可用舰船名 (含编队成员)
        """
        _log.info('[地图控制器] 扫描当前编队与可用舰船')

        self.enter_formation()
        time.sleep(0.5)  # 等待编队页加载完成
        page = DecisiveBattlePreparationPage(self._ctx, self._config, self._ocr)

        screen = self._ctrl.screenshot()
        fleet = page.detect_fleet(screen)
        damage = page.detect_ship_damage(screen)

        # 进入选船列表：先确认已离开出征准备页，再进行一次识别
        page.click_ship_slot(0)
        deadline = time.monotonic() + 5.0
        ship_list_screen = None
        while time.monotonic() < deadline:
            time.sleep(0.2)
            screen = self._ctrl.screenshot()
            if not BattlePreparationPage.is_current_page(screen):
                ship_list_screen = screen
                break

        if ship_list_screen is None:
            _log.warning('[地图控制器] 点击舰船位后未确认进入选船列表，按当前截图继续识别')
            ship_list_screen = self._ctrl.screenshot()
        else:
            time.sleep(0.3)  # 等待选船列表内容稳定
            ship_list_screen = self._ctrl.screenshot()

        available = _recognize_ships(self._ocr, ship_list_screen)
        _log.debug('[地图控制器] 选船列表识别结果: {}', sorted(available))

        # 编队中的舰船也计入可用集合
        all_ships = set(available)
        for name in fleet:
            if name is not None:
                all_ships.add(name)

        # 返回准备页
        self._ctrl.click(0.05, 0.05)
        time.sleep(1.0)

        # 返回地图页
        page.go_back()
        time.sleep(1.0)

        _log.info(
            '[地图控制器] 编队={}, 可用舰船={}',
            fleet,
            sorted(all_ships),
        )
        return fleet, damage, all_ships

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
        from autowsgr.ui.utils.navigation import NavConfig

        # 调试：检测当前页面状态
        screen = self._ctrl.screenshot()
        from autowsgr.ui.battle.base import PAGE_SIGNATURE
        from autowsgr.ui.decisive.overlay import SIG_MAP_PAGE
        from autowsgr.vision.matcher import PixelChecker

        map_check = PixelChecker.check_signature(screen, SIG_MAP_PAGE)
        prep_check = PixelChecker.check_signature(screen, PAGE_SIGNATURE)
        _log.debug(
            '[地图控制器] 点击编队前 - 地图页: {}, 出征准备页: {}',
            map_check.matched,
            prep_check.matched,
        )

        config = NavConfig(timeout=10.0, interval=0.5, max_retries=3)
        click_and_wait_for_page(
            self._ctrl,
            CLICK_FORMATION,
            BattlePreparationPage.is_current_page,
            config=config,
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
            _log.warning('[地图控制器] 无法确认已回到地图页')

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
        from autowsgr.ui.utils import confirm_operation

        confirm_operation(self._ctrl, must_confirm=True, timeout=5.0)
        confirm_operation(self._ctrl, must_confirm=True, timeout=5.0)

        ship_templates = [
            Templates.Symbol.GET_SHIP,
            Templates.Symbol.GET_ITEM,
        ]
        entry_templates = Templates.Decisive.entry_status_templates()
        collected: list[str] = []
        for _ in range(10):
            # 等待掉落弹窗出现
            if ImageChecker.template_exists(
                self._ctrl.screenshot(),
                ship_templates,
                confidence=0.8,
            ):
                break
            time.sleep(0.25)
        while True:
            screen = self._ctrl.screenshot()
            detail = ImageChecker.find_any(
                screen,
                ship_templates,
                confidence=0.8,
            )
            if detail is None:
                time.sleep(1.0)
                screen = self._ctrl.screenshot()
                detail = ImageChecker.find_any(
                    screen,
                    ship_templates,
                    confidence=0.8,
                )
                if detail is None:
                    break

            _log.info("[地图控制器] 检测到掉落: '{}'", detail.template_name)
            collected.append(detail.template_name)
            self._ctrl.click(0.953, 0.954)
            time.sleep(0.5)
            confirm_operation(self._ctrl, timeout=1.0)

        # 掉落处理结束后，继续等待回到决战入口页，避免奖励弹窗残留导致后续状态识别超时
        settle_deadline = time.monotonic() + 12.0
        reward_ack_pos = (0.5, 0.5)
        while time.monotonic() < settle_deadline:
            screen = self._ctrl.screenshot()
            if ImageChecker.find_any(screen, entry_templates, confidence=0.8) is not None:
                _log.info('[地图控制器] 小关通关结算完成，已回到决战入口页')
                break

            reward_detail = ImageChecker.find_any(screen, ship_templates, confidence=0.8)
            if reward_detail is not None:
                _log.info("[地图控制器] 结算阶段仍有奖励弹窗: '{}'", reward_detail.template_name)
                self._ctrl.click(*reward_ack_pos)
                time.sleep(0.35)
                confirm_operation(self._ctrl, timeout=0.8)
                continue

            if confirm_operation(self._ctrl, timeout=0.8):
                continue

            time.sleep(0.3)
        else:
            _log.warning('[地图控制器] 小关通关后未能确认已回到决战入口页')

        if collected:
            _log.info('[地图控制器] 小关通关共收集 {} 个掉落', len(collected))
        return collected

    # ══════════════════════════════════════════════════════════════════════
    # 节点间修理
    # ══════════════════════════════════════════════════════════════════════

    def repair_at_node(self, repair_level: int) -> list[int]:
        """进入出征准备页 → 执行快速修理 → 返回地图页。"""
        _log.info('[地图控制器] 节点间修理 (等级: {})', repair_level)

        self._ctrl.click(*CLICK_SORTIE)
        time.sleep(2.0)

        page = BattlePreparationPage(self._ctx)
        strategy = RepairStrategy.MODERATE if repair_level <= 1 else RepairStrategy.SEVERE
        repaired = page.apply_repair(strategy)

        if repaired:
            _log.info('[地图控制器] 修理完成, 修理槽位: {}', repaired)
        else:
            _log.debug('[地图控制器] 无需修理')

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
            舰队编号 (2-4)；``None`` 代表不指定舰队。1 队不支持更换。
        ship_names:
            目标舰船名列表 (按槽位 0-5)；``None``/``""`` 表示该位留空。
        """
        _log.info('[地图控制器] 进入准备页换船: {} 队 → {}', fleet_id, ship_names)
        page = DecisiveBattlePreparationPage(self._ctx, self._config, self._ocr)
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
                raise TimeoutError(f'等待 overlay {target.value} 超时 ({timeout}s)')
            time.sleep(interval)
