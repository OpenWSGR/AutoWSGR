"""基础设施层 — 日志、配置、异常体系、文件工具。"""

from .config import (
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
from .exceptions import (
    ActionFailedError,
    AutoWSGRError,
    ConfigError,
    CriticalError,
    DockFullError,
    EmulatorConnectionError,
    EmulatorError,
    EmulatorNotFoundError,
    GameError,
    ImageNotFoundError,
    NavigationError,
    NetworkError,
    OCRError,
    PageNotFoundError,
    ResourceError,
    UIError,
    VisionError,
)
from .file_utils import load_yaml, merge_dicts, save_yaml
from .logger import save_image, setup_logger

__all__ = [
    # config
    "AccountConfig",
    "BattleConfig",
    "ConfigManager",
    "DailyAutomationConfig",
    "DecisiveBattleConfig",
    "EmulatorConfig",
    "ExerciseConfig",
    "FightConfig",
    "LogConfig",
    "NodeConfig",
    "OCRConfig",
    "UserConfig",
    # exceptions
    "ActionFailedError",
    "AutoWSGRError",
    "ConfigError",
    "CriticalError",
    "DockFullError",
    "EmulatorConnectionError",
    "EmulatorError",
    "EmulatorNotFoundError",
    "GameError",
    "ImageNotFoundError",
    "NavigationError",
    "NetworkError",
    "OCRError",
    "PageNotFoundError",
    "ResourceError",
    "UIError",
    "VisionError",
    # file_utils
    "load_yaml",
    "merge_dicts",
    "save_yaml",
    # logger
    "setup_logger",
    "save_image",
]
