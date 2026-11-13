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
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

import cv2
import numpy as np

import autowsgr.ui.decisive.fleet_ocr as _fleet_ocr
from autowsgr.infra.logger import get_logger
from autowsgr.types import DecisivePhase, FleetSelection, ShipDamageState
from autowsgr.ui.battle.preparation import BattlePreparationPage, RepairStrategy
from autowsgr.ui.choose_ship_page import ChooseShipPage
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
    get_overlay_template,
    is_decisive_map_page,
    is_fleet_acquisition,
)
from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage
from autowsgr.ui.decisive.ship_list import DecisiveInventoryScanError, DecisiveShipListWalker
from autowsgr.ui.page import click_and_wait_for_page
from autowsgr.ui.utils import wait_for_page
from autowsgr.vision import (
    ROI,
    ImageChecker,
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
    get_api_dll,
)


if TYPE_CHECKING:
    from typing import NoReturn

    from autowsgr.context import GameContext
    from autowsgr.emulator.frame import CapturedFrame
    from autowsgr.infra import DecisiveConfig
    from autowsgr.vision.api_dll import ApiDll
    from autowsgr.vision.image_template import ImageMatchDetail


_log = get_logger('ui.decisive')


SKILL_USED = PixelSignature(
    name='skill_used',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1977, 0.9361, (245, 245, 245), tolerance=30.0),
    ],
)


STAGE_CLEAR_SELECTED = PixelSignature(
    name='stage_clear_selected',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(x / 1280, y / 720, (253, 253, 253), tolerance=65.0)
        for x, y in ((238, 248), (560, 248), (238, 447), (557, 447))
    ],
)


@dataclass(frozen=True, slots=True)
class MapNodeObservation:
    """同一 RGB 帧的字母观察；元数据不可变，图像沿用 CapturedFrame 的只读借用。"""

    frame: CapturedFrame
    icon_x: float | None = None
    crop_bounds: tuple[int, int, int, int] | None = None
    raw_node: str | None = None
    node_label: str | None = None
    locate_seconds: float = 0.0
    native_seconds: float | None = None
    failure: Literal['missing_icon', 'native_error', 'invalid_label'] | None = None
    error: str | None = None

    @property
    def crop(self) -> np.ndarray | None:
        """传给 ApiDll 的原始 RGB 裁剪；不另存一份可能与元数据失配的图像。"""
        if self.crop_bounds is None:
            return None
        left, top, right, bottom = self.crop_bounds
        return self.frame.image[top:bottom, left:right]


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

    def detect_decisive_phase(  # noqa: PLR0911
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

        # 通关卡过场尚无按钮时也不能透过遮罩认成普通地图并点击编队。
        if self._has_stage_clear_choices(screen):
            return None

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

    @staticmethod
    def _node_crop_bounds(screen: np.ndarray, center: float) -> tuple[int, int, int, int]:
        h, w = screen.shape[:2]
        x1 = max(0, int((center - 0.03) * w))
        x2 = min(w, int((center - 0.03 + 0.042) * w))
        return x1, 0, x2, h

    def dll_recognize_map(self, dll: ApiDll, screen: np.ndarray, center: float) -> str:
        """保留原始字符串接口；与结构化观察共用裁剪规则。"""
        left, top, right, bottom = self._node_crop_bounds(screen, center)
        return dll.recognize_map(screen[top:bottom, left:right])

    def observe_node(self, frame: CapturedFrame) -> MapNodeObservation:
        """从已有帧定位、裁剪并调用一次 native，不等待、不重截或判断页面。

        页面门禁、主动采样与去重由调用方负责。这里只解析首字符 A-Z，
        字母是否属于当前小关由会话校验；native 失败保留诊断与分项耗时。
        """
        started = time.perf_counter()
        center = self._locate_ship_icon(cv2.cvtColor(frame.image, cv2.COLOR_RGB2BGR))
        locate_seconds = time.perf_counter() - started
        if center is None:
            return MapNodeObservation(frame, locate_seconds=locate_seconds, failure='missing_icon')
        observation = MapNodeObservation(
            frame,
            icon_x=center,
            crop_bounds=self._node_crop_bounds(frame.image, center),
            locate_seconds=locate_seconds,
        )
        started = time.perf_counter()
        try:
            raw = get_api_dll().recognize_map(observation.crop)
        except Exception as exc:
            _log.warning('[地图控制器] DLL 节点识别异常', exc_info=True)
            return replace(
                observation,
                failure='native_error',
                error=f'{type(exc).__name__}: {exc}',
                native_seconds=time.perf_counter() - started,
            )
        native_seconds = time.perf_counter() - started
        node = raw[:1] if raw else ''
        valid = bool(node and 'A' <= node <= 'Z')
        return replace(
            observation,
            raw_node=raw,
            node_label=node if valid else None,
            native_seconds=native_seconds,
            failure=None if valid else 'invalid_label',
        )

    def recognize_node(
        self,
        frame: CapturedFrame | None = None,
    ) -> str | None:
        """读取已有稳定帧；同帧定位和裁剪，失败作为缺失证据交还调用者。

        页面稳定由上层页面等待负责，这里不等待、不重截，也不把失败转换为节点。
        """
        if frame is None:
            frame = self._ctrl.capture_frame()
        if is_fleet_acquisition(frame.image):
            return 'CHOOSE_FLEET'
        node = self.observe_node(frame).node_label
        if node is not None:
            _log.info('[地图控制器] 识别决战节点: {} (帧 {})', node, frame.sequence)
            return node
        return None

    def wait_for_stable_map_frame(self, timeout: float = 5.0) -> CapturedFrame:
        """复用地图等待：两个不同帧确认地图，有舰标时另外验证位移稳定。"""
        deadline = time.monotonic() + timeout
        previous = None
        previous_center = None
        while time.monotonic() < deadline:
            if self._ctx.stop_event.is_set():
                raise InterruptedError('等待决战地图时收到停止请求')
            frame = self._ctrl.capture_frame()
            if (
                is_decisive_map_page(frame.image)
                and detect_decisive_overlay(frame.image) is None
                and not self._has_stage_clear_choices(frame.image)
            ):
                center = self._locate_ship_icon(cv2.cvtColor(frame.image, cv2.COLOR_RGB2BGR))
                distinct = previous is not None and (
                    frame.sequence != previous.sequence
                    if frame.sequence is not None and previous.sequence is not None
                    else frame.captured_at > previous.captured_at
                )
                if distinct and (
                    (center is None and previous_center is None)
                    or (
                        center is not None
                        and previous_center is not None
                        and abs(center - previous_center) * frame.image.shape[1] <= 2
                    )
                ):
                    return frame
                if previous is None or distinct:
                    previous, previous_center = frame, center
            else:
                previous, previous_center = None, None
            time.sleep(0.05)
        raise TimeoutError('决战地图未取得两个稳定的独立帧')

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
                time.sleep(0.2)  # 等待动画完成
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

        click_confirm_pos: tuple[float, float] = (873 / 960, 500 / 540)

        screen = self._ctrl.screenshot()
        match = ImageChecker.find_template(
            screen,
            Templates.Decisive.USE_LAST_FLEET,
            confidence=0.8,
        )
        if match is not None:
            self._ctrl.click(*match.center)
            time.sleep(0.5)

        self._ctrl.click(*click_confirm_pos)
        time.sleep(1.0)

    def use_skill(self) -> list[str]:
        """在地图页使用一次副官技能并返回识别到的舰船。"""
        return _fleet_ocr.use_skill(self._ctrl, self._ocr)

    def check_fleet(
        self,
    ) -> tuple[list[str | None], dict[int, ShipDamageState], set[str]]:
        """确认完整库存及返回地图后才返回快照；失败不返回部分库存。

        完整 UI 流程:

        1. 进入编队页 (preparation page)
        2. OCR 识别当前编队成员 + 像素检测血量
        3. 进入选船列表扫描所有可用舰船
        4. 返回地图页

        在队成员不出现在候选列表中，因此只有完整列表扫描成功后才合并两者。

        Returns
        -------
        tuple[list[str | None], dict[int, ShipDamageState], set[str]]
            ``(fleet, damage, all_ships)``:

            - *fleet*: 当前 6 槽位舰船名 (``None`` 为空)
            - *damage*: 各槽位血量状态
            - *all_ships*: 所有可用舰船名 (含编队成员)
        """
        _log.info('[地图控制器] 扫描当前编队与可用舰船')
        if self._ctx.stop_event.is_set():
            raise InterruptedError('扫描决战库存前收到停止请求')
        self.enter_formation()
        page = DecisiveBattlePreparationPage(self._ctx, self._config, self._ocr)
        wait_for_page(
            self._ctrl, page.is_current_page, timeout=5.0, source='决战地图', target='出征准备'
        )
        snapshot = page.detect_fleet_snapshot()
        if len(snapshot.names) != 6 or len(snapshot.occupied) != 6:
            raise DecisiveInventoryScanError('决战编队快照不是六槽，拒绝发布库存')
        for _ in range(2):
            if not snapshot.unknown_slots:
                break
            if self._ctx.stop_event.is_set():
                raise InterruptedError('补识别决战舰名前收到停止请求')
            # 只补尚未识别的舰名，不向识别器提供预期编队或舰名候选上下文。
            snapshot = page.fill_missing_fleet_snapshot(snapshot, detail_requirements={})
        if self._ctx.stop_event.is_set():
            raise InterruptedError('补识别决战舰名时收到停止请求')
        if snapshot.unknown_slots:
            raise DecisiveInventoryScanError('决战编队有未识别的占用槽，拒绝发布库存')
        fleet = snapshot.names
        screen = self._ctrl.screenshot()
        damage = page.detect_ship_damage(screen)
        if set(damage) != set(range(6)) or any(
            snapshot.occupied[slot] != (damage[slot] != ShipDamageState.NO_SHIP)
            for slot in range(6)
        ):
            raise DecisiveInventoryScanError('决战编队占用与血量检测不一致，停止库存扫描')

        if self._ctx.stop_event.is_set():
            raise InterruptedError('扫描决战库存时收到停止请求')
        page.click_ship_slot(0)
        wait_for_page(
            self._ctrl,
            ChooseShipPage.is_current_page,
            timeout=5.0,
            source='出征准备',
            target='编队选船',
        )
        available = DecisiveShipListWalker(self._ctx, self._ocr).scan()
        all_ships = available | {name for name in fleet if name is not None}

        self._ctrl.click(0.05, 0.05)
        wait_for_page(
            self._ctrl, page.is_current_page, timeout=5.0, source='编队选船', target='出征准备'
        )
        page.go_back()
        self.wait_for_stable_map_frame()
        if self._ctx.stop_event.is_set():
            raise InterruptedError('决战库存扫描完成前收到停止请求')
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
        # 调试：检测当前页面状态
        from autowsgr.image_resources import Templates
        from autowsgr.ui.utils.navigation import NavConfig

        screen = self._ctrl.screenshot()
        map_check = ImageChecker.template_exists(
            screen, Templates.Decisive.MAP_PAGE, confidence=0.85
        )
        prep_check = ImageChecker.template_exists(
            screen, Templates.Page.BATTLE_PREP, confidence=0.85
        )
        _log.debug(
            '[地图控制器] 点击编队前 - 地图页: {}, 出征准备页: {}',
            map_check,
            prep_check,
        )

        config = NavConfig(timeout=10.0, interval=0.5, max_retries=3)
        click_and_wait_for_page(
            self._ctrl,
            CLICK_FORMATION,
            BattlePreparationPage.is_current_page,
            config=config,
            source='决战地图',
            target='出征准备',
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

    @staticmethod
    def _has_stage_clear_choices(screen: np.ndarray) -> bool:
        """两侧实图标题在各自卡片位置出现，排除奖励或一般确认窗。"""
        from autowsgr.image_resources import Templates

        for template, roi in (
            (Templates.Decisive.STAGE_CLEAR_TITLE, ROI(0.18, 0.32, 0.45, 0.42)),
            (Templates.Decisive.STAGE_CLEAR_ABANDON, ROI(0.55, 0.32, 0.83, 0.42)),
        ):
            if not ImageChecker.template_exists(screen, template, roi=roi, confidence=0.9):
                return False
        return True

    @staticmethod
    def _stage_clear_button(screen: np.ndarray) -> ImageMatchDetail | None:
        """通关卡和实际确认按钮必须同帧可见，过场动画不产生可点击坐标。"""
        from autowsgr.image_resources import Templates

        if not DecisiveMapController._has_stage_clear_choices(screen):
            return None
        return ImageChecker.find_template(
            screen, Templates.Confirm.CONFIRM_4, roi=ROI(0.4, 0.78, 0.6, 0.91), confidence=0.88
        )

    def is_stage_clear(self, screen: np.ndarray) -> bool:
        """独立识别真实通关选择页，不依赖预测节点、OCR 或单个通用确认按钮。"""
        return self._stage_clear_button(screen) is not None

    @staticmethod
    def _has_reward_drop(screen: np.ndarray) -> bool:
        """菜单和已展开的对话框共同确认掉落页，装饰角仅作识别证据。"""
        from autowsgr.image_resources import Templates

        return ImageChecker.find_any(
            screen,
            [Templates.Symbol.GET_SHIP, Templates.Symbol.GET_ITEM],
            roi=ROI(0.0, 0.7, 0.16, 1.0),
            confidence=0.85,
        ) is not None and ImageChecker.template_exists(
            screen,
            Templates.Decisive.REWARD_DIALOG_CORNER,
            roi=ROI(0.78, 0.88, 0.89, 0.98),
            confidence=0.88,
        )

    def _raise_clear_error(self, screen: np.ndarray, reason: str) -> NoReturn:
        """结算失败保存最后实际画面，拒绝盲点或将半途结算当作下一关。"""
        from pathlib import Path

        from autowsgr.infra.logger import save_image

        try:
            path = save_image(
                screen, 'decisive-clear-error', Path(self._ctx.config.log.dir) / 'images'
            )
            _log.error('[地图控制器] {}；现场={}', reason, path)
        except Exception as exc:
            _log.warning('[地图控制器] 通关现场保存失败: {}', exc)
        raise RuntimeError(reason)

    _STAGE_CLEAR_TIMEOUT = 45.0

    def confirm_stage_clear(self, *, resume_rewards: bool = False) -> list[str]:  # noqa: PLR0912
        """按实际控件结算奖励，两个独立帧确认返回入口后才结束小关。

        左侧「确认通关」必须处于选中状态才能确认，避免误选「放弃」。
        掉落展示只在菜单和完整对话框同时可见时推进；过场动画不点击。
        只有调用者明确恢复已确认的结算时，才允许从完整掉落页继续。
        """
        from autowsgr.combat import recognize_ship_drop
        from autowsgr.combat.actions import Coords
        from autowsgr.image_resources import Templates

        if self._ctx.stop_event.is_set():
            raise InterruptedError('决战通关结算时收到停止请求')
        frame = self._ctrl.capture_frame()
        if resume_rewards and not self._has_reward_drop(frame.image):
            self._raise_clear_error(frame.image, '未确认完整掉落页面，拒绝恢复决战通关奖励结算')
        if not resume_rewards and not self.is_stage_clear(frame.image):
            self._raise_clear_error(frame.image, '未确认真实决战通关页面，拒绝结算操作')
        deadline = time.monotonic() + self._STAGE_CLEAR_TIMEOUT
        collected: list[str] = []
        last_frame = None
        last_drop = None
        entry_frames = 0
        confirmed_clear = resume_rewards
        while time.monotonic() < deadline:
            if self._ctx.stop_event.is_set():
                raise InterruptedError('决战通关结算时收到停止请求')
            token = frame.sequence if frame.sequence is not None else frame.captured_at
            if token == last_frame:
                time.sleep(0.05)
                frame = self._ctrl.capture_frame()
                continue
            last_frame = token
            screen = frame.image
            clear_button = self._stage_clear_button(screen)
            if clear_button is not None:
                selected = PixelChecker.check_signature(screen, STAGE_CLEAR_SELECTED).matched
                # 先点击实际左卡，再等待新帧确认选中；绝不确认右侧放弃选项。
                self._ctrl.click(*(clear_button.center if selected else (0.31, 0.48)))
                confirmed_clear = confirmed_clear or selected
                entry_frames = 0
            elif confirmed_clear:
                confirm = ImageChecker.find_any(
                    screen,
                    Templates.Confirm.all(),
                    roi=ROI(0.25, 0.15, 0.8, 0.93),
                    confidence=0.88,
                )
                if confirm is not None:
                    self._ctrl.click(*confirm.center)
                    entry_frames = 0
                    last_drop = None
                elif self._has_reward_drop(screen):
                    try:
                        drop = recognize_ship_drop(screen, ocr=self._ocr)
                        if drop.ship_name and drop.ship_name != last_drop:
                            collected.append(drop.ship_name)
                            last_drop = drop.ship_name
                    except Exception as exc:
                        # 舰名只用于反馈，不让一次 OCR 失败改变已确认的控件操作。
                        _log.warning('[地图控制器] 掉落舰名读取失败: {}', exc)
                    # 斜纹角只证明对话框已展开，不是继续按钮；复用掉落页已验证的继续区域。
                    self._ctrl.click(*Coords.CLICK_RESULT)
                    entry_frames = 0
                elif (
                    ImageChecker.find_any(
                        screen,
                        Templates.Decisive.entry_status_templates(),
                        roi=ROI(0.3, 0.8, 0.78, 1.0),
                        confidence=0.85,
                    )
                    is not None
                ):
                    entry_frames += 1
                    if entry_frames >= 2:
                        _log.info('[地图控制器] 通关结算完成并确认返回入口，掉落={}', collected)
                        return collected
                else:
                    entry_frames = 0
                    last_drop = None
            time.sleep(0.3)
            frame = self._ctrl.capture_frame()
        self._raise_clear_error(frame.image, '决战通关结算超时，未确认返回入口页，保留现场并停止')

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
            舰队编号 (1-4)；``None`` 代表不指定舰队。
            更换 1 队时槽位 0 必须保留目标舰船。
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
        tmpl = get_overlay_template(target)
        deadline = time.monotonic() + timeout
        while True:
            screen = self._ctrl.screenshot()
            if ImageChecker.template_exists(screen, tmpl, confidence=0.85):
                return screen
            if time.monotonic() >= deadline:
                raise TimeoutError(f'等待 overlay {target.value} 超时 ({timeout}s)')
            time.sleep(interval)
