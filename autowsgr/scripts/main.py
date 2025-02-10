import logging
from typing import Any

from airtest.core.settings import Settings as ST  # noqa

from autowsgr.configs import UserConfig
from autowsgr.game.build import BuildManager
from autowsgr.timer import Timer
from autowsgr.utils.io import yaml_to_dict
from autowsgr.utils.logger import Logger
from autowsgr.utils.update import check_for_updates


def start_script(settings_path: str | None = None) -> Timer:
    """启动脚本, 返回一个 Timer 记录器.
    :如果模拟器没有运行, 会尝试启动模拟器,
    :如果游戏没有运行, 会自动启动游戏,
    :如果游戏在后台, 会将游戏转到前台
    Returns:
        Timer: 该模拟器的记录器
    """
    # airtest全局设置
    ST.CVSTRATEGY = ['tpl']

    # config
    config_dict: dict[str, Any] = {} if settings_path is None else yaml_to_dict(settings_path)
    config = UserConfig.from_dict(config_dict)
    config.pprint()

    if config.check_update:
        check_for_updates()

    # logger
    logging.getLogger('airtest').setLevel(logging.ERROR)
    logger = Logger(config.log_dir, config.log_level)
    logger.save_config(config)

    timer = Timer(config, logger)
    timer.port.factory = BuildManager(timer)

    return timer
