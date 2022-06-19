if(__name__ == '__main__'):
    import sys
    import os
    sys.path.append(os.path.abspath('./source/python_src'))

from supports.models import *
from supports.io import *
from constants import *
from functools import wraps
from logging import FileHandler, StreamHandler

import logging


__all__ = ['logit', 'logit_time']
time_path = os.path.join(S.LOG_PATH, time.strftime("%Y-%m-%d %H-%M-%S", time.localtime()))
log_path = os.path.join(time_path, 'log.txt')
create_file_with_path(log_path)

std_handler = logging.FileHandler(log_path)
std_handler.setLevel(logging.DEBUG)
std_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)

std_logger = logging.Logger('std_logger', logging.DEBUG)
std_logger.addHandler(std_handler)
std_logger.addHandler(console_handler)


def logit(acc='str', file='log.txt', time_rec=False):
    global std_logger

    def logger(fun):
        @wraps(fun)
        def log_info(*args, **kwargs):
            no_log = kwargs.get('no_log')

            if(no_log is None):
                std_logger.debug("called " + fun.__name__ + '\nargs are' + str(args) + '\nkwargs are' + str(kwargs) + '\n')
                start_time = time.time()
            else:
                kwargs.pop('no_log')

            res = fun(*args, **kwargs)

            if(time_rec and no_log is None):
                std_logger.debug("ended " + fun.__name__ + " take time:" + str(time.time() - start_time) + '\n')

            return res

        return log_info

    return logger


def logit_time():
    return logit(time_rec=True)


@logit()
def hello(name):
    print("hello", name)


if(__name__ == '__main__'):
    hello('huan_yp')
