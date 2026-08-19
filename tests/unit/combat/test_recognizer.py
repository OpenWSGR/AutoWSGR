"""测试 autowsgr.combat.recognizer。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autowsgr.combat.recognizer import (
    RESULT_GRADE_KEYS,
    RESULT_GRADE_TEMPLATES,
    CombatRecognitionTimeoutError,
    CombatRecognizer,
    CombatStopRequestedError,
    PhaseSignature,
)
from autowsgr.combat.state import CombatPhase
from autowsgr.image_resources import TemplateKey


class TestPhaseSignature:
    """PhaseSignature 构造与冻结测试。"""

    def test_construction_with_defaults(self) -> None:
        sig = PhaseSignature(template_key=TemplateKey.PROCEED)
        assert sig.template_key is TemplateKey.PROCEED
        assert sig.default_timeout == 15.0
        assert sig.confidence == 0.8
        assert sig.after_match_delay == 0.0
        assert sig.pixel_signature is None

    def test_frozen_instance(self) -> None:
        sig = PhaseSignature(template_key=TemplateKey.PROCEED)
        with pytest.raises(FrozenInstanceError):
            sig.confidence = 0.5  # ty: ignore[invalid-assignment]


class TestGetSignature:
    """CombatRecognizer.get_signature 测试。"""

    def test_known_phase(self) -> None:
        sig = CombatRecognizer.get_signature(CombatPhase.PROCEED)
        assert sig.template_key is TemplateKey.PROCEED

    def test_unknown_phase_returns_default(self) -> None:
        with patch(
            'autowsgr.combat.recognizer.PHASE_SIGNATURES',
            {},
        ):
            sig = CombatRecognizer.get_signature(CombatPhase.PROCEED)
        assert sig.template_key is None
        assert sig.default_timeout == 10.0
        assert sig.confidence == 0.8
        assert sig.after_match_delay == 0.0
        assert sig.pixel_signature is None


class TestMatchTemplate:
    """CombatRecognizer._match_template 测试。"""

    def test_find_any_returns_detail(self) -> None:
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        detail = MagicMock()
        with patch(
            'autowsgr.combat.recognizer.ImageChecker.find_any',
            return_value=detail,
        ) as mock_find:
            result = CombatRecognizer._match_template(
                screen,
                TemplateKey.PROCEED,
                0.8,
            )
        assert result is True
        mock_find.assert_called_once_with(
            screen,
            TemplateKey.PROCEED.templates,
            confidence=0.8,
        )

    def test_find_any_returns_none(self) -> None:
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        with patch(
            'autowsgr.combat.recognizer.ImageChecker.find_any',
            return_value=None,
        ) as mock_find:
            result = CombatRecognizer._match_template(
                screen,
                TemplateKey.PROCEED,
                0.8,
            )
        assert result is False
        mock_find.assert_called_once_with(
            screen,
            TemplateKey.PROCEED.templates,
            confidence=0.8,
        )


class TestMatchPixel:
    """CombatRecognizer._match_pixel 测试。"""

    def test_check_signature_matched_true(self) -> None:
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        pixel_sig = MagicMock()
        with patch(
            'autowsgr.combat.recognizer.PixelChecker.check_signature',
            return_value=SimpleNamespace(matched=True),
        ) as mock_check:
            result = CombatRecognizer._match_pixel(screen, pixel_sig)
        assert result is True
        mock_check.assert_called_once_with(screen, pixel_sig)

    def test_check_signature_matched_false(self) -> None:
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        pixel_sig = MagicMock()
        with patch(
            'autowsgr.combat.recognizer.PixelChecker.check_signature',
            return_value=SimpleNamespace(matched=False),
        ) as mock_check:
            result = CombatRecognizer._match_pixel(screen, pixel_sig)
        assert result is False
        mock_check.assert_called_once_with(screen, pixel_sig)


class TestMatchPhase:
    """CombatRecognizer._match_phase 分支测试。"""

    def test_template_branch(self) -> None:
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        sig = PhaseSignature(template_key=TemplateKey.PROCEED)
        with (
            patch.object(
                CombatRecognizer,
                '_match_template',
                return_value=True,
            ) as mock_template,
            patch.object(
                CombatRecognizer,
                '_match_pixel',
                return_value=False,
            ) as mock_pixel,
        ):
            result = CombatRecognizer._match_phase(screen, sig)
        assert result is True
        mock_template.assert_called_once_with(
            screen,
            TemplateKey.PROCEED,
            0.8,
        )
        mock_pixel.assert_not_called()

    def test_pixel_branch(self) -> None:
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        pixel_sig = MagicMock()
        sig = PhaseSignature(template_key=None, pixel_signature=pixel_sig)
        with (
            patch.object(
                CombatRecognizer,
                '_match_template',
                return_value=True,
            ) as mock_template,
            patch.object(
                CombatRecognizer,
                '_match_pixel',
                return_value=True,
            ) as mock_pixel,
        ):
            result = CombatRecognizer._match_phase(screen, sig)
        assert result is True
        mock_template.assert_not_called()
        mock_pixel.assert_called_once_with(screen, pixel_sig)

    def test_both_none_returns_false(self) -> None:
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        sig = PhaseSignature(template_key=None, pixel_signature=None)
        with (
            patch.object(
                CombatRecognizer,
                '_match_template',
                return_value=True,
            ) as mock_template,
            patch.object(
                CombatRecognizer,
                '_match_pixel',
                return_value=True,
            ) as mock_pixel,
        ):
            result = CombatRecognizer._match_phase(screen, sig)
        assert result is False
        mock_template.assert_not_called()
        mock_pixel.assert_not_called()


class TestIdentifyCurrent:
    """CombatRecognizer.identify_current 测试。"""

    def test_returns_first_match(self) -> None:
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        sig1 = PhaseSignature(template_key=TemplateKey.PROCEED)
        sig2 = PhaseSignature(template_key=TemplateKey.RESULT)
        with (
            patch.object(
                CombatRecognizer,
                'get_signature',
                side_effect=[sig1, sig2],
            ),
            patch.object(
                CombatRecognizer,
                '_match_phase',
                side_effect=[False, True],
            ) as mock_match,
        ):
            result = CombatRecognizer.identify_current(
                screen,
                [CombatPhase.PROCEED, CombatPhase.RESULT],
            )
        assert result is CombatPhase.RESULT
        assert mock_match.call_count == 2

    def test_returns_none_when_no_match(self) -> None:
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        sig = PhaseSignature(template_key=TemplateKey.PROCEED)
        with (
            patch.object(
                CombatRecognizer,
                'get_signature',
                return_value=sig,
            ),
            patch.object(
                CombatRecognizer,
                '_match_phase',
                return_value=False,
            ) as mock_match,
        ):
            result = CombatRecognizer.identify_current(
                screen,
                [CombatPhase.PROCEED],
            )
        assert result is None
        assert mock_match.call_count == 1

    def test_skips_empty_signature(self) -> None:
        screen = np.zeros((10, 10, 3), dtype=np.uint8)
        empty_sig = PhaseSignature(template_key=None, pixel_signature=None)
        normal_sig = PhaseSignature(template_key=TemplateKey.PROCEED)
        with (
            patch.object(
                CombatRecognizer,
                'get_signature',
                side_effect=[empty_sig, normal_sig],
            ),
            patch.object(
                CombatRecognizer,
                '_match_phase',
                return_value=False,
            ) as mock_match,
        ):
            result = CombatRecognizer.identify_current(
                screen,
                [CombatPhase.START_FIGHT, CombatPhase.PROCEED],
            )
        assert result is None
        assert mock_match.call_count == 1
        mock_match.assert_called_once_with(screen, normal_sig)


class TestExceptions:
    """异常类基本测试。"""

    def test_timeout_error_subclass(self) -> None:
        assert issubclass(CombatRecognitionTimeoutError, Exception)

    def test_stop_requested_error_subclass(self) -> None:
        assert issubclass(CombatStopRequestedError, Exception)


class TestResultGradeKeys:
    """RESULT_GRADE_KEYS 测试。"""

    def test_keys(self) -> None:
        assert set(RESULT_GRADE_KEYS.keys()) == {'SS', 'S', 'A', 'B', 'C', 'D'}


class TestResultGradeTemplates:
    """RESULT_GRADE_TEMPLATES 测试。"""

    def test_values_are_strings(self) -> None:
        assert all(isinstance(v, str) for v in RESULT_GRADE_TEMPLATES.values())
