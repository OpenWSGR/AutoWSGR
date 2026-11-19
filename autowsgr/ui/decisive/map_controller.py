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
from autowsgr.infra import ActionFailedError
from autowsgr.infra.logger import get_logger
from autowsgr.types import DecisivePhase, FleetSelection, ShipDamageState
from autowsgr.ui.battle.constants import CLICK_BACK
from autowsgr.ui.battle.preparation import BattlePreparationPage, RepairStrategy
from autowsgr.ui.decisive.overlay import (
    ADVANCE_CHOICE_ROI,
    ADVANCE_CHOICE_THREE_ROI,
    CLICK_ADVANCE_CONFIRM,
    CLICK_FLEET_CLOSE,
    CLICK_FLEET_REFRESH,
    CLICK_FORMATION,
    CLICK_LEAVE,
    CLICK_RETREAT_BUTTON,
    CLICK_RETREAT_CONFIRM,
    CLICK_SORTIE,
    ENTRY_STATUS_ROI,
    SIG_MAP_PAGE,
    USE_LAST_FLEET_ROI,
    DecisiveOverlay,
    advance_choice_layout,
    detect_decisive_overlay,
    is_decisive_map_page,
    is_fleet_acquisition,
)
from autowsgr.ui.decisive.preparation import DecisiveBattlePreparationPage, read_complete_fleet
from autowsgr.ui.utils.navigation import (
    NavConfig,
    check_stop,
    click_and_wait_for_page,
    wait_for_page,
)
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
    from collections.abc import Callable
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
        *,
        map_checker: Literal['template', 'pixel'] = 'template',
        wait_timeout: float = 5.0,
    ) -> None:
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._config = config
        self._ocr = ctx.ocr
        if map_checker not in {'template', 'pixel'} or wait_timeout <= 0:
            raise ValueError('地图检查器必须为 template 或 pixel，等待时限必须为正数')
        self._map_checker = map_checker
        self._wait_timeout = wait_timeout
        self._branch_count: int | None = None
        self._clear_drops: list[str] | None = None
        self._clear_last_frame: CapturedFrame | None = None
        self._clear_at_entry = False

    def configure_route(self, branch_count: int | None) -> None:
        """由当前路线提供分支数量；不把它当作弹窗已出现的证据。"""
        if branch_count is not None and branch_count not in {0, 1, 2, 3}:
            raise ValueError('决战分支数必须为 0 到 3 或 None')
        self._branch_count = branch_count

    # ══════════════════════════════════════════════════════════════════════
    # 页面状态检测
    # ══════════════════════════════════════════════════════════════════════

    def screenshot(self) -> np.ndarray:
        """获取当前截图。"""
        return self._ctrl.screenshot()

    def detect_overlay(
        self,
        screen: np.ndarray | None = None,
        *,
        advance_choice_roi: ROI | None = None,
    ) -> DecisiveOverlay | None:
        """检测当前地图页上的 overlay 类型。"""
        if screen is None:
            check_stop(self._ctx.stop_event)
            screen = self._ctrl.capture_frame().image
        return detect_decisive_overlay(
            screen,
            branch_count=self._branch_count,
            advance_choice_roi=advance_choice_roi,
        )

    def is_map_page(self, screen: np.ndarray | None = None) -> bool:
        """判断截图是否为决战地图页 (无 overlay 遮挡)。"""
        if screen is None:
            check_stop(self._ctx.stop_event)
            screen = self._ctrl.capture_frame().image
        return bool(
            self._has_map_controls(screen)
            and not self._has_stage_clear_choices(screen)
            and not self._has_reward_drop(screen)
            and self.detect_overlay(screen) is None
            and self._find_use_last(screen) is None
        )

    def _has_map_controls(self, screen: np.ndarray) -> bool:
        """仅识别地图按钮。调用方负责排除遮挡。"""
        if getattr(self, '_map_checker', 'template') == 'pixel':
            return PixelChecker.check_signature(screen, SIG_MAP_PAGE).matched
        return is_decisive_map_page(screen)

    @staticmethod
    def _find_use_last(screen: np.ndarray) -> ImageMatchDetail | None:
        from autowsgr.image_resources import Templates

        return ImageChecker.find_template(
            screen,
            Templates.Decisive.USE_LAST_FLEET,
            roi=USE_LAST_FLEET_ROI,
            confidence=0.8,
        )

    def is_skill_used(self) -> bool:
        screen = self._ctrl.screenshot()
        return PixelChecker.check_signature(screen, SKILL_USED).matched

    def _phase_on_screen(  # noqa: PLR0911
        self,
        screen: np.ndarray,
        *,
        allow_fleet_overlay: bool = True,
        advance_choice_roi: ROI | None = None,
    ) -> DecisivePhase | None:
        """纯分类：所有判断沿用调用者的同一帧，不等待或重新截图。"""
        from autowsgr.image_resources import Templates

        # 通关卡过场尚无按钮时也不能透过遮罩认成普通地图并点击编队。
        if self._has_stage_clear_choices(screen) or self._has_reward_drop(screen):
            return None

        if ImageChecker.template_exists(
            screen,
            Templates.Build.SHIP_FULL_DEPOT,
            confidence=0.8,
        ):
            _log.warning('[地图控制器] 检测到船坞已满弹窗')
            return DecisivePhase.DOCK_FULL

        if self._find_use_last(screen) is not None:
            _log.info('[地图控制器] 检测到「使用上次舰队」按钮')
            return DecisivePhase.USE_LAST_FLEET

        overlay = self.detect_overlay(screen, advance_choice_roi=advance_choice_roi)
        if overlay is not None:
            if overlay == DecisiveOverlay.ADVANCE_CHOICE:
                return DecisivePhase.ADVANCE_CHOICE
            if overlay == DecisiveOverlay.FLEET_ACQUISITION:
                return DecisivePhase.CHOOSE_FLEET if allow_fleet_overlay else None
            return None

        return DecisivePhase.PREPARE_COMBAT if self._has_map_controls(screen) else None

    def detect_decisive_phase(
        self,
        screen: np.ndarray | None = None,
        *,
        allow_fleet_overlay: bool = True,
        advance_choice_roi: ROI | None = None,
    ) -> DecisivePhase | None:
        """有截图时直接判断；未提供截图时等待可识别的入口页面。"""
        check_stop(self._ctx.stop_event)
        if screen is not None:
            return self._phase_on_screen(
                screen,
                allow_fleet_overlay=allow_fleet_overlay,
                advance_choice_roi=advance_choice_roi,
            )
        try:
            return self.wait_for_entry_phase(
                wait_for_fleet=allow_fleet_overlay,
                advance_choice_roi=advance_choice_roi,
                timeout=self._wait_timeout,
            )
        except TimeoutError:
            return None

    def wait_for_entry_phase(
        self,
        *,
        wait_for_use_last: bool = True,
        wait_for_advance: bool = True,
        wait_for_fleet: bool = True,
        advance_choice_roi: ROI | None = None,
        timeout: float = 5.0,
        interval: float = 0.2,
    ) -> DecisivePhase:
        """已消费的浮窗只阻挡地图操作，不能再次作为允许的入口阶段。"""
        allowed = {DecisivePhase.DOCK_FULL, DecisivePhase.PREPARE_COMBAT}
        if wait_for_use_last:
            allowed.add(DecisivePhase.USE_LAST_FLEET)
        if wait_for_advance:
            allowed.add(DecisivePhase.ADVANCE_CHOICE)
        if wait_for_fleet:
            allowed.add(DecisivePhase.CHOOSE_FLEET)
        phase = None

        def ready(image: np.ndarray) -> bool:
            nonlocal phase
            phase = self._phase_on_screen(image, advance_choice_roi=advance_choice_roi)
            return phase in allowed

        wait_for_page(
            self._ctrl,
            ready,
            target='决战入口',
            timeout=timeout,
            interval=interval,
            stop_event=self._ctx.stop_event,
            timeout_error=TimeoutError,
        )
        if phase is None:
            raise TimeoutError('未识别到决战入口')
        return phase

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

    def map_icon_is_stable(self, earlier: CapturedFrame, later: CapturedFrame) -> bool:
        """两个已核实地图帧中，舰标位移不超过两像素或均不可见。"""
        first, second = (
            self._locate_ship_icon(cv2.cvtColor(frame.image, cv2.COLOR_RGB2BGR))
            for frame in (earlier, later)
        )
        if first is None or second is None:
            return first is second
        return abs(second - first) * later.image.shape[1] <= 2

    def wait_for_stable_map_frame(self, timeout: float = 5.0) -> CapturedFrame:
        """复用地图等待：两个不同帧确认地图，有舰标时另外验证位移稳定。"""
        deadline = time.monotonic() + timeout
        previous = None
        while time.monotonic() < deadline:
            check_stop(self._ctx.stop_event)
            frame = self._ctrl.capture_frame()
            if not frame.is_newer_than(previous, allow_static=True):
                time.sleep(0.05)
                continue
            if self.is_map_page(frame.image):
                if previous is not None and self.map_icon_is_stable(previous, frame):
                    check_stop(self._ctx.stop_event)
                    return frame
                previous = frame.snapshot()
            else:
                previous = None
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
        """等待购买浮窗，给卡片文字留出展开时间。"""
        if screen is not None and (
            self._has_stage_clear_choices(screen) or self._has_reward_drop(screen)
        ):
            raise TimeoutError('通关或奖励页面不能作为战备舰队读取')
        if screen is None or not is_fleet_acquisition(screen):
            self.wait_for_overlay(DecisiveOverlay.FLEET_ACQUISITION, timeout=timeout)
        self._ctx.stop_event.wait(0.3)
        check_stop(self._ctx.stop_event)
        screen = self._ctrl.screenshot()
        if not is_fleet_acquisition(screen):
            raise TimeoutError('读取战备舰队时购买浮窗已关闭')
        return screen

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
        check_stop(self._ctx.stop_event)
        self._ctrl.click(*click_position)
        time.sleep(0.3)

    def refresh_fleet(self) -> None:
        """点击「刷新」按钮，刷新备选舰船。"""
        check_stop(self._ctx.stop_event)
        self._ctrl.click(*CLICK_FLEET_REFRESH)
        time.sleep(1.5)

    def close_fleet_overlay(self) -> bool:
        """关闭战备舰队获取 overlay，并确认已离开该弹窗。"""
        try:
            self.wait_for_overlay(DecisiveOverlay.FLEET_ACQUISITION, timeout=self._wait_timeout)
            click_and_wait_for_page(
                self._ctrl,
                CLICK_FLEET_CLOSE,
                lambda image: (
                    self._phase_on_screen(image)
                    in {DecisivePhase.PREPARE_COMBAT, DecisivePhase.ADVANCE_CHOICE}
                ),
                config=NavConfig(timeout=self._wait_timeout, interval=0.3),
                target='决战地图或前进点',
                stop_event=self._ctx.stop_event,
                timeout_error=TimeoutError,
            )
        except TimeoutError:
            _log.warning('[地图控制器] 关闭战备舰队弹窗后未确认返回地图或前进点')
            return False
        return True

    def is_fleet_overlay_open(self) -> bool:
        """当前是否仍停留在战备舰队获取界面。"""
        check_stop(self._ctx.stop_event)
        return is_fleet_acquisition(self._ctrl.capture_frame().image)

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
        screen = wait_for_page(
            self._ctrl,
            lambda image: self._find_use_last(image) is not None,
            target='使用上次舰队',
            timeout=self._wait_timeout,
            interval=0.3,
            stop_event=self._ctx.stop_event,
            timeout_error=TimeoutError,
        )
        match = self._find_use_last(screen)
        if match is None:
            raise TimeoutError('未识别到使用上次舰队按钮，拒绝点击')
        check_stop(self._ctx.stop_event)
        self._ctrl.click(*match.center)
        # 等按钮的点击动画结束，再辨别下方的舰队确认按钮。
        self._ctx.stop_event.wait(0.3)
        following = wait_for_page(
            self._ctrl,
            lambda image: (
                self._find_use_last(image) is not None
                or self._phase_on_screen(image)
                in {
                    DecisivePhase.PREPARE_COMBAT,
                    DecisivePhase.ADVANCE_CHOICE,
                    DecisivePhase.CHOOSE_FLEET,
                }
            ),
            timeout=self._wait_timeout,
            target='上次舰队确认或决战地图',
            interval=0.3,
            stop_event=self._ctx.stop_event,
            timeout_error=TimeoutError,
        )
        if self._find_use_last(following) is not None:
            check_stop(self._ctx.stop_event)
            self._ctrl.click(873 / 960, 500 / 540)

    def use_skill(self) -> list[str]:
        """在地图页使用一次副官技能并返回识别到的舰船。"""
        return _fleet_ocr.use_skill(self._ctx, self._ocr)

    def check_fleet(
        self,
        observe_repairing: Callable[[str], None] | None = None,
    ) -> tuple[list[str | None], dict[int, ShipDamageState], set[str]]:
        """在准备页核对当前编队和伤情，查看选船列表第一页有哪些候补舰，然后返回地图。"""
        self.enter_formation()
        page = DecisiveBattlePreparationPage(self._ctx, self._config, self._ocr)
        fleet, damage = read_complete_fleet(page, self._ctx.stop_event)
        if observe_repairing is not None:
            for slot, name in enumerate(fleet):
                if name and damage[slot] is ShipDamageState.REPAIRING:
                    observe_repairing(name)
        available = page.read_first_screen_candidates()
        check_stop(self._ctx.stop_event)
        page.go_back()
        check_stop(self._ctx.stop_event)
        _log.info('[决战] 当前编队={}，选船首屏候选={}', fleet, sorted(available))
        return fleet, damage, available | {name for name in fleet if name}

    def select_advance_card(self, index: int) -> None:
        """按页面显示的两卡或三卡布局选择前进点并确认。"""

        def layout(image: np.ndarray) -> int | None:
            return advance_choice_layout(image, branch_count=self._branch_count)

        screen = wait_for_page(
            self._ctrl,
            lambda image: layout(image) is not None,
            target='选择前进点',
            timeout=self._wait_timeout,
            interval=0.3,
            stop_event=self._ctx.stop_event,
            timeout_error=TimeoutError,
        )
        count = layout(screen)
        if count not in (2, 3) or not 0 <= index < count:
            raise ValueError('前进点索引超出实际布局')
        left = (ADVANCE_CHOICE_THREE_ROI if count == 3 else ADVANCE_CHOICE_ROI).center[0]
        positions = (left, 0.5, 1.0 - left) if count == 3 else (left, 1.0 - left)
        check_stop(self._ctx.stop_event)
        self._ctrl.click(positions[index], 0.5)
        self._ctx.stop_event.wait(0.5)
        click_and_wait_for_page(
            self._ctrl,
            CLICK_ADVANCE_CONFIRM,
            lambda image: layout(image) is None,
            target='离开前进点选择',
            config=NavConfig(timeout=self._wait_timeout, interval=0.3),
            stop_event=self._ctx.stop_event,
            timeout_error=TimeoutError,
        )

    @staticmethod
    def is_fleet_preparation(screen: np.ndarray) -> bool:
        """沿用出征准备页的识别特征。"""
        return bool(BattlePreparationPage.is_current_page(screen))

    def enter_formation(self) -> None:
        """确认地图上的浮窗已经关闭，再进入出征准备页。"""
        wait_for_page(
            self._ctrl,
            self.is_map_page,
            target='决战地图',
            timeout=self._wait_timeout,
            interval=0.3,
            stop_event=self._ctx.stop_event,
            timeout_error=TimeoutError,
        )
        click_and_wait_for_page(
            self._ctrl,
            CLICK_FORMATION,
            self.is_fleet_preparation,
            target='出征准备',
            config=NavConfig(timeout=self._wait_timeout, interval=0.3),
            stop_event=self._ctx.stop_event,
            timeout_error=TimeoutError,
        )

    def click_sortie(self) -> None:
        """点击右下角「出征」按钮。"""
        self._ctrl.click(*CLICK_SORTIE)
        time.sleep(2.0)

    def go_to_map_page(self) -> None:
        """核实决战地图，或从已识别的准备页返回。"""
        check_stop(self._ctx.stop_event)
        frame = self._ctrl.capture_frame()
        if self.is_map_page(frame.image):
            return
        if not self.is_fleet_preparation(frame.image):
            raise RuntimeError('未确认决战地图或编队页，无法打开撤退菜单')
        click_and_wait_for_page(
            self._ctrl,
            (0.03, 0.06),
            self.is_map_page,
            target='决战地图',
            config=NavConfig(timeout=self._wait_timeout, interval=0.3),
            stop_event=self._ctx.stop_event,
            timeout_error=TimeoutError,
        )

    def open_retreat_dialog(self) -> None:
        self.go_to_map_page()
        self._open_exit_from_map()

    def _open_exit_from_map(self) -> None:
        check_stop(self._ctx.stop_event)
        self._ctrl.click(*CLICK_RETREAT_BUTTON)
        self.wait_for_overlay(DecisiveOverlay.CONFIRM_EXIT)

    def try_leave_interrupted_sortie(self) -> bool:
        """冷启动遇到已打开的决战时，从已核实的准备页或地图暂离到总览。"""
        check_stop(self._ctx.stop_event)
        screen = self._ctrl.capture_frame().image
        if not self.is_map_page(screen):
            if not self.is_fleet_preparation(screen):
                return False
            # 普通准备页有选中的编号舰队标签，决战的同一区域则显示固定标题。
            if BattlePreparationPage.get_selected_fleet(screen) is not None:
                return False
            title = PixelChecker.crop(screen, 113 / 1280, 87 / 720, 307 / 1280, 144 / 720)
            result = self._ocr.recognize_single(title)
            if result.text.strip() != '主力决战舰队' or result.confidence < 0.8:
                raise ActionFailedError('恢复决战', '未能在准备页核实主力决战舰队标题')
            click_and_wait_for_page(
                self._ctrl,
                CLICK_BACK,
                self.is_map_page,
                target='决战地图',
                config=NavConfig(timeout=self._wait_timeout, interval=0.3),
                stop_event=self._ctx.stop_event,
                timeout_error=TimeoutError,
            )
        self._open_exit_from_map()
        self.confirm_leave()
        return True

    def _confirm_exit(self, coord: tuple[float, float]) -> None:
        from autowsgr.ui.decisive.battle_page import DecisiveBattlePage

        self.wait_for_overlay(DecisiveOverlay.CONFIRM_EXIT, timeout=self._wait_timeout)
        click_and_wait_for_page(
            self._ctrl,
            coord,
            DecisiveBattlePage.is_current_page,
            target='决战总览',
            config=NavConfig(timeout=self._wait_timeout, interval=0.3),
            stop_event=self._ctx.stop_event,
            timeout_error=TimeoutError,
        )

    def confirm_retreat(self) -> None:
        self._confirm_exit(CLICK_RETREAT_CONFIRM)

    def confirm_leave(self) -> None:
        self._confirm_exit(CLICK_LEAVE)

    def leave_to_overview(self) -> None:
        """在地图或已打开的退出菜单暂离。每个按钮只点一次，直到新画面确认总览。"""
        from autowsgr.ui.decisive.battle_page import DecisiveBattlePage

        stop = self._ctx.stop_event
        deadline = time.monotonic() + self._wait_timeout
        menu_requested = leave_requested = False
        previous = None
        while True:
            check_stop(stop)
            frame = self._ctrl.capture_frame()
            check_stop(stop)
            if frame.is_newer_than(previous, allow_static=False):
                screen = frame.image
                if DecisiveBattlePage.is_current_page(screen):
                    return
                if (
                    not leave_requested
                    and self.detect_overlay(screen) is DecisiveOverlay.CONFIRM_EXIT
                ):
                    check_stop(stop)
                    self._ctrl.click(*CLICK_LEAVE)
                    leave_requested = True
                    # 暂离已经提交。即使加载超过常规导航时限，也只等总览的新帧。
                    deadline = time.monotonic() + 2 * self._wait_timeout
                elif not (menu_requested or leave_requested) and self.is_map_page(screen):
                    check_stop(stop)
                    self._ctrl.click(*CLICK_RETREAT_BUTTON)
                    menu_requested = True
                    deadline = time.monotonic() + self._wait_timeout
                previous = frame.snapshot()
            if time.monotonic() >= deadline:
                raise ActionFailedError('暂离决战', '未能确认已返回决战总览，保留当前页面')
            stop.wait(0.3)

    def continue_combat_result(self, screen: np.ndarray) -> None:
        """只在仍可识别的战果或经验页推进，避免点击决战地图。"""
        from autowsgr.combat.actions import Coords
        from autowsgr.combat.recognizer import CombatRecognizer
        from autowsgr.combat.state import CombatPhase

        if CombatRecognizer.identify_current(
            screen, [CombatPhase.RESULT, CombatPhase.EXP_SETTLEMENT]
        ):
            check_stop(self._ctx.stop_event)
            self._ctrl.click(*Coords.CLICK_RESULT)

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

    def reset_settlement(self) -> None:
        """新一轮或成功结算后，清理本次通关的凭据与掉落记录。"""
        self._clear_drops = None
        self._clear_last_frame = None
        self._clear_at_entry = False

    def _advance_reward(self, screen: np.ndarray, collected: list[str]) -> bool:
        """处理已确认结算中的一个页面，返回是否观察到了入口。"""
        from autowsgr.combat import recognize_ship_drop
        from autowsgr.combat.actions import Coords
        from autowsgr.image_resources import Templates

        if self._has_reward_drop(screen):
            try:
                drop = recognize_ship_drop(screen, ocr=self._ocr)
                if drop.ship_name and drop.ship_name not in collected:
                    collected.append(drop.ship_name)
            except Exception as exc:
                _log.warning('[地图控制器] 掉落舰名读取失败: {}', exc)
            check_stop(self._ctx.stop_event)
            self._ctrl.click(*Coords.CLICK_RESULT)
            return False

        confirm = ImageChecker.find_any(
            screen,
            Templates.Confirm.all(),
            roi=ROI(0.25, 0.15, 0.8, 0.93),
            confidence=0.88,
        )
        if confirm is not None:
            check_stop(self._ctx.stop_event)
            self._ctrl.click(*confirm.center)
            return False
        return (
            ImageChecker.find_any(
                screen,
                Templates.Decisive.entry_status_templates(),
                roi=ENTRY_STATUS_ROI,
                confidence=0.85,
            )
            is not None
        )

    def confirm_stage_clear(self, *, resume_rewards: bool = False) -> list[str]:
        """按通关控件推进结算，连续两次观察到裸露的入口页才结束。"""
        check_stop(self._ctx.stop_event)
        frame = self._ctrl.capture_frame()
        if self._clear_drops is None:
            if resume_rewards:
                if not self._has_reward_drop(frame.image):
                    self._raise_clear_error(
                        frame.image, '未确认完整掉落页面，拒绝恢复决战通关奖励结算'
                    )
                self._clear_drops = []
            elif not self.is_stage_clear(frame.image):
                self._raise_clear_error(frame.image, '未确认真实决战通关页面，拒绝结算操作')

        deadline = time.monotonic() + self._STAGE_CLEAR_TIMEOUT
        while time.monotonic() < deadline:
            check_stop(self._ctx.stop_event)
            if frame.is_newer_than(self._clear_last_frame, allow_static=self._clear_at_entry):
                self._clear_last_frame = frame.snapshot()
                clear_button = self._stage_clear_button(frame.image)
                if clear_button is not None:
                    selected = PixelChecker.check_signature(
                        frame.image, STAGE_CLEAR_SELECTED
                    ).matched
                    check_stop(self._ctx.stop_event)
                    self._ctrl.click(*(clear_button.center if selected else (0.31, 0.48)))
                    if selected and self._clear_drops is None:
                        self._clear_drops = []
                    self._clear_at_entry = False
                elif self._clear_drops is not None:
                    at_entry = self._advance_reward(frame.image, self._clear_drops)
                    if at_entry and self._clear_at_entry:
                        check_stop(self._ctx.stop_event)
                        collected = self._clear_drops
                        self.reset_settlement()
                        _log.info('[地图控制器] 通关结算完成并确认返回入口，掉落={}', collected)
                        return collected
                    self._clear_at_entry = at_entry
            time.sleep(0.3)
            check_stop(self._ctx.stop_event)
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
            _log.info('[地图控制器] 快修完成，编队位置（从 1 开始）：{}', [i + 1 for i in repaired])
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
            更换第 1 舰队时，旗舰位置必须指定舰船。
        ship_names:
            按编队顺序列出舰名，第一项为旗舰。``None``/``""`` 表示该位置留空。
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
        return wait_for_page(
            self._ctrl,
            lambda screen: self.detect_overlay(screen) == target,
            target=target.value,
            timeout=timeout,
            interval=interval,
            stop_event=self._ctx.stop_event,
            timeout_error=TimeoutError,
        )
