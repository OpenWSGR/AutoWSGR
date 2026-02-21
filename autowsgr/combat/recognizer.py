"""战斗状态视觉识别器。

负责从截图中识别当前战斗状态。与旧代码 ``FightInfo.update_state()`` 中的
图像匹配逻辑对应，但将识别职责独立抽取。

每个 ``CombatPhase`` 关联一组视觉签名（模板图片和置信度阈值），
识别器在候选状态集合中依次尝试匹配，返回首个匹配成功的状态。

.. note::

    本模块定义了每个状态的 **默认超时** 和 **匹配后延时**。
    实际超时可被状态转移图中的覆盖值修改。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
from loguru import logger

from autowsgr.combat.state import CombatPhase
from autowsgr.emulator.controller import AndroidController
from autowsgr.image_resources import TemplateKey
from autowsgr.vision import ImageChecker


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
    """

    template_key: TemplateKey | None
    default_timeout: float = 15.0
    confidence: float = 0.8
    after_match_delay: float = 0.0


PHASE_SIGNATURES: dict[CombatPhase, PhaseSignature] = {
    CombatPhase.PROCEED: PhaseSignature(
        template_key=TemplateKey.PROCEED,
        default_timeout=7.5,
        after_match_delay=0.5,
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
        template_key=TemplateKey.FORMATION,
        default_timeout=22.5,
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
    CombatPhase.BATTLE_PAGE: PhaseSignature(
        template_key=TemplateKey.END_BATTLE_PAGE,
        default_timeout=7.5,
    ),
    CombatPhase.EXERCISE_PAGE: PhaseSignature(
        template_key=TemplateKey.END_EXERCISE_PAGE,
        default_timeout=7.5,
    ),
}

# 战役模式下某些状态的超时覆盖
BATTLE_MODE_OVERRIDES: dict[CombatPhase, dict[str, float]] = {
    CombatPhase.SPOT_ENEMY_SUCCESS: {"default_timeout": 15.0},
    CombatPhase.FORMATION: {"default_timeout": 15.0, "confidence": 0.8},
    CombatPhase.FIGHT_PERIOD: {"default_timeout": 7.5},
    CombatPhase.RESULT: {"default_timeout": 75.0},
}


# ═══════════════════════════════════════════════════════════════════════════════
# 结果识别模板
# ═══════════════════════════════════════════════════════════════════════════════

RESULT_GRADE_KEYS: dict[str, TemplateKey] = {
    "SS": TemplateKey.GRADE_SS,
    "S": TemplateKey.GRADE_S,
    "A": TemplateKey.GRADE_A,
    "B": TemplateKey.GRADE_B,
    "C": TemplateKey.GRADE_C,
    "D": TemplateKey.GRADE_D,
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
    mode_overrides:
        模式特定的签名覆盖（如战役模式下的超时调整）。
    """

    def __init__(
        self,
        device: AndroidController,
        mode_overrides: dict[CombatPhase, dict[str, float]] | None = None,
    ) -> None:
        self._device = device
        self._overrides = mode_overrides or {}

    @staticmethod
    def _match_template(
        screen: np.ndarray, key: TemplateKey, confidence: float,
    ) -> bool:
        """检查截图是否包含模板键对应的图像。"""
        return ImageChecker.find_any(
            screen, key.templates, confidence=confidence,
        ) is not None

    def get_signature(self, phase: CombatPhase) -> PhaseSignature:
        """获取状态的视觉签名（含模式覆盖）。"""
        base = PHASE_SIGNATURES.get(phase)
        if base is None:
            return PhaseSignature(template_key=None, default_timeout=10.0)

        overrides = self._overrides.get(phase)
        if overrides is None:
            return base

        # 应用覆盖
        return PhaseSignature(
            template_key=base.template_key,
            default_timeout=overrides.get("default_timeout", base.default_timeout),
            confidence=overrides.get("confidence", base.confidence),
            after_match_delay=overrides.get("after_match_delay", base.after_match_delay),
        )

    def wait_for_phase(
        self,
        candidates: list[tuple[CombatPhase, float | None]],
        *,
        poll_action: Callable[[], None] | None = None,
    ) -> CombatPhase:
        """等待候选状态之一出现。

        轮询截图并匹配，直到匹配到其中一个候选状态或超时。

        Parameters
        ----------
        candidates:
            ``(状态, 超时覆盖)`` 列表。超时为 ``None`` 使用签名默认值。
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
        # 计算总超时
        max_timeout = 0.0
        phase_sigs: list[tuple[CombatPhase, PhaseSignature, float]] = []
        for phase, timeout_override in candidates:
            sig = self.get_signature(phase)
            timeout = timeout_override if timeout_override is not None else sig.default_timeout
            max_timeout = max(max_timeout, timeout)
            phase_sigs.append((phase, sig, timeout))

        # 全局置信度取所有候选的最小值
        min_confidence = min(
            (sig.confidence for _, sig, _ in phase_sigs),
            default=0.8,
        )

        deadline = time.time() + max_timeout
        poll_interval = 0.3

        logger.debug(
            "等待状态: {} (超时 {:.1f}s)",
            [p.name for p, _, _ in phase_sigs],
            max_timeout,
        )

        while time.time() < deadline:
            if poll_action is not None:
                poll_action()

            screen = self._device.screenshot()

            for phase, sig, _ in phase_sigs:
                if sig.template_key is None:
                    continue
                if self._match_template(screen, sig.template_key, min_confidence):
                    # 匹配后延时
                    if sig.after_match_delay > 0:
                        time.sleep(sig.after_match_delay)
                    logger.info("匹配到状态: {}", phase.name)
                    return phase

            time.sleep(poll_interval)

        # 超时
        phase_names = [p.name for p, _, _ in phase_sigs]
        raise CombatRecognitionTimeout(
            f"等待状态超时 ({max_timeout:.1f}s): {phase_names}"
        )

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
            if sig.template_key is None:
                continue
            if self._match_template(screen, sig.template_key, sig.confidence):
                return phase
        return None


class CombatRecognitionTimeout(Exception):
    """战斗状态识别超时。"""

    pass
