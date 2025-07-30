import logging
from typing import Any

from airtest.core.settings import Settings as ST  # noqa

from autowsgr.configs import (
    DailyAutomationConfig,
    DecisiveBattleConfig,
    LoggerConfig,
    OCRConfig,
    TimerConfig,
    UserConfig,
)
from autowsgr.fight.decisive_battle import DecisiveBattle
from autowsgr.game.build import BuildManager
from autowsgr.scripts.daily_api import DailyOperation
from autowsgr.timer import Timer
from autowsgr.timer.backends.ocr_backend import EasyocrBackend, PaddleOCRBackend
from autowsgr.types import LogSource, OcrBackend
from autowsgr.utils.io import yaml_to_dict
from autowsgr.utils.logger import Logger
from autowsgr.utils.update import check_for_updates


def get_config(settings_path: str | None = None) -> UserConfig:
    """获取配置文件, 如果没有则返回默认配置
    :param settings_path: 配置文件路径
    :return: 配置对象
    """
    # config
    config_dict: dict[str, Any] = {} if settings_path is None else yaml_to_dict(settings_path)
    return UserConfig.from_dict(config_dict)


def init_logger(config: LoggerConfig) -> Logger:
    """初始化日志记录器
    :param config: 配置对象
    :return: 日志记录器
    """
    # logger
    logging.getLogger('airtest').setLevel(logging.ERROR)
    return Logger(config)


def init_ocr(config: OCRConfig, logger: Logger) -> EasyocrBackend | PaddleOCRBackend:
    """初始化OCR后端
    :param config: 配置对象
    :param logger: 日志记录器
    :return: OCR后端对象
    """
    match config.ocr_backend:
        case OcrBackend.easyocr:
            ocr_backend = EasyocrBackend(config, logger)
        case OcrBackend.paddleocr:
            ocr_backend = PaddleOCRBackend(config, logger)
    logger.info(LogSource.no_source, 'OCR 后端初始化成功')
    return ocr_backend


class Launcher:
    timer: Timer
    daily_automation: DailyAutomationConfig
    decisive_battle: DecisiveBattleConfig
    plan_tree: dict

    def __init__(self, config: UserConfig) -> None:
        """启动脚本, 返回一个 Timer 记录器.
        :如果模拟器没有运行, 会尝试启动模拟器,
        :如果游戏没有运行, 会自动启动游戏,
        :如果游戏在后台, 会将游戏转到前台
        Returns:
            Timer: 该模拟器的记录器
        """
        self.daily_automation = config.daily_automation
        self.decisive_battle = config.decisive_battle

        config.pprint()
        # airtest全局设置
        ST.CVSTRATEGY = ['tpl']

        if config.check_update:
            check_for_updates()

        logger = init_logger(LoggerConfig.from_user_config(config))
        logger.save_config(config)
        ocr_backend = init_ocr(OCRConfig.from_user_config(config), logger)

        timer_config = TimerConfig.from_user_config(config)
        self.timer = Timer(timer_config, logger, ocr_backend)
        self.plan_tree = self.timer.plan_tree
        self.timer.port.factory = BuildManager(self.timer)

    def run_daily_automation(self) -> None:
        """运行日常自动化脚本"""
        if self.daily_automation is not None:
            daily_operation = DailyOperation(self.timer, self.daily_automation)
            daily_operation.run()
        else:
            self.timer.logger.warning(LogSource.no_source, '未设置日常任务，请检查配置文件')

    def run_decisive_battle(self, times: int = 1) -> None:
        """运行决战脚本"""
        if self.decisive_battle is not None:
            decisive_battle = DecisiveBattle(self.timer, self.decisive_battle)
            decisive_battle.run_for_times(times)
        else:
            self.timer.logger.warning(LogSource.no_source, '未设置决战任务，请检查配置文件')


def start_script(settings_path: str) -> Launcher:
    """从配置文件路径创建 Launcher 对象"""
    config = get_config(settings_path)
    return Launcher(config)
