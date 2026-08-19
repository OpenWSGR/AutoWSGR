"""EXP_SETTLEMENT (经验结算子页) 识别的无设备单元测试。

背景 (实机 2026-08-15): 战果页点击后游戏进入经验结算子页, 旧识别器在该页
返回 None → 引擎等待后继状态超时。

判据演进 (两轮实机迭代):
  1. "升级剩余经验" 标签 (exp_settlement_540p): 舰船背景使置信度在
     0.61~0.91 大幅波动, 计数判据也漏检 — 弃用。
  2. MVP 徽章 + 无评级字母: MVP 徽章 (result_page_540p) 在战果/经验
     两页必出现于 6 个舰船行位之一 (左缘 x≈0.057, 实测 0.94+, 不被
     立绘遮挡), 评级字母仅战果页出现 → "MVP 有 + 评级无" 即经验页。
"""

from __future__ import annotations

import numpy as np

from autowsgr.combat.recognizer import CombatRecognizer
from autowsgr.combat.state import CombatPhase
from autowsgr.image_resources import TemplateKey


def _paste(canvas: np.ndarray, tile: np.ndarray, x: int, y: int) -> None:
    h, w = tile.shape[:2]
    canvas[y : y + h, x : x + w] = tile


def _synth_frame(tiles: list[np.ndarray], shape: tuple[int, int] = (540, 960)) -> np.ndarray:
    """把各 *tiles* 粘贴到左缘 (MVP 行位) 的合成帧。*shape* 为 (H, W)。"""
    frame = np.zeros((*shape, 3), dtype=np.uint8)
    y = 100
    for tile in tiles:
        _paste(frame, tile, 40, y)
        y += tile.shape[0] + 60
    return frame


class TestExpSettlementByMvp:
    def test_mvp_only_matches(self):
        """MVP 徽章出现、无评级字母 → 识别为 EXP_SETTLEMENT。"""
        frame = _synth_frame([TemplateKey.RESULT_PAGE.templates[0].image])
        result = CombatRecognizer.identify_current(frame, [CombatPhase.EXP_SETTLEMENT])
        assert result is CombatPhase.EXP_SETTLEMENT

    def test_mvp_with_grade_rejected(self):
        """MVP 徽章与评级字母同时出现 (战果页形态) → 否决键排除, 不命中。"""
        tiles = [
            TemplateKey.RESULT_PAGE.templates[0].image,
            TemplateKey.RESULT_GRADES.templates[0].image,
        ]
        frame = _synth_frame(tiles)
        result = CombatRecognizer.identify_current(frame, [CombatPhase.EXP_SETTLEMENT])
        assert result is None

    def test_empty_frame_no_match(self):
        """既无 MVP 也无评级 → 不命中。"""
        assert (
            CombatRecognizer.identify_current(
                np.zeros((540, 960, 3), dtype=np.uint8), [CombatPhase.EXP_SETTLEMENT]
            )
            is None
        )

    def test_default_signature_unchanged(self):
        """exclude_template_key 默认 None — 其他状态不受否决逻辑影响。"""
        from autowsgr.combat.recognizer import PhaseSignature

        sig = PhaseSignature(template_key=TemplateKey.PROCEED)
        assert sig.exclude_template_key is None

    def test_exp_settlement_signature_config(self):
        """EXP_SETTLEMENT 签名: 主键 MVP 徽章, 否决键评级字母, 置信度 0.85。"""
        sig = CombatRecognizer.get_signature(CombatPhase.EXP_SETTLEMENT)
        assert sig.template_key == TemplateKey.RESULT_PAGE
        assert sig.exclude_template_key == TemplateKey.RESULT_GRADES
        assert sig.confidence == 0.85

    def test_result_signature_uses_grades(self):
        """RESULT 签名用评级字母 (仅战果页出现), 不再用 "点击继续" 文字
        (两页都有且被舰船立绘遮挡致分数波动)。"""
        sig = CombatRecognizer.get_signature(CombatPhase.RESULT)
        assert sig.template_key == TemplateKey.RESULT_GRADES
        assert len(TemplateKey.RESULT_GRADES.templates) == 6
