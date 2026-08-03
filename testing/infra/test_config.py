"""测试配置系统与日志工具。"""

from collections.abc import Callable
from pathlib import Path

import pytest

from autowsgr.infra import (
    BattleConfig,
    ConfigManager,
    DecisiveConfig,
    EmulatorConfig,
    FightConfig,
    OCRConfig,
    UserConfig,
)
from autowsgr.types import (
    DestroyShipWorkMode,
    EmulatorType,
    OSType,
    RepairMode,
)


@pytest.fixture(autouse=True)
def _mock_wsl(monkeypatch: pytest.MonkeyPatch):
    """在非 WSL Linux CI runner 上伪装成 WSL，使 OSType.auto() 不抛异常。"""
    monkeypatch.setattr(OSType, '_is_wsl', staticmethod(lambda: True))


@pytest.fixture(autouse=True)
def _reset_operation_delay():
    """每个用例前后复位 OPERATION_DELAY 全局, 避免 delay 迁移污染其他用例。"""
    from autowsgr.infra import config

    config.OPERATION_DELAY_MIN = 0.0
    config.OPERATION_DELAY_MAX = 0.0
    yield
    config.OPERATION_DELAY_MIN = 0.0
    config.OPERATION_DELAY_MAX = 0.0


# ── EmulatorConfig ──


class TestEmulatorConfig:
    def test_from_dict(self):
        cfg = EmulatorConfig.model_validate({'type': '蓝叠', 'serial': '127.0.0.1:5555'})
        assert cfg.type == EmulatorType.bluestacks
        assert cfg.serial == '127.0.0.1:5555'


# ── OCRConfig ──


class TestOCRConfig:
    def test_unused_backend_field_is_removed(self):
        assert not hasattr(OCRConfig(), 'backend')

    def test_ship_name_match_confidence_default(self):
        assert OCRConfig().ship_name_match_confidence == 0.65

    def test_ship_name_corrections_default(self):
        assert OCRConfig().ship_name_corrections == {}

    def test_ship_name_aliases_default(self):
        assert OCRConfig().ship_name_aliases == {}

    def test_ship_name_corrections_skip_malformed_entries(self):
        config = OCRConfig(
            ship_name_corrections={
                ' 误识别 ': ' 胡德 ',
                'empty': ' ',
                1: '雪风',
            },
        )

        assert config.ship_name_corrections == {'误识别': '胡德'}

    def test_ship_name_corrections_skip_non_mapping(self):
        config = OCRConfig(ship_name_corrections=['误识别', '胡德'])  # type: ignore[arg-type]

        assert config.ship_name_corrections == {}

    def test_ship_name_aliases_are_trimmed(self):
        config = OCRConfig(ship_name_aliases={' 契卡洛夫 ': ' 85工程 '})

        assert config.ship_name_aliases == {'契卡洛夫': '85工程'}

    @pytest.mark.parametrize(
        ('value', 'message'),
        [(-0.01, 'greater than or equal'), (1.01, 'less than or equal')],
    )
    def test_ship_name_match_confidence_bounds(self, value: float, message: str):
        with pytest.raises(ValueError, match=message):
            OCRConfig(ship_name_match_confidence=value)


# ── DecisiveBattleConfig ──


class TestDecisiveConfig:
    def test_invalid_chapter(self):
        with pytest.raises(ValueError, match='决战章节'):
            DecisiveConfig(chapter=0)

    def test_fleet_change_algorithm_is_disabled_by_default(self):
        assert DecisiveConfig().use_new_fleet_change_algorithm is False

    def test_fleet_change_algorithm_can_be_enabled(self):
        config = DecisiveConfig(use_new_fleet_change_algorithm=True)

        assert config.use_new_fleet_change_algorithm is True


# ── UserConfig ──


class TestUserConfig:
    def test_unused_bathroom_feature_count_is_removed(self):
        config = UserConfig(
            emulator=EmulatorConfig(
                serial='127.0.0.1:5555',
                path='/tmp/emulator',
            ),
            os_type=OSType.linux,
        )

        assert not hasattr(config, 'bathroom_feature_count')

    def test_from_yaml(self, tmp_yaml: Callable[[str, str], Path]):
        content = """\
emulator:
  type: "蓝叠"
  serial: "127.0.0.1:5555"
  path: "C:/fake/player.exe"
account:
  game_app: "官服"
operation_delay_min: 2.0
operation_delay_max: 3.0
dock_full_destroy: false
"""
        path = tmp_yaml('config.yaml', content)
        cfg = UserConfig.from_yaml(path)
        assert cfg.emulator.type == EmulatorType.bluestacks
        assert cfg.emulator.serial == '127.0.0.1:5555'
        assert cfg.dock_full_destroy is False
        assert cfg.operation_delay_min == 2.0
        assert cfg.operation_delay_max == 3.0
        assert not hasattr(cfg, 'delay')

    def test_with_daily_automation(self, tmp_yaml: Callable[[str, str], Path]):
        content = """\
emulator:
  type: "雷电"
  serial: "emulator-5554"
  path: "C:/fake/dnplayer.exe"
daily_automation:
  auto_exercise: false
  battle_type: "简单航母"
"""
        path = tmp_yaml('daily.yaml', content)
        cfg = UserConfig.from_yaml(path)
        assert cfg.daily_automation is not None
        assert cfg.daily_automation.auto_exercise is False
        assert cfg.daily_automation.battle_type == '简单航母'

    def test_with_decisive_battle(self, tmp_yaml: Callable[[str, str], Path]):
        content = """\
emulator:
  type: "雷电"
  serial: "emulator-5554"
  path: "C:/fake/dnplayer.exe"
decisive_battle:
  chapter: 5
  repair_level: 2
"""
        path = tmp_yaml('decisive.yaml', content)
        cfg = UserConfig.from_yaml(path)
        assert cfg.decisive_battle is not None
        assert cfg.decisive_battle.chapter == 5
        assert cfg.decisive_battle.repair_level == 2

    def test_destroy_ship_config(self, tmp_yaml: Callable[[str, str], Path]):
        content = """\
emulator:
  type: "雷电"
  serial: "emulator-5554"
  path: "C:/fake/dnplayer.exe"
destroy_ship_work_mode: 1
destroy_ship_types:
  - "驱逐"
  - "轻巡"
"""
        path = tmp_yaml('destroy.yaml', content)
        cfg = UserConfig.from_yaml(path)
        assert cfg.destroy_ship_work_mode == DestroyShipWorkMode.include
        assert len(cfg.destroy_ship_types) == 2


# ── FightConfig ──


class TestFightConfig:
    def test_repair_mode_expanded(self):
        cfg = FightConfig(repair_mode=RepairMode.moderate_damage)
        assert isinstance(cfg.repair_mode, list)
        assert len(cfg.repair_mode) == 6
        assert all(r == RepairMode.moderate_damage for r in cfg.repair_mode)

    def test_repair_mode_list_kept(self):
        modes = [RepairMode.moderate_damage, RepairMode.severe_damage] + [
            RepairMode.moderate_damage
        ] * 4
        cfg = FightConfig(repair_mode=modes)
        assert cfg.repair_mode == modes


class TestBattleConfig:
    def test_default_repair_mode(self):
        cfg = BattleConfig()
        assert isinstance(cfg.repair_mode, list)
        assert all(r == RepairMode.moderate_damage for r in cfg.repair_mode)


# ── ConfigManager ──


class TestConfigManager:
    def test_load_existing_file(self, tmp_yaml: Callable[[str, str], Path]):
        content = """\
emulator:
  type: "MuMu"
  serial: "127.0.0.1:16384"
  path: "C:/fake/MuMuPlayer.exe"
operation_delay_min: 2.5
"""
        path = tmp_yaml('settings.yaml', content)
        cfg = ConfigManager.load(path)
        assert cfg.emulator.type == EmulatorType.mumu
        assert cfg.operation_delay_min == 2.5
        assert not hasattr(cfg, 'delay')

    def test_load_nonexistent_returns_default(self, tmp_path: Path):
        cfg = ConfigManager.load(tmp_path / 'no_such_file.yaml')
        assert isinstance(cfg, UserConfig)
        assert not hasattr(cfg, 'delay')


# ── ConfigCompat (向下兼容迁移) ──


class TestConfigCompat:
    """老版本配置: detect (运行期崩溃) + migrate (工具, 纯转换) + operation_delay 字段。"""

    # ── detect_legacy_user_config (只读) ──

    def test_detect_clean_returns_empty(self):
        from autowsgr.infra.config_compat import detect_legacy_user_config

        assert detect_legacy_user_config({'emulator': {'type': 'MuMu'}}) == []

    def test_detect_hits_each_legacy_item(self):
        from autowsgr.infra.config_compat import detect_legacy_user_config

        assert detect_legacy_user_config({'ship_name_file': 'x'})
        assert detect_legacy_user_config({'account': {'account': 'a', 'password': 'b'}})
        assert detect_legacy_user_config({'delay': 1.5})
        assert detect_legacy_user_config({'emulator_type': 'MuMu'})
        assert detect_legacy_user_config({'check_update': False})

    def test_detect_non_dict_returns_empty(self):
        from autowsgr.infra.config_compat import detect_legacy_user_config

        assert detect_legacy_user_config(None) == []  # type: ignore[arg-type]

    # ── migrate_raw_config (原地转换, 无副作用) ──

    def test_ship_name_file_removed(self):
        from autowsgr.infra.config_compat import migrate_raw_config

        out = migrate_raw_config({'ship_name_file': '/tmp/x.json'})
        assert 'ship_name_file' not in out

    def test_account_credentials_removed(self):
        from autowsgr.infra.config_compat import migrate_raw_config

        out = migrate_raw_config(
            {'account': {'game_app': '官服', 'account': 'a', 'password': 'b'}},
        )
        assert out['account'] == {'game_app': '官服'}

    def test_delay_migrated_to_operation_delay_fields(self):
        from autowsgr.infra.config_compat import migrate_raw_config

        out = migrate_raw_config({'delay': 1.5})
        assert 'delay' not in out
        assert out['operation_delay_min'] == 1.5
        assert out['operation_delay_max'] == 1.5

    def test_delay_unparseable_dropped(self):
        from autowsgr.infra.config_compat import migrate_raw_config

        out = migrate_raw_config({'delay': 'abc'})
        assert 'delay' not in out
        assert 'operation_delay_min' not in out

    def test_operation_delay_reads_global(self):
        from autowsgr.infra import config

        config.OPERATION_DELAY_MIN = 2.0
        config.OPERATION_DELAY_MAX = 2.0
        assert config.operation_delay() == 2.0

    def test_non_dict_passthrough(self):
        from autowsgr.infra.config_compat import migrate_raw_config

        assert migrate_raw_config(None) is None  # type: ignore[arg-type]

    def test_legacy_emulator_fields_migrated(self):
        """classic 平铺 emulator_type/start_cmd/name → 嵌套 emulator 块, 值透传。"""
        from autowsgr.infra.config_compat import migrate_raw_config

        out = migrate_raw_config(
            {
                'emulator_type': 'MuMu',
                'emulator_start_cmd': 'C:/fake/MuMuPlayer.exe',
                'emulator_name': '127.0.0.1:16384',
            },
        )
        assert out['emulator'] == {
            'type': 'MuMu',
            'path': 'C:/fake/MuMuPlayer.exe',
            'serial': '127.0.0.1:16384',
        }
        assert 'emulator_type' not in out

    def test_nested_emulator_takes_precedence(self):
        """同时存在平铺与嵌套时, 以嵌套 emulator 块为准。"""
        from autowsgr.infra.config_compat import migrate_raw_config

        out = migrate_raw_config(
            {
                'emulator_type': 'MuMu',
                'emulator': {'type': '蓝叠', 'serial': '127.0.0.1:5555'},
            },
        )
        assert out['emulator'] == {'type': '蓝叠', 'serial': '127.0.0.1:5555'}
        assert 'emulator_type' not in out

    def test_legacy_null_emulator_fields_skipped(self):
        """None 值的平铺模拟器字段不写入嵌套 (让 dev 自动检测)。"""
        from autowsgr.infra.config_compat import migrate_raw_config

        out = migrate_raw_config(
            {'emulator_type': 'MuMu', 'emulator_start_cmd': None, 'emulator_name': None},
        )
        assert out['emulator'] == {'type': 'MuMu'}

    def test_legacy_toplevel_fields_dropped(self):
        """check_update / 顶层 show_map_node 等 classic 废弃字段被清理。"""
        from autowsgr.infra.config_compat import migrate_raw_config

        out = migrate_raw_config({'check_update': False, 'show_map_node': True})
        assert 'check_update' not in out
        assert 'show_map_node' not in out

    # ── detect 与 migrate 一致性 (防漂移) ──

    def test_detect_migrate_consistency(self):
        import copy

        from autowsgr.infra.config_compat import (
            detect_legacy_user_config,
            migrate_raw_config,
        )

        samples = [
            {},
            {'emulator': {'type': 'MuMu'}},
            {'ship_name_file': 'x'},
            {'delay': 1.0},
            {'emulator_type': 'MuMu'},
            {'check_update': True},
            {'account': {'account': 'a'}},
        ]
        for sample in samples:
            detected = bool(detect_legacy_user_config(sample))
            before = copy.deepcopy(sample)
            migrate_raw_config(sample)
            changed = sample != before
            assert detected == changed, f'detect/migrate 不一致: {sample!r}'

    # ── operation_delay_min/max 字段 → 模块全局 ──

    def test_operation_delay_field_sets_globals(self):
        from autowsgr.infra import config

        # 给定 serial+path 的 emulator: 既满足 linux/WSL 分支的强制要求,
        # 又让 windows 分支跳过 auto_emulator_path (避免在非 Windows 上 import winreg)。
        # 本用例只验证 operation_delay 字段 → 模块全局, 与模拟器无关。
        cfg = UserConfig(
            emulator=EmulatorConfig(serial='emulator-5554', path='/fake/dnplayer.exe'),
            operation_delay_min=1.0,
            operation_delay_max=2.0,
        )
        assert cfg.operation_delay_min == 1.0
        assert cfg.operation_delay_max == 2.0
        assert config.OPERATION_DELAY_MIN == 1.0
        assert config.OPERATION_DELAY_MAX == 2.0

    # ── 运行期 from_yaml: 检测到老版本即崩溃 ──

    def test_from_yaml_crashes_on_legacy_emulator(
        self,
        tmp_yaml: Callable[[str, str], Path],
    ):
        from autowsgr.infra.config_compat import LegacyConfigError

        path = tmp_yaml('emu_legacy.yaml', "emulator_type: 'MuMu'\n")
        with pytest.raises(LegacyConfigError, match='迁移工具'):
            UserConfig.from_yaml(path)

    def test_from_yaml_crashes_on_delay(self, tmp_yaml: Callable[[str, str], Path]):
        from autowsgr.infra.config_compat import LegacyConfigError

        path = tmp_yaml('delay_legacy.yaml', 'delay: 1.5\n')
        with pytest.raises(LegacyConfigError, match='delay'):
            UserConfig.from_yaml(path)

    def test_clean_config_loads_and_not_rewritten(
        self,
        tmp_yaml: Callable[[str, str], Path],
    ):
        """干净配置正常加载; from_yaml 不再有写回副作用, 文件字节原样保留。"""
        content = """\
emulator:
  type: "MuMu"
  path: "C:/fake/MuMuPlayer.exe"
  serial: "127.0.0.1:16384"
dock_full_destroy: false
"""
        path = tmp_yaml('clean.yaml', content)
        before = path.read_text(encoding='utf-8')
        cfg = UserConfig.from_yaml(path)
        assert cfg.emulator.type == EmulatorType.mumu
        assert path.read_text(encoding='utf-8') == before


# ── PlanCompat (计划文件迁移: classic fleet 前导空占位) ──


class TestPlanCompat:
    """计划文件老版本: detect_legacy_plan (崩溃) + migrate_plan_dict (剥离前导空)。"""

    # ── detect_legacy_plan (只读) ──

    def test_detect_clean_fleet_empty(self):
        from autowsgr.infra.config_compat import detect_legacy_plan

        assert detect_legacy_plan({'fleet': ['吹雪', '明斯克']}) == []
        assert detect_legacy_plan({}) == []

    def test_detect_leading_empty_fleet(self):
        from autowsgr.infra.config_compat import detect_legacy_plan

        assert detect_legacy_plan({'fleet': ['', '吹雪']})
        assert detect_legacy_plan({'fleet': [None, '吹雪']})

    # ── migrate_plan_dict (原地转换) ──

    def test_leading_empty_string_stripped(self):
        from autowsgr.infra.config_compat import migrate_plan_dict

        out = migrate_plan_dict({'fleet': ['', '吹雪', '明斯克', '胡德', '赤诚', '']})
        # 前导 "" 占位被剥离; 尾部 "" 保留 (运行期归一化为 None = 不关心该槽位)
        assert out['fleet'] == ['吹雪', '明斯克', '胡德', '赤诚', '']

    def test_leading_none_stripped(self):
        from autowsgr.infra.config_compat import migrate_plan_dict

        out = migrate_plan_dict({'fleet': [None, '吹雪', '明斯克']})
        assert out['fleet'] == ['吹雪', '明斯克']

    def test_multiple_leading_empties_stripped(self):
        from autowsgr.infra.config_compat import migrate_plan_dict

        out = migrate_plan_dict({'fleet': ['', '', '吹雪']})
        assert out['fleet'] == ['吹雪']

    def test_whitespace_only_treated_as_empty(self):
        from autowsgr.infra.config_compat import migrate_plan_dict

        out = migrate_plan_dict({'fleet': ['   ', '吹雪']})
        assert out['fleet'] == ['吹雪']

    def test_clean_fleet_unchanged(self):
        from autowsgr.infra.config_compat import migrate_plan_dict

        clean = ['飞龙', 'U-1206', 'U-47', '射水鱼', 'U-96', '鲃鱼']
        out = migrate_plan_dict({'fleet': list(clean)})
        assert out['fleet'] == clean

    def test_non_list_fleet_skipped(self):
        """fleet 缺省 / None / 非 list 都不动。"""
        from autowsgr.infra.config_compat import migrate_plan_dict

        assert migrate_plan_dict({}) == {}
        assert migrate_plan_dict({'fleet': None}) == {'fleet': None}
        assert migrate_plan_dict({'fleet': '吹雪'}) == {'fleet': '吹雪'}

    def test_empty_list_fleet_skipped(self):
        from autowsgr.infra.config_compat import migrate_plan_dict

        assert migrate_plan_dict({'fleet': []}) == {'fleet': []}

    def test_non_dict_passthrough(self):
        from autowsgr.infra.config_compat import migrate_plan_dict

        assert migrate_plan_dict(None) is None  # type: ignore[arg-type]

    def test_from_yaml_crashes_on_legacy_fleet(self, tmp_yaml: Callable[[str, str], Path]):
        """CombatPlan.from_yaml 检测到 classic 前导空 fleet → 崩溃提示迁移。"""
        from autowsgr.combat.plan import CombatPlan
        from autowsgr.infra.config_compat import LegacyConfigError

        path = tmp_yaml('plan_legacy.yaml', 'fleet: ["", "吹雪", "明斯克"]\n')
        with pytest.raises(LegacyConfigError, match='迁移工具'):
            CombatPlan.from_yaml(path)

    def test_clean_plan_loads_and_not_rewritten(
        self,
        tmp_yaml: Callable[[str, str], Path],
    ):
        """干净 fleet 的计划文件正常加载, 不被改写 (格式保留)。"""
        from autowsgr.combat.plan import CombatPlan

        content = 'fleet: ["飞龙", "U-1206"]\n'
        path = tmp_yaml('plan_clean.yaml', content)
        before = path.read_text(encoding='utf-8')
        plan = CombatPlan.from_yaml(path)
        assert plan.fleet == ['飞龙', 'U-1206']
        assert path.read_text(encoding='utf-8') == before


# ── LogConfig (setup_logger) ──


class TestSetupLogger:
    """setup_logger 进行基本函数验证。"""

    def test_with_log_dir(self, tmp_path: Path):
        """log_dir 应被自动创建。"""
        from autowsgr.infra import setup_logger

        log_dir = tmp_path / 'logs' / 'sub'
        setup_logger(log_dir=log_dir, level='INFO')
        assert log_dir.exists()
