"""测试枚举类型。"""

import pytest

from autowsgr.types import (
    BaseEnum,
    ConditionFlag,
    DestroyShipWorkMode,
    EmulatorType,
    FightCondition,
    Formation,
    GameAPP,
    IntEnum,
    OcrBackend,
    OSType,
    RepairMode,
    SearchEnemyAction,
    ShipType,
    StrEnum,
)


class TestBaseEnum:
    """测试枚举基类功能。"""

    def test_missing_value_error_message(self):
        with pytest.raises(ValueError, match="不是合法的"):
            OcrBackend("not_exist")

    def test_str_enum_value(self):
        assert OcrBackend.easyocr.value == "easyocr"
        assert isinstance(OcrBackend.easyocr, str)

    def test_int_enum_value(self):
        assert RepairMode.moderate_damage.value == 1
        assert isinstance(RepairMode.moderate_damage, int)


class TestOSType:
    """测试操作系统类型枚举。"""

    def test_values(self):
        assert OSType.windows.value == "Windows"
        assert OSType.linux.value == "linux"
        assert OSType.macos.value == "macOS"

    def test_auto_returns_os_type(self):
        result = OSType.auto()
        assert isinstance(result, OSType)


class TestEmulatorType:
    """测试模拟器类型枚举。"""

    def test_values(self):
        assert EmulatorType.leidian.value == "雷电"
        assert EmulatorType.bluestacks.value == "蓝叠"
        assert EmulatorType.mumu.value == "MuMu"

    def test_default_emulator_name_leidian_windows(self):
        name = EmulatorType.leidian.default_emulator_name(OSType.windows)
        assert name == "emulator-5554"

    def test_default_emulator_name_mumu_windows(self):
        name = EmulatorType.mumu.default_emulator_name(OSType.windows)
        assert name == "127.0.0.1:16384"

    def test_default_emulator_name_unknown_raises(self):
        with pytest.raises(ValueError):
            EmulatorType.others.default_emulator_name(OSType.windows)


class TestGameAPP:
    """测试游戏渠道枚举。"""

    def test_package_name_official(self):
        assert GameAPP.official.package_name == "com.huanmeng.zhanjian2"

    def test_package_name_xiaomi(self):
        assert GameAPP.xiaomi.package_name == "com.hoolai.zjsnr.mi"

    def test_package_name_tencent(self):
        assert GameAPP.tencent.package_name == "com.tencent.tmgp.zhanjian2"


class TestRepairMode:
    """测试修理模式枚举。"""

    def test_values(self):
        assert RepairMode.moderate_damage == 1
        assert RepairMode.severe_damage == 2
        assert RepairMode.repairing == 3


class TestFightCondition:
    """测试战况选择枚举。"""

    def test_all_values(self):
        assert len(FightCondition) == 5

    def test_relative_click_position(self):
        pos = FightCondition.aim.relative_click_position
        assert isinstance(pos, tuple)
        assert len(pos) == 2
        assert all(isinstance(v, float) for v in pos)

    @pytest.mark.parametrize("cond", list(FightCondition))
    def test_all_have_positions(self, cond: FightCondition):
        pos = cond.relative_click_position
        assert 0 < pos[0] < 1
        assert 0 < pos[1] < 1


class TestFormation:
    """测试阵型枚举。"""

    def test_all_values(self):
        assert Formation.single_column == 1
        assert Formation.double_column == 2
        assert Formation.circular == 3
        assert Formation.wedge == 4
        assert Formation.single_horizontal == 5

    @pytest.mark.parametrize("f", list(Formation))
    def test_relative_position(self, f: Formation):
        pos = f.relative_position
        assert isinstance(pos, tuple)
        assert len(pos) == 2


class TestShipType:
    """测试舰船类型枚举。"""

    def test_total_count(self):
        assert len(ShipType) == 23

    def test_cv_value(self):
        assert ShipType.CV.value == "航母"

    def test_dd_value(self):
        assert ShipType.DD.value == "驱逐"

    @pytest.mark.parametrize("st", list(ShipType))
    def test_all_have_destroy_position(self, st: ShipType):
        pos = st.relative_position_in_destroy
        assert isinstance(pos, tuple)
        assert len(pos) == 2


class TestSearchEnemyAction:
    """测试索敌动作枚举。"""

    def test_values(self):
        assert SearchEnemyAction.no_action == "no_action"
        assert SearchEnemyAction.retreat == "retreat"
        assert SearchEnemyAction.detour == "detour"
        assert SearchEnemyAction.refresh == "refresh"


class TestDestroyShipWorkMode:
    """测试拆解工作模式。"""

    def test_values(self):
        assert DestroyShipWorkMode.disable == 0
        assert DestroyShipWorkMode.include == 1
        assert DestroyShipWorkMode.exclude == 2


class TestConditionFlag:
    """测试战斗状态标记。"""

    def test_values(self):
        assert ConditionFlag.DOCK_FULL == "dock is full"
        assert ConditionFlag.OPERATION_SUCCESS == "success"
        assert ConditionFlag.SL == "SL"
