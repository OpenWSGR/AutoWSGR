import datetime
import os
from types import SimpleNamespace as SN

import keyboard as kd

from AutoWSGR.controller.run_timer import Timer
from AutoWSGR.utils.io import recursive_dict_update, yaml_to_dict
from AutoWSGR.utils.new_logger import Logger

event_pressed = set()
script_end = 0


def lencmp(s1, s2):
    if (len(s1) < len(s2)):
        return 1
    if (len(s1) > len(s2)):
        return -1
    return 0


def listener(event: kd.KeyboardEvent):
    on_press = event_pressed
    if (event.event_type == 'down'):
        if (event.name in on_press):
            return
        on_press.add(event.name)
    if (event.event_type == 'up'):
        on_press.discard(event.name)

    if ('ctrl' in on_press and 'alt' in on_press and 'c' in on_press):
        global script_end
        script_end = 1
        print("Script end by user request")
        quit()


def start_script(settings_path=None):
    """启动脚本,返回一个 Timer 记录器

    Returns:
        Timer: 该模拟器的记录器
    """
    config = yaml_to_dict(os.path.join(os.path.dirname(__file__), "data", "default_settings.yaml"))
    if settings_path is not None:
        user_settings = yaml_to_dict(settings_path)
        config = recursive_dict_update(config, user_settings)

    # set logger
    config['log_dir'] = os.path.join(config['LOG_PATH'], datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    os.makedirs(config['log_dir'], exist_ok=True)
    logger = Logger(config)

    config = SN(**config)
    timer = Timer(config, logger)
    config_str = logger.save_config(config)

    return timer
