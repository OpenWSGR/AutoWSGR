"""战斗状态视觉识别器。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.image_resources import TemplateKey
from autowsgr.infra import get_logger
from autowsgr.vision import (
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
    from autowsgr.vision import ImageTemplate


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
    image_templates:
        图像模板列表 (不归属 :class:`TemplateKey` 体系的自定义模板, 如活动标题图)。
        ``template_key`` 与 ``pixel_signature`` 均为 ``None`` 时使用, ``find_any``
        命中任一即匹配。
    exclude_template_key:
        否决键: ``template_key`` 匹配成功后, 若此键对应的模板**也**命中则
        整体判为不匹配。用于"共有元素 + 独有元素"区分结构相似页:
        如 MVP 徽章在战果页/经验页都出现 (稳定 0.94+), 而评级字母仅
        战果页出现 — "MVP 有 + 评级无" 即经验结算页。
    """

    template_key: TemplateKey | None
    default_timeout: float = 15.0
    confidence: float = 0.8
    after_match_delay: float = 0.0
    pixel_signature: PixelSignature | None = None
    image_templates: list[ImageTemplate] | None = None
    exclude_template_key: TemplateKey | None = None


def _get_event_map_title_templates() -> list[ImageTemplate]:
    """延迟导入活动地图页面标题图模板。

    用于识别活动战斗结束回港后的活动地图页 (CombatPhase.EVENT_MAP_PAGE)。
    """
    from autowsgr.ui.event.event_page import _get_event_title_templates

    return _get_event_title_templates()


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
    # 战果页判据用评级字母 (SS~D): 仅战果页出现 (经验页/出征准备页实测
    # 噪声 ≤0.48)。旧判据 result_540p ("点击继续") 两页都有且被舰船立绘
    # 遮挡致分数波动 (0.75~0.87), 无法区分还会误判。
    CombatPhase.RESULT: PhaseSignature(
        template_key=TemplateKey.RESULT_GRADES,
        default_timeout=90.0,
        confidence=0.85,
    ),
    # 经验页判据: MVP 徽章 + 无评级字母。MVP 徽章在战果/经验两页必出现
    # 于 6 个舰船行位之一 (左缘 x≈0.057, 实测 0.94+, 不受立绘遮挡),
    # 评级字母仅在战果页出现 → 否决键排除战果页。旧判据 "升级剩余经验"
    # 标签会被舰船背景干扰 (置信度波动 0.61~0.91), 弃用。
    CombatPhase.EXP_SETTLEMENT: PhaseSignature(
        template_key=TemplateKey.RESULT_PAGE,
        exclude_template_key=TemplateKey.RESULT_GRADES,
        default_timeout=7.5,
        confidence=0.85,
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
        image_templates=_get_event_map_title_templates(),
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
        sig: PixelSignature,
    ) -> bool:
        """检查截图是否匹配像素特征签名。"""
        return PixelChecker.check_signature(screen, sig).matched

    @staticmethod
    def _match_phase(
        screen: np.ndarray,
        sig: PhaseSignature,
    ) -> bool:
        """检查截图是否匹配指定状态的视觉签名（模板、图像列表或像素）。"""
        if sig.template_key is not None:
            if not CombatRecognizer._match_template(screen, sig.template_key, sig.confidence):
                return False
            # 否决键: 主键命中但排除键也命中 → 整体不匹配
            if sig.exclude_template_key is None:
                return True
            return not CombatRecognizer._match_template(
                screen, sig.exclude_template_key, sig.confidence
            )
        if sig.image_templates is not None:
            return (
                ImageChecker.find_any(screen, sig.image_templates, confidence=sig.confidence)
                is not None
            )
        if sig.pixel_signature is not None:
            return CombatRecognizer._match_pixel(screen, sig.pixel_signature)
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
        CombatRecognitionTimeoutError
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
                raise CombatStopRequestedError('任务被用户停止')

            screen = self._device.screenshot()
            if poll_action is not None:
                poll_action(screen)

            for phase, sig in phase_sigs:
                if (
                    sig.template_key is None
                    and sig.pixel_signature is None
                    and sig.image_templates is None
                ):
                    continue
                if self._match_phase(screen, sig):
                    if sig.after_match_delay > 0:
                        time.sleep(sig.after_match_delay)
                    _log.debug('[Combat] 匹配到状态: {}', phase.name)
                    return phase
        # 超时
        phase_names = [p.name for p, _ in phase_sigs]
        raise CombatRecognitionTimeoutError(f'等待状态超时 ({max_timeout:.1f}s): {phase_names}')

    @staticmethod
    def identify_current(
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
            sig = CombatRecognizer.get_signature(phase)
            if (
                sig.template_key is None
                and sig.pixel_signature is None
                and sig.image_templates is None
            ):
                continue
            if CombatRecognizer._match_phase(screen, sig):
                return phase
        return None


class CombatRecognitionTimeoutError(Exception):
    """战斗状态识别超时。"""


class CombatStopRequestedError(Exception):
    """外部请求停止战斗。"""
