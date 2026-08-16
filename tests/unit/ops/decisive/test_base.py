"""测试 autowsgr.ops.decisive.base。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from autowsgr.constants import DECISIVE_SKILL_NAMES
from autowsgr.ops.decisive.base import DecisiveBase


if TYPE_CHECKING:
    from collections.abc import Iterator


def _make_ctx(decisive_battle: object | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.config.decisive_battle = decisive_battle
    ctx.ctrl = MagicMock()
    ctx.ocr = MagicMock()
    return ctx


class TestDecisiveBaseInit:
    """DecisiveBase.__init__ 测试。"""

    @pytest.fixture(autouse=True)
    def _setup_patches(self) -> Iterator[None]:
        self.p_update_shipnames = patch('autowsgr.ops.decisive.base.update_shipnames')
        self.p_config_cls = patch('autowsgr.ops.decisive.base.DecisiveConfig')
        self.p_state_cls = patch('autowsgr.ops.decisive.base.DecisiveState')
        self.p_logic_cls = patch('autowsgr.ops.decisive.base.DecisiveLogic')
        self.p_battle_page_cls = patch('autowsgr.ops.decisive.base.DecisiveBattlePage')
        self.p_map_cls = patch('autowsgr.ops.decisive.base.DecisiveMapController')
        self.p_log_warning = patch('autowsgr.ops.decisive.base._log.warning')

        self.mock_update_shipnames = self.p_update_shipnames.start()
        self.mock_config_cls = self.p_config_cls.start()
        self.mock_state_cls = self.p_state_cls.start()
        self.mock_logic_cls = self.p_logic_cls.start()
        self.mock_battle_page_cls = self.p_battle_page_cls.start()
        self.mock_map_cls = self.p_map_cls.start()
        self.mock_log_warning = self.p_log_warning.start()

        yield

        patch.stopall()

    @pytest.mark.parametrize(
        ('ctx_config_dump', 'expected_base'),
        [
            (None, {}),
            ({'chapter': 3, 'level1': ['X'] * 6}, {'chapter': 3, 'level1': ['X'] * 6}),
        ],
    )
    def test_config_merge(
        self,
        ctx_config_dump: dict[str, object] | None,
        expected_base: dict[str, object],
    ) -> None:
        if ctx_config_dump is not None:
            ctx_decisive = MagicMock()
            ctx_decisive.model_dump.return_value = ctx_config_dump
            ctx = _make_ctx(decisive_battle=ctx_decisive)
        else:
            ctx = _make_ctx(decisive_battle=None)

        config = MagicMock()
        config.model_dump.return_value = {'chapter': 5, 'level2': ['Y']}

        self.mock_config_cls.return_value.level1 = ['A'] * 6
        self.mock_config_cls.return_value.level2 = ['B']

        DecisiveBase(ctx, config)

        config.model_dump.assert_called_once_with(exclude_unset=True)
        self.mock_config_cls.assert_called_once_with(
            **{**expected_base, 'chapter': 5, 'level2': ['Y']},
        )

    def test_level1_short_warning(self) -> None:
        ctx = _make_ctx(decisive_battle=None)
        config = MagicMock()
        config.model_dump.return_value = {}

        self.mock_config_cls.return_value.level1 = ['A'] * 5
        self.mock_config_cls.return_value.level2 = ['B']

        DecisiveBase(ctx, config)

        self.mock_log_warning.assert_called_once()

    def test_update_shipnames_called(self) -> None:
        ctx = _make_ctx(decisive_battle=None)
        config = MagicMock()
        config.model_dump.return_value = {}

        self.mock_config_cls.return_value.level1 = ['A1', 'A2']
        self.mock_config_cls.return_value.level2 = ['B1']

        DecisiveBase(ctx, config)

        self.mock_update_shipnames.assert_called_once_with(
            ['A1', 'A2', 'B1'] + DECISIVE_SKILL_NAMES,
        )

    def test_state_property_returns_created_state(self) -> None:
        ctx = _make_ctx(decisive_battle=None)
        config = MagicMock()
        config.model_dump.return_value = {}

        expected_state = self.mock_state_cls.return_value

        obj = DecisiveBase(ctx, config)

        assert obj.state is expected_state

    def test_attributes_initialized(self) -> None:
        ctx = _make_ctx(decisive_battle=None)
        config = MagicMock()
        config.model_dump.return_value = {}

        merged_config = self.mock_config_cls.return_value
        expected_state = self.mock_state_cls.return_value
        expected_logic = self.mock_logic_cls.return_value
        expected_battle_page = self.mock_battle_page_cls.return_value
        expected_map = self.mock_map_cls.return_value

        obj = DecisiveBase(ctx, config)

        assert obj._ctx is ctx
        assert obj._ctrl is ctx.ctrl
        assert obj._ocr is ctx.ocr
        assert obj._config is merged_config
        assert obj._state is expected_state
        assert obj._logic is expected_logic
        assert obj._battle_page is expected_battle_page
        assert obj._map is expected_map
        assert obj._resume_mode is False
        assert obj._has_chosen_fleet is False
        assert obj._wait_deadline == 0.0
        assert obj._use_last_fleet_attempts == 0

        self.mock_state_cls.assert_called_once_with(chapter=merged_config.chapter)
        self.mock_logic_cls.assert_called_once_with(
            merged_config,
            expected_state,
            ctx=ctx,
        )
        self.mock_battle_page_cls.assert_called_once_with(ctx, ocr=ctx.ocr)
        self.mock_map_cls.assert_called_once_with(ctx, merged_config)
