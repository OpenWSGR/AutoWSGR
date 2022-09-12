import datetime
import logging
import os
import time
from functools import wraps

import constants.settings as S
from constants.global_attribute import script_end
from constants.other_constants import INFO1, INFO2, INFO3

from utils.io import create_file_with_path

time_path = os.path.join(S.LOG_PATH, time.strftime("%Y-%m-%d %H-%M-%S", time.localtime()))
log_debug_path = os.path.join(time_path, 'debug.txt')
log_info1_path = os.path.join(time_path, 'info1.txt')
log_info2_path = os.path.join(time_path, 'info2.txt')
log_info3_path = os.path.join(time_path, 'info3.txt')
log_error_path = os.path.join(time_path, 'error.txt')
log_critical_path = os.path.join(time_path, 'critical.txt')

create_file_with_path(log_debug_path)
create_file_with_path(log_info1_path)
create_file_with_path(log_info2_path)
create_file_with_path(log_info3_path)
create_file_with_path(log_error_path)
create_file_with_path(log_critical_path)

std_debug_handler = logging.FileHandler(log_debug_path)
std_debug_handler.setLevel(logging.DEBUG)
std_debug_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

std_info1_handler = logging.FileHandler(log_info1_path)
std_info1_handler.setLevel(INFO1)
std_info1_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

std_info2_handler = logging.FileHandler(log_info2_path)
std_info2_handler.setLevel(INFO2)
std_info2_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

std_info3_handler = logging.FileHandler(log_info3_path)
std_info3_handler.setLevel(INFO3)
std_info3_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

std_error_handler = logging.FileHandler(log_error_path)
std_error_handler.setLevel(logging.ERROR)
std_error_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

std_critical_handler = logging.FileHandler(log_critical_path)
std_critical_handler.setLevel(logging.CRITICAL)
std_critical_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)

std_logger = logging.Logger('std_logger', logging.DEBUG)
std_logger.addHandler(std_debug_handler)
std_logger.addHandler(std_info1_handler)
std_logger.addHandler(std_info2_handler)
std_logger.addHandler(std_info3_handler)
std_logger.addHandler(std_error_handler)
std_logger.addHandler(std_critical_handler)
std_logger.addHandler(console_handler)


def get_time_as_string(accuracy='year'):
    """返回一个字符串时间戳,可以用于文件保存

    Args:
        accuracy (str, optional): 时间戳粒度. Defaults to "year".
            values:
                'year':记录某年某月某日某时刻
                'day':记录某天某时刻
                'second':只记录时刻
    """
    res = "".join([ch for ch in str(datetime.datetime.now()) if ch.isdigit()])
    if (accuracy == 'year'):
        return res
    if (accuracy == 'day'):
        return res[4:]
    if (accuracy == 'second'):
        return res[8:]


def logit(acc='str', level=logging.DEBUG, time_rec=True):
    global std_logger

    def logger(fun):
        @wraps(fun)
        def log_info(*args, **kwargs):
            if (script_end == 1):
                return 'end'

            no_log = kwargs.get('no_log')

            if (no_log is None):
                std_logger.log(level, msg="called " + fun.__name__ + '\nargs are' +
                               str(args) + '\nkwargs are' + str(kwargs) + '\n')
                start_time = time.time()
            else:
                kwargs.pop('no_log')
            try:
                res = fun(*args, **kwargs)
            except Exception as e:
                std_logger.log(logging.ERROR, str(e))
                print(e)
                raise e

            if (time_rec and no_log is None):
                std_logger.log(level, "ended " + fun.__name__ + " take time:" + str(time.time() - start_time) + '\n')

            return res

        return log_info

    return logger


def logit_time():
    return logit(time_rec=True)
 