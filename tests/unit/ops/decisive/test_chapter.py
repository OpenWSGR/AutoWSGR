"""测试 autowsgr.ops.decisive.chapter。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autowsgr.infra import DockFullError
from autowsgr.ops.decisive.chapter import DecisiveChapterOps


class TestDecisiveChapterOps:
    """DecisiveChapterOps 测试。"""

    def setup_method(self) -> None:
        self.ctx = MagicMock()
        self.ctx.config.decisive_battle = None

    def _make_config(self, **kwargs: object) -> tuple[MagicMock, MagicMock]:
        config = MagicMock()
        config.model_dump.return_value = {}
        config.level1 = ['a'] * 6
        config.level2 = ['b'] * 6
        for k, v in kwargs.items():
            setattr(config, k, v)
        merged = MagicMock()
        for k, v in kwargs.items():
            setattr(merged, k, v)
        merged.level1 = ['a'] * 6
        merged.level2 = ['b'] * 6
        return config, merged

    def test_init(self) -> None:
        config, merged = self._make_config(chapter=3)
        with (
            patch('autowsgr.ops.decisive.base.update_shipnames') as mock_update,
            patch('autowsgr.ops.decisive.base.DecisiveBattlePage'),
            patch('autowsgr.ops.decisive.base.DecisiveMapController'),
            patch('autowsgr.ops.decisive.base.DecisiveConfig', return_value=merged),
        ):
            ops = DecisiveChapterOps(self.ctx, config)
            assert ops.state.chapter == 3
            mock_update.assert_called_once()

    def test_prepare_entry_state(self) -> None:
        config, merged = self._make_config(chapter=2)
        with (
            patch('autowsgr.ops.decisive.base.update_shipnames'),
            patch('autowsgr.ops.decisive.base.DecisiveBattlePage'),
            patch('autowsgr.ops.decisive.base.DecisiveMapController'),
            patch('autowsgr.ops.decisive.base.DecisiveConfig', return_value=merged),
            patch('autowsgr.ops.navigate.goto_page') as mock_goto,
        ):
            ops = DecisiveChapterOps(self.ctx, config)
            ops._prepare_entry_state()
            mock_goto.assert_called_once()
            ops._battle_page.navigate_to_chapter.assert_called_once_with(2)

    def test_dock_full_destroy_enabled(self) -> None:
        config, merged = self._make_config(chapter=1, full_destroy=True)
        with (
            patch('autowsgr.ops.decisive.base.update_shipnames'),
            patch('autowsgr.ops.decisive.base.DecisiveBattlePage'),
            patch('autowsgr.ops.decisive.base.DecisiveMapController'),
            patch('autowsgr.ops.decisive.base.DecisiveConfig', return_value=merged),
            patch('autowsgr.ops.destroy.destroy_ships') as mock_destroy,
        ):
            ops = DecisiveChapterOps(self.ctx, config)
            ops._do_dock_full_destroy()
            mock_destroy.assert_called_once()

    def test_dock_full_destroy_disabled(self) -> None:
        config, merged = self._make_config(chapter=1, full_destroy=False)
        with (
            patch('autowsgr.ops.decisive.base.update_shipnames'),
            patch('autowsgr.ops.decisive.base.DecisiveBattlePage'),
            patch('autowsgr.ops.decisive.base.DecisiveMapController'),
            patch('autowsgr.ops.decisive.base.DecisiveConfig', return_value=merged),
        ):
            ops = DecisiveChapterOps(self.ctx, config)
            with pytest.raises(DockFullError, match='船坞已满'):
                ops._do_dock_full_destroy()
