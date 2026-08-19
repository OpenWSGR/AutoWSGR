"""测试 autowsgr.ops.build。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from autowsgr.ops.build import BuildRecipe, build_ship, collect_built_ships
from autowsgr.types import PageName


class TestBuildRecipe:
    """BuildRecipe 数据类测试。"""

    def test_defaults(self) -> None:
        recipe = BuildRecipe(30, 30, 30, 30)
        assert recipe.fuel == 30
        assert recipe.ammo == 30
        assert recipe.steel == 30
        assert recipe.bauxite == 30


class TestCollectBuiltShips:
    """collect_built_ships 测试。"""

    @patch('autowsgr.ops.build.goto_page')
    @patch('autowsgr.ui.build_page.BuildPage')
    def test_collect_ship(
        self,
        mock_page_cls: MagicMock,
        mock_goto: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_page = mock_page_cls.return_value
        mock_page.collect_all.return_value = 3
        # 模拟当前已在建造标签
        mock_page_cls.get_active_tab.return_value = MagicMock()

        result = collect_built_ships(ctx)

        mock_goto.assert_called_once_with(ctx, PageName.BUILD)
        mock_page.collect_all.assert_called_once_with('ship', allow_fast_build=False)
        assert result == 3

    @patch('autowsgr.ops.build.goto_page')
    @patch('autowsgr.ui.build_page.BuildPage')
    def test_collect_equipment(
        self,
        mock_page_cls: MagicMock,
        mock_goto: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_page = mock_page_cls.return_value
        mock_page.collect_all.return_value = 2

        result = collect_built_ships(ctx, build_type='equipment')

        mock_goto.assert_called_once_with(ctx, PageName.BUILD)
        mock_page.switch_tab.assert_called_once()
        mock_page.collect_all.assert_called_once_with('equipment', allow_fast_build=False)
        assert result == 2

    @patch('autowsgr.ops.build.goto_page')
    @patch('autowsgr.ui.build_page.BuildPage')
    def test_switch_tab_when_not_build(
        self,
        mock_page_cls: MagicMock,
        mock_goto: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_page = mock_page_cls.return_value
        mock_page.collect_all.return_value = 1
        # get_active_tab 返回的 tab 不等于当前标签，触发 switch_tab
        other_tab = MagicMock()
        mock_page_cls.get_active_tab.return_value = other_tab

        collect_built_ships(ctx)

        mock_goto.assert_called_once_with(ctx, PageName.BUILD)
        mock_page.switch_tab.assert_called_once()


class TestBuildShip:
    """build_ship 测试。"""

    @patch('autowsgr.ops.build.collect_built_ships')
    @patch('autowsgr.ui.build_page.BuildPage')
    def test_build_ship_no_recipe(
        self,
        mock_page_cls: MagicMock,
        mock_collect: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_page = mock_page_cls.return_value

        build_ship(ctx)

        mock_collect.assert_called_once_with(ctx, build_type='ship', allow_fast_build=False)
        mock_page.start_new_build.assert_called_once_with('ship')

    @patch('autowsgr.ops.build.collect_built_ships')
    @patch('autowsgr.ui.build_page.BuildPage')
    def test_build_ship_with_recipe(
        self,
        mock_page_cls: MagicMock,
        mock_collect: MagicMock,
    ) -> None:
        ctx = MagicMock()
        mock_page = mock_page_cls.return_value
        recipe = BuildRecipe(400, 30, 600, 130)

        build_ship(ctx, recipe=recipe, build_type='equipment', allow_fast_build=True)

        mock_collect.assert_called_once_with(
            ctx,
            build_type='equipment',
            allow_fast_build=True,
        )
        mock_page.start_new_build.assert_called_once_with('equipment')
