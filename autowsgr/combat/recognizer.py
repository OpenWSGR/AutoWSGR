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

import numpy as np
from loguru import logger

from autowsgr.combat.state import CombatPhase
from autowsgr.emulator.controller import AndroidController


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

    template_key: str
    default_timeout: float = 15.0
    confidence: float = 0.8
    after_match_delay: float = 0.0

    # template_key 命名规则:
    #   与 autowsgr/combat/image_resources.py 中 PHASE_TEMPLATE_MAP 的键一一对应。
    #   单模板:   "formation"、"proceed"、"night_battle" …
    #   多模板任一: "get_ship_or_item"
    #   战果评级: "grade_ss"、"grade_s" …


# 各状态对应的视觉签名
# template_key 命名规则:
#   与 autowsgr/combat/image_resources.py 中 PHASE_TEMPLATE_MAP 的键一一对应。
#   单模板: "formation"、"proceed" 等
#   多模板任一匹配: "get_ship_or_item" 等

PHASE_SIGNATURES: dict[CombatPhase, PhaseSignature] = {
    CombatPhase.PROCEED: PhaseSignature(
        template_key="proceed",
        default_timeout=7.5,
        after_match_delay=0.5,
    ),
    CombatPhase.FIGHT_CONDITION: PhaseSignature(
        template_key="fight_condition",
        default_timeout=22.5,
    ),
    CombatPhase.SPOT_ENEMY_SUCCESS: PhaseSignature(
        template_key="spot_enemy",
        default_timeout=22.5,
    ),
    CombatPhase.FORMATION: PhaseSignature(
        template_key="formation",
        default_timeout=22.5,
    ),
    CombatPhase.MISSILE_ANIMATION: PhaseSignature(
        template_key="missile_animation",
        default_timeout=3.0,
    ),
    CombatPhase.FIGHT_PERIOD: PhaseSignature(
        template_key="fight_period",
        default_timeout=30.0,
    ),
    CombatPhase.NIGHT_PROMPT: PhaseSignature(
        template_key="night_battle",
        default_timeout=150.0,
        after_match_delay=1.75,
    ),
    CombatPhase.RESULT: PhaseSignature(
        template_key="result",
        default_timeout=90.0,
    ),
    CombatPhase.GET_SHIP: PhaseSignature(
        template_key="get_ship_or_item",
        default_timeout=5.0,
        after_match_delay=1.0,
    ),
    CombatPhase.FLAGSHIP_SEVERE_DAMAGE: PhaseSignature(
        template_key="flagship_damage",
        default_timeout=7.5,
    ),
    CombatPhase.MAP_PAGE: PhaseSignature(
        template_key="end_map_page",
        default_timeout=7.5,
    ),
    CombatPhase.BATTLE_PAGE: PhaseSignature(
        template_key="end_battle_page",
        default_timeout=7.5,
    ),
    CombatPhase.EXERCISE_PAGE: PhaseSignature(
        template_key="end_exercise_page",
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

# 战果等级对应的模板键（均在 PHASE_TEMPLATE_MAP 中注册）
RESULT_GRADE_TEMPLATES: dict[str, str] = {
    "SS": "grade_ss",
    "S": "grade_s",
    "A": "grade_a",
    "B": "grade_b",
    "C": "grade_c",
    "D": "grade_d",
}


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
    image_matcher:
        图像匹配回调函数。签名:
        ``(screen: ndarray, template_key: str, confidence: float) → bool``
    mode_overrides:
        模式特定的签名覆盖（如战役模式下的超时调整）。
    """

    def __init__(
        self,
        device: AndroidController,
        image_matcher: ImageMatcherFunc,
        mode_overrides: dict[CombatPhase, dict[str, float]] | None = None,
    ) -> None:
        self._device = device
        self._match = image_matcher
        self._overrides = mode_overrides or {}

    def get_signature(self, phase: CombatPhase) -> PhaseSignature:
        """获取状态的视觉签名（含模式覆盖）。"""
        base = PHASE_SIGNATURES.get(phase)
        if base is None:
            return PhaseSignature(template_key="", default_timeout=10.0)

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
        before_match: BeforeMatchCallback | None = None,
    ) -> CombatPhase:
        """等待候选状态之一出现。

        轮询截图并匹配，直到匹配到其中一个候选状态或超时。

        Parameters
        ----------
        candidates:
            ``(状态, 超时覆盖)`` 列表。超时为 ``None`` 使用签名默认值。
        before_match:
            每轮匹配前的回调（用于点击加速等操作）。

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
            if before_match is not None:
                before_match()

            screen = self._device.screenshot()

            for phase, sig, _ in phase_sigs:
                if not sig.template_key:
                    continue
                if self._match(screen, sig.template_key, min_confidence):
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
            if not sig.template_key:
                continue
            if self._match(screen, sig.template_key, sig.confidence):
                return phase
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 类型别名
# ═══════════════════════════════════════════════════════════════════════════════

from typing import Callable, Protocol

ImageMatcherFunc = Callable[[np.ndarray, str, float], bool]
"""图像匹配函数签名: ``(screen, template_key, confidence) → matched``"""

BeforeMatchCallback = Callable[[], None]
"""每轮匹配前的回调函数。"""


class CombatRecognitionTimeout(Exception):
    """战斗状态识别超时。"""

    pass
