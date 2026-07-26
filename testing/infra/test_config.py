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
    UserConfig,
    load_yaml,
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


# ── DecisiveBattleConfig ──


class TestDecisiveConfig:
    def test_invalid_chapter(self):
        with pytest.raises(ValueError, match='决战章节'):
            DecisiveConfig(chapter=0)


# ── UserConfig ──


class TestUserConfig:
    def test_from_yaml(self, tmp_yaml: Callable[[str, str], Path]):
        content = """\
emulator:
  type: "蓝叠"
  serial: "127.0.0.1:5555"
  path: "C:/fake/player.exe"
account:
  game_app: "官服"
delay: 2.0
dock_full_destroy: false
"""
        path = tmp_yaml('config.yaml', content)
        cfg = UserConfig.from_yaml(path)
        assert cfg.emulator.type == EmulatorType.bluestacks
        assert cfg.emulator.serial == '127.0.0.1:5555'
        assert cfg.dock_full_destroy is False
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
delay: 2.5
"""
        path = tmp_yaml('settings.yaml', content)
        cfg = ConfigManager.load(path)
        assert cfg.emulator.type == EmulatorType.mumu
        assert not hasattr(cfg, 'delay')

    def test_load_nonexistent_returns_default(self, tmp_path: Path):
        cfg = ConfigManager.load(tmp_path / 'no_such_file.yaml')
        assert isinstance(cfg, UserConfig)
        assert not hasattr(cfg, 'delay')


# ── ConfigCompat (向下兼容迁移) ──


class TestConfigCompat:
    """向下兼容迁移: migrate_raw_config + operation_delay。"""

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

    def test_delay_mapped_to_operation_delay(self):
        from autowsgr.infra import config
        from autowsgr.infra.config_compat import migrate_raw_config

        out = migrate_raw_config({'delay': 1.5})
        assert 'delay' not in out
        assert config.OPERATION_DELAY_MIN == 1.5
        assert config.OPERATION_DELAY_MAX == 1.5

    def test_operation_delay_reads_global(self):
        from autowsgr.infra import config

        config.OPERATION_DELAY_MIN = 2.0
        config.OPERATION_DELAY_MAX = 2.0
        assert config.operation_delay() == 2.0

    def test_non_dict_passthrough(self):
        from autowsgr.infra.config_compat import migrate_raw_config

        assert migrate_raw_config(None) is None  # type: ignore[arg-type]

    def test_legacy_emulator_fields_migrated(self, tmp_yaml: Callable[[str, str], Path]):
        """classic 平铺 emulator_type/start_cmd/name → 嵌套 emulator 块, 值透传。"""
        content = """\
emulator_type: "MuMu"
emulator_start_cmd: "C:/fake/MuMuPlayer.exe"
emulator_name: "127.0.0.1:16384"
"""
        path = tmp_yaml('emu_legacy.yaml', content)
        cfg = UserConfig.from_yaml(path)
        assert cfg.emulator.type == EmulatorType.mumu
        assert cfg.emulator.path == 'C:/fake/MuMuPlayer.exe'
        assert cfg.emulator.serial == '127.0.0.1:16384'

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

    # ── 写回 (source_path 持久化) ──

    def test_legacy_emulator_fields_written_back(
        self,
        tmp_yaml: Callable[[str, str], Path],
    ):
        """from_yaml 应把迁移结果写回原文件: 平铺→嵌套, 且不灌入默认字段。"""
        content = """\
emulator_type: "MuMu"
emulator_start_cmd: "C:/fake/MuMuPlayer.exe"
emulator_name: "127.0.0.1:16384"
"""
        path = tmp_yaml('emu_writeback.yaml', content)
        UserConfig.from_yaml(path)

        rewritten = load_yaml(path)
        # 平铺字段已消失, 值搬进嵌套 emulator 块
        assert 'emulator_type' not in rewritten
        assert 'emulator_start_cmd' not in rewritten
        assert 'emulator_name' not in rewritten
        assert rewritten['emulator'] == {
            'type': 'MuMu',
            'path': 'C:/fake/MuMuPlayer.exe',
            'serial': '127.0.0.1:16384',
        }
        # 关键: 不得写入用户从未定义的 Pydantic 默认字段
        assert 'dock_full_destroy' not in rewritten
        assert 'os_type' not in rewritten
        assert 'repair_manually' not in rewritten

    def test_writeback_idempotent(self, tmp_yaml: Callable[[str, str], Path]):
        """迁移写回后, 再次加载不应再改动文件 (一次性生效)。"""
        content = """\
emulator_type: "MuMu"
emulator_start_cmd: "C:/fake/MuMuPlayer.exe"
emulator_name: "127.0.0.1:16384"
"""
        path = tmp_yaml('emu_idempotent.yaml', content)
        UserConfig.from_yaml(path)
        first = load_yaml(path)
        # 第二次加载: 平铺字段已不在, 无迁移发生, 文件应原样不动
        UserConfig.from_yaml(path)
        assert load_yaml(path) == first

    def test_clean_config_not_rewritten(self, tmp_yaml: Callable[[str, str], Path]):
        """无需迁移的干净配置, 文件字节应原样保留 (不触发写回)。"""
        content = """\
emulator:
  type: "MuMu"
  path: "C:/fake/MuMuPlayer.exe"
  serial: "127.0.0.1:16384"
dock_full_destroy: false
"""
        path = tmp_yaml('clean.yaml', content)
        before = path.read_text(encoding='utf-8')
        UserConfig.from_yaml(path)
        assert path.read_text(encoding='utf-8') == before

    def test_migrate_without_source_path_does_not_persist(self):
        """不传 source_path 时, 迁移只在内存生效 (向后兼容旧调用)。"""
        from autowsgr.infra.config_compat import migrate_raw_config

        out = migrate_raw_config({'emulator_type': 'MuMu'})
        # 内存里照常迁移
        assert out['emulator'] == {'type': 'MuMu'}
        assert 'emulator_type' not in out


# ── LogConfig (setup_logger) ──


class TestSetupLogger:
    """setup_logger 进行基本函数验证。"""

    def test_with_log_dir(self, tmp_path: Path):
        """log_dir 应被自动创建。"""
        from autowsgr.infra import setup_logger

        log_dir = tmp_path / 'logs' / 'sub'
        setup_logger(log_dir=log_dir, level='INFO')
        assert log_dir.exists()
