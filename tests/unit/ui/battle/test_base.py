"""测试 autowsgr.ui.battle.base."""

from __future__ import annotations

import pytest

from autowsgr.ui.battle.base import (
    CLICK_PANEL,
    PAGE_SIGNATURE,
    PANEL_PROBE,
    BaseBattlePreparation,
    Panel,
    RepairStrategy,
)
from autowsgr.vision import PixelSignature


class TestRepairStrategy:
    """测试 RepairStrategy 枚举."""

    def test_members(self) -> None:
        """成员名与值应与源码一致."""
        assert RepairStrategy.MODERATE.value == 'moderate'
        assert RepairStrategy.SEVERE.value == 'severe'
        assert RepairStrategy.ALWAYS.value == 'always'
        assert RepairStrategy.NEVER.value == 'never'

    def test_all_members_present(self) -> None:
        """应包含全部四个成员."""
        members = {member.name for member in RepairStrategy}
        assert members == {'MODERATE', 'SEVERE', 'ALWAYS', 'NEVER'}


class TestPanel:
    """测试 Panel 枚举."""

    def test_members(self) -> None:
        """成员名与值应与源码一致."""
        assert Panel.STATS.value == '综合战力'
        assert Panel.QUICK_SUPPLY.value == '快速补给'
        assert Panel.QUICK_REPAIR.value == '快速修理'
        assert Panel.EQUIPMENT.value == '装备预览'

    def test_all_members_present(self) -> None:
        """应包含全部四个成员."""
        members = {member.name for member in Panel}
        assert members == {'STATS', 'QUICK_SUPPLY', 'QUICK_REPAIR', 'EQUIPMENT'}


class TestPanelProbe:
    """测试 PANEL_PROBE 映射."""

    def test_keys_match_panel_members(self) -> None:
        """键集合应与 Panel 成员完全一致."""
        assert set(PANEL_PROBE.keys()) == set(Panel)

    @pytest.mark.parametrize('panel', list(Panel))
    def test_values_are_normalized_2d_coordinates(self, panel: Panel) -> None:
        """每个值应为两个 [0, 1] 范围内浮点数构成的元组."""
        value = PANEL_PROBE[panel]
        assert isinstance(value, tuple)
        assert len(value) == 2
        x, y = value
        assert isinstance(x, float)
        assert isinstance(y, float)
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0


class TestClickPanel:
    """测试 CLICK_PANEL 映射."""

    def test_keys_match_panel_members(self) -> None:
        """键集合应与 Panel 成员完全一致."""
        assert set(CLICK_PANEL.keys()) == set(Panel)

    @pytest.mark.parametrize('panel', list(Panel))
    def test_values_are_normalized_2d_coordinates(self, panel: Panel) -> None:
        """每个值应为两个 [0, 1] 范围内浮点数构成的元组."""
        value = CLICK_PANEL[panel]
        assert isinstance(value, tuple)
        assert len(value) == 2
        x, y = value
        assert isinstance(x, float)
        assert isinstance(y, float)
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0


class TestPageSignature:
    """测试 PAGE_SIGNATURE."""

    def test_type_is_pixel_signature(self) -> None:
        """PAGE_SIGNATURE 应为 PixelSignature 实例."""
        assert isinstance(PAGE_SIGNATURE, PixelSignature)


class TestBaseBattlePreparation:
    """测试 BaseBattlePreparation 基类."""

    def test_class_is_importable(self) -> None:
        """类应可被正常导入."""
        assert BaseBattlePreparation is not None

    def test_expected_static_methods(self) -> None:
        """应包含预期的静态方法."""
        assert hasattr(BaseBattlePreparation, 'is_current_page')
        assert hasattr(BaseBattlePreparation, 'get_selected_fleet')
        assert hasattr(BaseBattlePreparation, 'get_active_panel')
        assert hasattr(BaseBattlePreparation, 'is_auto_supply_enabled')

        assert type(BaseBattlePreparation.__dict__['is_current_page']) is staticmethod
        assert type(BaseBattlePreparation.__dict__['get_selected_fleet']) is staticmethod
        assert type(BaseBattlePreparation.__dict__['get_active_panel']) is staticmethod
        assert type(BaseBattlePreparation.__dict__['is_auto_supply_enabled']) is staticmethod
