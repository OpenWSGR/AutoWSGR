"""测试配置系统与日志工具。"""

import pytest
from pathlib import Path

from autowsgr.infra.config import (
    BattleConfig,
    ConfigManager,
    DecisiveBattleConfig,
    EmulatorConfig,
    FightConfig,
    LogConfig,
    UserConfig,
)
from autowsgr.types import (
    DestroyShipWorkMode,
    EmulatorType,
    OSType,
    RepairMode,
)


# ── EmulatorConfig ──


class TestEmulatorConfig:
    def test_from_dict(self):
        cfg = EmulatorConfig.model_validate({"type": "蓝叠", "serial": "127.0.0.1:5555"})
        assert cfg.type == EmulatorType.bluestacks
        assert cfg.serial == "127.0.0.1:5555"


# ── LogConfig ──


class TestLogConfig:
    def test_dir_auto_generated(self):
        cfg = LogConfig()
        assert cfg.dir is not None
        assert str(cfg.root) in str(cfg.dir)


# ── DecisiveBattleConfig ──


class TestDecisiveBattleConfig:
    def test_invalid_chapter(self):
        with pytest.raises(Exception):
            DecisiveBattleConfig(chapter=0)


# ── UserConfig ──


class TestUserConfig:
    def test_emulator_serial_auto_resolved(self):
        """非 WSL 环境下 serial 应被自动填充。"""
        cfg = UserConfig()
        if cfg.os_type != OSType.linux:
            assert cfg.emulator.serial is not None

    def test_from_yaml(self, tmp_yaml):
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
        path = tmp_yaml("config.yaml", content)
        cfg = UserConfig.from_yaml(path)
        assert cfg.emulator.type == EmulatorType.bluestacks
        assert cfg.emulator.serial == "127.0.0.1:5555"
        assert cfg.delay == 2.0
        assert cfg.dock_full_destroy is False

    def test_with_daily_automation(self, tmp_yaml):
        content = """\
emulator:
  type: "雷电"
  serial: "emulator-5554"
  path: "C:/fake/dnplayer.exe"
daily_automation:
  auto_exercise: false
  battle_type: "简单航母"
"""
        path = tmp_yaml("daily.yaml", content)
        cfg = UserConfig.from_yaml(path)
        assert cfg.daily_automation is not None
        assert cfg.daily_automation.auto_exercise is False
        assert cfg.daily_automation.battle_type == "简单航母"

    def test_with_decisive_battle(self, tmp_yaml):
        content = """\
emulator:
  type: "雷电"
  serial: "emulator-5554"
  path: "C:/fake/dnplayer.exe"
decisive_battle:
  chapter: 5
  repair_level: 2
"""
        path = tmp_yaml("decisive.yaml", content)
        cfg = UserConfig.from_yaml(path)
        assert cfg.decisive_battle is not None
        assert cfg.decisive_battle.chapter == 5
        assert cfg.decisive_battle.repair_level == 2

    def test_destroy_ship_config(self, tmp_yaml):
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
        path = tmp_yaml("destroy.yaml", content)
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
        modes = [RepairMode.moderate_damage, RepairMode.severe_damage] + [RepairMode.moderate_damage] * 4
        cfg = FightConfig(repair_mode=modes)
        assert cfg.repair_mode == modes


class TestBattleConfig:
    def test_default_repair_mode(self):
        cfg = BattleConfig()
        assert isinstance(cfg.repair_mode, list)
        assert all(r == RepairMode.moderate_damage for r in cfg.repair_mode)


# ── ConfigManager ──


class TestConfigManager:
    def test_load_existing_file(self, tmp_yaml):
        content = """\
emulator:
  type: "MuMu"
  serial: "127.0.0.1:16384"
  path: "C:/fake/MuMuPlayer.exe"
delay: 2.5
"""
        path = tmp_yaml("settings.yaml", content)
        cfg = ConfigManager.load(path)
        assert cfg.emulator.type == EmulatorType.mumu
        assert cfg.delay == 2.5

    def test_load_nonexistent_returns_default(self, tmp_path: Path):
        cfg = ConfigManager.load(tmp_path / "no_such_file.yaml")
        assert isinstance(cfg, UserConfig)
        assert cfg.delay == 1.5


# ── LogConfig (setup_logger) ──


class TestSetupLogger:
    """setup_logger 进行基本函数验证。"""

    def test_with_log_dir(self, tmp_path: Path):
        """log_dir 应被自动创建。"""
        from autowsgr.infra.logger import setup_logger

        log_dir = tmp_path / "logs" / "sub"
        setup_logger(log_dir=log_dir, level="INFO")
        assert log_dir.exists()
