"""战斗状态视觉识别器。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.image_resources import TemplateKey
from autowsgr.infra import get_logger
from autowsgr.vision import (
    CompositePixelSignature,
    ImageChecker,
    MatchStrategy,
    PixelChecker,
    PixelRule,
    PixelSignature,
)

from .state import CombatPhase


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np

    from autowsgr.context import GameContext


_log = get_logger('combat.recognition')


# ═══════════════════════════════════════════════════════════════════════════════
# 状态视觉签名
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class PhaseSignature:
    """一个战斗状态的视觉识别签名。

    Attributes
    ----------
    template_key:
        图像模板标识键。在实际使用中，由图像加载器将此键映射到
        具体的模板图片 (numpy 数组)。
    default_timeout:
        等待此状态出现的默认超时时间（秒）。
    confidence:
        模板匹配的最低置信度。
    after_match_delay:
        匹配到此状态后的额外等待时间（秒），用于等待 UI 动画完成。
    pixel_signature:
        像素特征签名，当 ``template_key`` 为 ``None`` 时使用像素匹配。
    """

    template_key: TemplateKey | None
    default_timeout: float = 15.0
    confidence: float = 0.8
    after_match_delay: float = 0.0
    pixel_signature: PixelSignature | CompositePixelSignature | None = None


def _get_event_map_signatures() -> CompositePixelSignature:
    """延迟导入活动地图页面的组合像素签名（基础页面 OR 浮层）。"""
    from autowsgr.ui.event.event_page import BASE_PAGE_SIGNATURE, OVERLAY_SIGNATURE

    return CompositePixelSignature.any_of(
        'event_map_page_composite',
        BASE_PAGE_SIGNATURE,
        OVERLAY_SIGNATURE,
    )


_CHOOSE_FORMATION_SIGNATURE = PixelSignature(
    name='choose_formation',
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.9413, 0.2011, (227, 227, 227), tolerance=30.0),
        PixelRule.of(0.9375, 0.3644, (227, 227, 227), tolerance=30.0),
        PixelRule.of(0.9569, 0.5278, (227, 227, 227), tolerance=30.0),
        PixelRule.of(0.5050, 0.5678, (24, 101, 181), tolerance=30.0),
        PixelRule.of(0.5019, 0.9478, (26, 103, 183), tolerance=30.0),
        PixelRule.of(0.8531, 0.9367, (32, 134, 219), tolerance=30.0),
    ],
)


PHASE_SIGNATURES: dict[CombatPhase, PhaseSignature] = {
    CombatPhase.PROCEED: PhaseSignature(
        template_key=TemplateKey.PROCEED,
        default_timeout=7.5,
        after_match_delay=0.5,
    ),
    CombatPhase.START_FIGHT: PhaseSignature(
        template_key=None,  # 过渡态，不直接用模板匹配
        default_timeout=3.0,
    ),
    CombatPhase.DOCK_FULL: PhaseSignature(
        template_key=TemplateKey.DOCK_FULL,
        default_timeout=3.0,
    ),
    CombatPhase.FIGHT_CONDITION: PhaseSignature(
        template_key=TemplateKey.FIGHT_CONDITION,
        default_timeout=22.5,
    ),
    CombatPhase.SPOT_ENEMY_SUCCESS: PhaseSignature(
        template_key=TemplateKey.SPOT_ENEMY,
        default_timeout=22.5,
    ),
    CombatPhase.FORMATION: PhaseSignature(
        template_key=None,
        default_timeout=22.5,
        pixel_signature=_CHOOSE_FORMATION_SIGNATURE,
    ),
    CombatPhase.MISSILE_ANIMATION: PhaseSignature(
        template_key=TemplateKey.MISSILE_ANIMATION,
        default_timeout=3.0,
    ),
    CombatPhase.FIGHT_PERIOD: PhaseSignature(
        template_key=TemplateKey.FIGHT_PERIOD,
        default_timeout=30.0,
    ),
    CombatPhase.NIGHT_PROMPT: PhaseSignature(
        template_key=TemplateKey.NIGHT_BATTLE,
        default_timeout=150.0,
        after_match_delay=1.75,
    ),
    CombatPhase.RESULT: PhaseSignature(
        template_key=TemplateKey.RESULT,
        default_timeout=90.0,
    ),
    CombatPhase.GET_SHIP: PhaseSignature(
        template_key=TemplateKey.GET_SHIP_OR_ITEM,
        default_timeout=5.0,
        after_match_delay=1.0,
    ),
    CombatPhase.FLAGSHIP_SEVERE_DAMAGE: PhaseSignature(
        template_key=TemplateKey.FLAGSHIP_DAMAGE,
        default_timeout=7.5,
    ),
    CombatPhase.MAP_PAGE: PhaseSignature(
        template_key=TemplateKey.END_MAP_PAGE,
        default_timeout=7.5,
    ),
    CombatPhase.EXERCISE_PAGE: PhaseSignature(
        template_key=TemplateKey.END_EXERCISE_PAGE,
        default_timeout=7.5,
    ),
    CombatPhase.EVENT_MAP_PAGE: PhaseSignature(
        template_key=None,
        default_timeout=7.5,
        pixel_signature=_get_event_map_signatures(),
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# 结果识别模板
# ═══════════════════════════════════════════════════════════════════════════════

RESULT_GRADE_KEYS: dict[str, TemplateKey] = {
    'SS': TemplateKey.GRADE_SS,
    'S': TemplateKey.GRADE_S,
    'A': TemplateKey.GRADE_A,
    'B': TemplateKey.GRADE_B,
    'C': TemplateKey.GRADE_C,
    'D': TemplateKey.GRADE_D,
}

# 向后兼容别名
RESULT_GRADE_TEMPLATES = {k: v.value for k, v in RESULT_GRADE_KEYS.items()}


# ═══════════════════════════════════════════════════════════════════════════════
# 识别器
# ═══════════════════════════════════════════════════════════════════════════════


class CombatRecognizer:
    """战斗状态识别器。

    封装从截图到状态识别的完整流程，包括：
    - 候选状态筛选
    - 多模板并行匹配
    - 超时控制
    - 匹配后延时

    Parameters
    ----------
    device:
        设备控制器（用于截图）。
    """

    def __init__(self, ctx: GameContext) -> None:
        self._ctx = ctx
        self._device = ctx.ctrl

    @staticmethod
    def _match_template(
        screen: np.ndarray,
        key: TemplateKey,
        confidence: float,
    ) -> bool:
        """检查截图是否包含模板键对应的图像。"""
        return (
            ImageChecker.find_any(
                screen,
                key.templates,
                confidence=confidence,
            )
            is not None
        )

    @staticmethod
    def _match_pixel(
        screen: np.ndarray,
        sig: PixelSignature | CompositePixelSignature,
    ) -> bool:
        """检查截图是否匹配像素特征签名（支持单签名或组合签名）。"""
        return PixelChecker.check_signature(screen, sig).matched

    def _match_phase(
        self,
        screen: np.ndarray,
        sig: PhaseSignature,
    ) -> bool:
        """检查截图是否匹配指定状态的视觉签名（模板或像素）。"""
        if sig.template_key is not None:
            return self._match_template(screen, sig.template_key, sig.confidence)
        if sig.pixel_signature is not None:
            return self._match_pixel(screen, sig.pixel_signature)
        return False

    @staticmethod
    def get_signature(phase: CombatPhase) -> PhaseSignature:
        """获取状态的视觉签名。"""
        sig = PHASE_SIGNATURES.get(phase)
        if sig is None:
            return PhaseSignature(template_key=None, default_timeout=10.0)
        return sig

    def wait_for_phase(
        self,
        candidates: list[CombatPhase],
        *,
        poll_action: Callable[[np.ndarray], None] | None = None,
    ) -> CombatPhase:
        """等待候选状态之一出现。

        轮询截图并匹配，直到匹配到其中一个候选状态或超时。

        Parameters
        ----------
        candidates:
            候选状态列表。
        poll_action:
            每轮匹配前执行的动作（如点击加速、节点追踪等）。

        Returns
        -------
        CombatPhase
            匹配到的状态。

        Raises
        ------
        CombatRecognitionTimeout
            所有候选状态均未在超时内匹配到。
        """
        # 构建签名列表并计算总超时
        max_timeout = 0.0
        phase_sigs: list[tuple[CombatPhase, PhaseSignature]] = []
        for phase in candidates:
            sig = self.get_signature(phase)
            max_timeout = max(max_timeout, sig.default_timeout)
            phase_sigs.append((phase, sig))

        deadline = time.time() + max_timeout

        _log.debug(
            '[Combat] 等待状态: {} (超时 {:.1f}s)',
            [p.name for p, _ in phase_sigs],
            max_timeout,
        )

        while time.time() < deadline:
            # 检查停止信号
            if self._ctx.stop_event.is_set():
                raise CombatStopRequested('任务被用户停止')

            screen = self._device.screenshot()
            if poll_action is not None:
                poll_action(screen)

            for phase, sig in phase_sigs:
                if sig.template_key is None and sig.pixel_signature is None:
                    continue
                if self._match_phase(screen, sig):
                    if sig.after_match_delay > 0:
                        time.sleep(sig.after_match_delay)
                    _log.debug('[Combat] 匹配到状态: {}', phase.name)
                    return phase
        # 超时
        phase_names = [p.name for p, _ in phase_sigs]
        raise CombatRecognitionTimeout(f'等待状态超时 ({max_timeout:.1f}s): {phase_names}')

    def identify_current(
        self,
        screen: np.ndarray,
        candidates: list[CombatPhase],
    ) -> CombatPhase | None:
        """在给定截图上识别当前状态（不等待）。

        Parameters
        ----------
        screen:
            截图数组。
        candidates:
            候选状态列表。

        Returns
        -------
        CombatPhase | None
            匹配到的状态，或 ``None``。
        """
        for phase in candidates:
            sig = self.get_signature(phase)
            if sig.template_key is None and sig.pixel_signature is None:
                continue
            if self._match_phase(screen, sig):
                return phase
        return None


class CombatRecognitionTimeout(Exception):
    """战斗状态识别超时。"""


class CombatStopRequested(Exception):
    """外部请求停止战斗。"""
