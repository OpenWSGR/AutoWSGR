import datetime
import os
import winreg
from types import SimpleNamespace

import keyboard as kd

import autowsgr
from autowsgr.controller.run_timer import Emulator, Timer
from autowsgr.utils.io import recursive_dict_update, yaml_to_dict
from autowsgr.utils.new_logger import Logger
from autowsgr.utils.update import check_for_updates

event_pressed = set()
script_end = 0


def initialize_logger_and_config(settings_path):
    config = yaml_to_dict(os.path.join(os.path.dirname(autowsgr.__file__), "data", "default_settings.yaml"))
    if settings_path is not None:
        user_settings = yaml_to_dict(settings_path)
        config = recursive_dict_update(config, user_settings)
    else:
        print("========Warning========")
        print(
            f"No user_settings file specified, default settings "
            f"{os.path.join(os.path.dirname(autowsgr.__file__), 'data', 'default_settings.yaml')}"
            f" will be used."
        )
        print("=========End===========")

    # reading the registry for emulator if needed
    if config["emulator"]["start_cmd"] == "":
        print("========Warning========")
        print("No emulator directory provided, reading the registry")
        config["emulator"]["start_cmd"] = get_emulator_path(config["emulator"]["type"])
        print("The emulator directory is " + config["emulator"]["start_cmd"])
        print("=========End===========")

    # set logger
    config["log_dir"] = os.path.join(config["LOG_PATH"], datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    os.makedirs(config["log_dir"], exist_ok=True)
    logger = Logger(config)
    config = SimpleNamespace(**config)
    if config.check_update:
        try:
            check_for_updates()
        except Exception as e:
            print(f"Failed to check for updates: {e}")
    config_str = logger.save_config(config)
    logger.reset_level()
    return config, logger


def start_script(settings_path=None):
    """启动脚本, 返回一个 Timer 记录器.
    :如果模拟器没有运行, 会尝试启动模拟器,
    :如果游戏没有运行, 会自动启动游戏,
    :如果游戏在后台, 会将游戏转到前台
    Returns:
        Timer: 该模拟器的记录器
    """
    # set logger
    config, logger = initialize_logger_and_config(settings_path)
    timer = Timer(config, logger)
    return timer


def start_script_emulator(settings_path=None):
    """启动脚本, 返回一个 Emulator 记录器, 用于操作模拟器
    Returns:
        Emulator: 该模拟器的记录器
    """
    config, logger = initialize_logger_and_config(settings_path)
    emulator = Emulator(config, logger)
    return emulator


def get_emulator_path(emulator_type):
    try:
        if emulator_type == "雷电":
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\leidian\ldplayer9")
            try:
                path, _ = winreg.QueryValueEx(key, "InstallDir")
                return os.path.join(path, "dnplayer.exe")
            except FileNotFoundError:
                print("Path not found")
            finally:
                winreg.CloseKey(key)

        elif emulator_type == "蓝叠 Hyper-V":
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\BlueStacks_nxt_cn")
            try:
                path, _ = winreg.QueryValueEx(key, "InstallDir")
                return os.path.join(path, "HD-Player.exe")
            except FileNotFoundError:
                print("Path not found")
            finally:
                winreg.CloseKey(key)

    except FileNotFoundError:
        print("Emulator not found")
        return None
