"""测试配置系统。"""

import pytest
from pathlib import Path

from autowsgr.infra.config import (
    AccountConfig,
    BattleConfig,
    ConfigManager,
    DailyAutomationConfig,
    DecisiveBattleConfig,
    EmulatorConfig,
    ExerciseConfig,
    FightConfig,
    LogConfig,
    NodeConfig,
    OCRConfig,
    UserConfig,
)
from autowsgr.types import (
    DestroyShipWorkMode,
    EmulatorType,
    GameAPP,
    OcrBackend,
    OSType,
    RepairMode,
)


# ── EmulatorConfig ──


class TestEmulatorConfig:
    def test_defaults(self):
        cfg = EmulatorConfig()
        assert cfg.type == EmulatorType.leidian
        assert cfg.path is None
        assert cfg.serial is None
        assert cfg.process_name is None

    def test_from_dict(self):
        cfg = EmulatorConfig.model_validate({"type": "蓝叠", "serial": "127.0.0.1:5555"})
        assert cfg.type == EmulatorType.bluestacks
        assert cfg.serial == "127.0.0.1:5555"

    def test_frozen(self):
        cfg = EmulatorConfig()
        with pytest.raises(Exception):
            cfg.type = EmulatorType.mumu  # type: ignore


# ── AccountConfig ──


class TestAccountConfig:
    def test_defaults(self):
        cfg = AccountConfig()
        assert cfg.game_app == GameAPP.official
        assert cfg.package_name == "com.huanmeng.zhanjian2"

    def test_xiaomi(self):
        cfg = AccountConfig(game_app=GameAPP.xiaomi)
        assert cfg.package_name == "com.hoolai.zjsnr.mi"


# ── OCRConfig ──


class TestOCRConfig:
    def test_defaults(self):
        cfg = OCRConfig()
        assert cfg.backend == OcrBackend.easyocr
        assert cfg.gpu is False


# ── LogConfig ──


class TestLogConfig:
    def test_defaults(self):
        cfg = LogConfig()
        assert cfg.level == "DEBUG"
        assert cfg.root == Path("log")
        assert cfg.dir is not None  # 自动生成

    def test_dir_auto_generated(self):
        cfg = LogConfig()
        assert cfg.dir is not None
        assert str(cfg.root) in str(cfg.dir)


# ── DailyAutomationConfig ──


class TestDailyAutomationConfig:
    def test_defaults(self):
        cfg = DailyAutomationConfig()
        assert cfg.auto_expedition is True
        assert cfg.auto_battle is True
        assert cfg.battle_type == "困难潜艇"
        assert cfg.normal_fight_tasks == []

    def test_custom(self):
        cfg = DailyAutomationConfig(auto_exercise=False, exercise_fleet_id=2)
        assert cfg.auto_exercise is False
        assert cfg.exercise_fleet_id == 2


# ── DecisiveBattleConfig ──


class TestDecisiveBattleConfig:
    def test_defaults(self):
        cfg = DecisiveBattleConfig()
        assert cfg.chapter == 6
        assert len(cfg.level1) > 0
        assert len(cfg.level2) > 0

    def test_invalid_chapter(self):
        with pytest.raises(Exception):
            DecisiveBattleConfig(chapter=0)

    def test_valid_chapter(self):
        cfg = DecisiveBattleConfig(chapter=3)
        assert cfg.chapter == 3


# ── UserConfig ──


class TestUserConfig:
    def test_defaults(self):
        cfg = UserConfig()
        assert isinstance(cfg.emulator, EmulatorConfig)
        assert isinstance(cfg.account, AccountConfig)
        assert isinstance(cfg.ocr, OCRConfig)
        assert isinstance(cfg.log, LogConfig)
        assert isinstance(cfg.os_type, OSType)
        assert cfg.delay == 1.5
        assert cfg.dock_full_destroy is True

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

    def test_frozen(self):
        cfg = UserConfig()
        with pytest.raises(Exception):
            cfg.delay = 3.0  # type: ignore

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
    def test_defaults(self):
        cfg = FightConfig()
        assert cfg.chapter == 1
        assert cfg.fleet_id == 1
        assert cfg.fight_condition == 4

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


class TestExerciseConfig:
    def test_defaults(self):
        cfg = ExerciseConfig()
        assert cfg.selected_nodes == ["player", "robot"]
        assert cfg.exercise_times == 4
        assert cfg.robot is True


# ── NodeConfig ──


class TestNodeConfig:
    def test_defaults(self):
        cfg = NodeConfig()
        assert cfg.formation == 2
        assert cfg.night is False
        assert cfg.proceed is True
        assert cfg.enemy_rules == []


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
