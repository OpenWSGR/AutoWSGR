"""测试 autowsgr.types。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from autowsgr.types import (
    ConditionFlag,
    DecisiveEntryStatus,
    EmulatorType,
    FightCondition,
    Formation,
    GameAPP,
    OSType,
    PageName,
    RepairMode,
    ShipDamageState,
    ShipType,
)


def test_base_enum_missing() -> None:
    """不存在的枚举值应抛出 ValueError。"""
    with pytest.raises(ValueError, match='不是合法的'):
        ShipDamageState('invalid')


def test_ostype_is_wsl_true() -> None:
    """_is_wsl 应在检测到 WSL 环境变量时返回 True。"""
    with patch.dict('os.environ', {'WSL_DISTRO_NAME': 'Ubuntu'}, clear=False):
        assert OSType._is_wsl() is True


def test_ostype_is_wsl_false() -> None:
    """_is_wsl 在无 WSL 标记时应返回 False。"""
    with patch.dict('os.environ', {}, clear=True), patch('builtins.open', side_effect=OSError):
        assert OSType._is_wsl() is False


def test_emulator_type_default_name_windows() -> None:
    """Windows 下雷电模拟器默认 serial 应正确。"""
    serial = EmulatorType.leidian.default_emulator_name(OSType.windows)
    assert serial == 'emulator-5554'


def test_emulator_type_default_name_macos() -> None:
    """macOS 下蓝叠模拟器默认 serial 应正确。"""
    serial = EmulatorType.bluestacks.default_emulator_name(OSType.macos)
    assert serial == '127.0.0.1:5555'


def test_game_app_package_names() -> None:
    """各渠道服包名应正确。"""
    assert GameAPP.official.package_name == 'com.huanmeng.zhanjian2'
    assert GameAPP.xiaomi.package_name == 'com.hoolai.zjsnr.mi'
    assert GameAPP.tencent.package_name == 'com.tencent.tmgp.zhanjian2'


def test_fight_condition_positions() -> None:
    """FightCondition 应返回有效的相对坐标。"""
    pos = FightCondition.aim.relative_click_position
    assert isinstance(pos, tuple)
    assert len(pos) == 2
    assert 0.0 < pos[0] < 1.0
    assert 0.0 < pos[1] < 1.0


def test_formation_relative_position() -> None:
    """Formation 应返回有效的相对坐标。"""
    pos = Formation.double_column.relative_position
    assert isinstance(pos, tuple)
    assert len(pos) == 2


def test_ship_type_destroy_position() -> None:
    """ShipType 应返回拆解界面的相对坐标。"""
    pos = ShipType.DD.relative_position_in_destroy
    assert isinstance(pos, tuple)
    assert len(pos) == 2


def test_ship_damage_state_values() -> None:
    """ShipDamageState 数值应符合预期。"""
    assert ShipDamageState.NORMAL.value == 0
    assert ShipDamageState.MODERATE.value == 1
    assert ShipDamageState.SEVERE.value == 2
    assert ShipDamageState.NO_SHIP.value == -1


def test_repair_mode_values() -> None:
    """RepairMode 数值应符合预期。"""
    assert RepairMode.moderate_damage.value == 1
    assert RepairMode.severe_damage.value == 2


def test_decisive_entry_status_values() -> None:
    """DecisiveEntryStatus 应包含预期值。"""
    assert DecisiveEntryStatus.CANT_FIGHT == 'cant_fight'
    assert DecisiveEntryStatus.CHALLENGING == 'challenging'


def test_condition_flag_values() -> None:
    """ConditionFlag 应包含预期值。"""
    assert ConditionFlag.OPERATION_SUCCESS == 'success'
    assert ConditionFlag.DOCK_FULL == 'dock is full'


def test_page_name_values() -> None:
    """PageName 应包含预期值。"""
    assert PageName.MAIN == '主页面'
    assert PageName.BATTLE_PREP == '出征准备'
