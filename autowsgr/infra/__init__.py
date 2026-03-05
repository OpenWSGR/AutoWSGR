"""基础设施层 — 日志、配置、异常体系、文件工具。"""

from .config import (
    AccountConfig,
    BattleConfig,
    ConfigManager,
    DailyAutomationConfig,
    DecisiveBattleConfig,
    DecisiveConfig,
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
from .file_utils import load_yaml, merge_dicts, resolve_plan_path, save_yaml
from .logger import caller_info, get_logger, save_image, setup_logger


__all__ = [
    # config
    'AccountConfig',
    'BattleConfig',
    'ConfigManager',
    'DailyAutomationConfig',
    'DecisiveBattleConfig',
    'EmulatorConfig',
    'ExerciseConfig',
    'FightConfig',
    'LogConfig',
    'NodeConfig',
    'OCRConfig',
    'UserConfig',
    'DecisiveConfig',
    # exceptions
    'ActionFailedError',
    'AutoWSGRError',
    'ConfigError',
    'CriticalError',
    'DockFullError',
    'EmulatorConnectionError',
    'EmulatorError',
    'EmulatorNotFoundError',
    'GameError',
    'ImageNotFoundError',
    'NavigationError',
    'NetworkError',
    'OCRError',
    'PageNotFoundError',
    'ResourceError',
    'UIError',
    'VisionError',
    # file_utils
    'load_yaml',
    'merge_dicts',
    'resolve_plan_path',
    'save_yaml',
    # logger
    'setup_logger',
    'save_image',
    'get_logger',
    'caller_info',
]
