import os
import subprocess

from airtest.core.error import AdbError

from autowsgr.constants.data_roots import TUNNEL_ROOT
from autowsgr.game.build import BuildManager
from autowsgr.timer import Timer
from autowsgr.user_config import UserConfig
from autowsgr.utils.io import yaml_to_dict
from autowsgr.utils.logger import Logger
from autowsgr.utils.update import check_for_updates


def start_script(settings_path=None) -> Timer:
    """启动脚本, 返回一个 Timer 记录器.
    :如果模拟器没有运行, 会尝试启动模拟器,
    :如果游戏没有运行, 会自动启动游戏,
    :如果游戏在后台, 会将游戏转到前台
    Returns:
        Timer: 该模拟器的记录器
    """
    # config
    config_dict = yaml_to_dict(settings_path)
    config = UserConfig.from_dict(config_dict)
    config.pprint()

    if config.check_update:
        check_for_updates()

    # logger
    logger = Logger(config.log_dir, config.log_level)
    logger.save_config(config)

    try:
        timer = Timer(config, logger)
        timer.port.factory = BuildManager(timer)
    except AdbError:
        adb_exe = os.path.join(os.path.dirname(TUNNEL_ROOT), 'adb', 'adb.exe')
        subprocess.run([adb_exe, 'devices', '-l'])
        logger.warning('Adb 连接模拟器失败, 正在清除原有连接并重试')
        timer = Timer(config, logger)

    return timer
