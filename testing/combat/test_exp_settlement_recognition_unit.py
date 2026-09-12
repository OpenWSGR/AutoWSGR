"""EXP_SETTLEMENT (经验结算子页) 识别的无设备单元测试。

背景 (实机 2026-08-15): 战果页点击后游戏进入经验结算子页, 旧识别器在该页
返回 None → 引擎等待后继状态超时。

当前判据: 固定顶部 ROI OCR 必须识别出 ``数字 + Exp``。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.combat import handlers as handlers_module
from autowsgr.combat.handlers import PhaseHandlersMixin
from autowsgr.combat.recognizer import CombatRecognizer
from autowsgr.combat.state import CombatPhase
from autowsgr.image_resources import TemplateKey
from autowsgr.vision import OCRResult


class TestExpSettlementByOcr:
    def test_default_signature_unchanged(self):
        """exclude_template_key 默认 None — 其他状态不受否决逻辑影响。"""
        from autowsgr.combat.recognizer import PhaseSignature

        sig = PhaseSignature(template_key=TemplateKey.PROCEED)
        assert sig.exclude_template_key is None

    def test_exp_settlement_signature_uses_runtime_ocr(self):
        """EXP_SETTLEMENT 没有全屏模板，运行时走 ROI OCR。"""
        sig = CombatRecognizer.get_signature(CombatPhase.EXP_SETTLEMENT)
        assert sig.template_key is None
        assert sig.exclude_template_key is None
        assert sig.confidence == 0.85
        assert sig.after_match_delay == 1.0

    def test_static_identify_does_not_use_exp_template(self):
        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        assert CombatRecognizer.identify_current(frame, [CombatPhase.EXP_SETTLEMENT]) is None

    def test_result_signature_uses_grades(self):
        """RESULT 签名用评级字母 (仅战果页出现), 不再用 "点击继续" 文字
        (两页都有且被舰船立绘遮挡致分数波动)。"""
        sig = CombatRecognizer.get_signature(CombatPhase.RESULT)
        assert sig.template_key == TemplateKey.RESULT_GRADES
        assert len(TemplateKey.RESULT_GRADES.templates) == 6

    def test_runtime_exp_ocr_accepts_digits_and_exp(self):
        class FakeOCR:
            def recognize(self, _image, allowlist=''):
                assert '0123456789' in allowlist
                return [OCRResult(text='200', confidence=0.99, bbox=(0, 0, 20, 20)), OCRResult(
                    text='Exp', confidence=0.99, bbox=(25, 0, 50, 20)
                )]

        recognizer = CombatRecognizer(SimpleNamespace(ctrl=None, ocr=FakeOCR()))
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        assert recognizer.identify_current_runtime(frame, [CombatPhase.EXP_SETTLEMENT]) == (
            CombatPhase.EXP_SETTLEMENT
        )

    def test_incremental_exp_tokens_accumulate_until_stable(self, monkeypatch):
        class FakeOCR:
            def __init__(self):
                self.calls = 0

            def recognize(self, _image, allowlist=''):
                self.calls += 1
                text = ('200E', 'X', 'P', '200E', 'X', 'P', '200E', 'X', 'P')[
                    self.calls - 1
                ]
                return [OCRResult(text=text, confidence=0.99, bbox=(0, 0, 20, 20))]

        fake_ocr = FakeOCR()
        recognizer = CombatRecognizer(SimpleNamespace(ctrl=None, ocr=fake_ocr))
        host = SimpleNamespace(_device=MagicMock(), _recognizer=recognizer)
        host._device.screenshot.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
        now = [0.0]
        monkeypatch.setattr(handlers_module.time, 'monotonic', lambda: now[0])
        monkeypatch.setattr(
            handlers_module.time,
            'sleep',
            lambda delay: now.__setitem__(0, now[0] + delay),
        )

        PhaseHandlersMixin._wait_for_exp_settlement(host)

        assert fake_ocr.calls == 9
        assert now[0] == 7.0

    def test_runtime_exp_ocr_rejects_missing_exp_suffix(self):
        class FakeOCR:
            def recognize(self, _image, allowlist=''):
                return [OCRResult(text='200', confidence=0.99, bbox=(0, 0, 20, 20))]

        recognizer = CombatRecognizer(SimpleNamespace(ctrl=None, ocr=FakeOCR()))
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        assert recognizer.identify_current_runtime(frame, [CombatPhase.EXP_SETTLEMENT]) is None

    def test_runtime_exp_ocr_rejects_other_characters(self):
        class FakeOCR:
            def recognize(self, _image, allowlist=''):
                return [OCRResult(text='200经验', confidence=0.99, bbox=(0, 0, 40, 20))]

        recognizer = CombatRecognizer(SimpleNamespace(ctrl=None, ocr=FakeOCR()))
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        assert recognizer.recognize_exp_settlement_text(frame) is None

    def test_incremental_exp_timeout_raises_error(self, monkeypatch):
        class FakeOCR:
            def recognize(self, _image, allowlist=''):
                return [OCRResult(text='200E', confidence=0.99, bbox=(0, 0, 40, 20))]

        recognizer = CombatRecognizer(SimpleNamespace(ctrl=None, ocr=FakeOCR()))
        host = SimpleNamespace(_device=MagicMock(), _recognizer=recognizer)
        host._device.screenshot.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
        now = [0.0]
        monkeypatch.setattr(handlers_module.time, 'monotonic', lambda: now[0])
        monkeypatch.setattr(
            handlers_module.time,
            'sleep',
            lambda delay: now.__setitem__(0, now[0] + delay),
        )

        with pytest.raises(TimeoutError, match='未能识别到经验结算页'):
            PhaseHandlersMixin._wait_for_exp_settlement(host)
