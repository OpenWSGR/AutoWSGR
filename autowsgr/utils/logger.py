import json
import os
from datetime import datetime

from loguru import logger

from autowsgr.utils.io import save_image


class Logger:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.log_dir = config['log_dir']
        log_level = config.get('log_level', 'INFO')
        self.log_level = log_level

    def _configure_logger(self, log_level: str | int) -> None:

        # 自定义格式化器
        def custom_format(record):
            level = record['level'].name

            # 绿色：32，红色：31，黄色：33，蓝色：34，淡蓝色：36，清除：0
            if level == 'INFO':
                return '\x1b[32m{time:HH:mm:ss} \x1b[36mautowsgr \x1b[32m{level:^7}\x1b[0m| {message}\n'
            if level == 'ERROR':
                return '\x1b[32m{time:HH:mm:ss} \x1b[36mautowsgr \x1b[31m{level:^7}\x1b[0m| {message}\n'
            if level == 'DEBUG':
                return '\x1b[32m{time:HH:mm:ss} \x1b[36mautowsgr \x1b[0m{level:^7}| {message}\n'
            if level == 'WARNING':
                return '\x1b[32m{time:HH:mm:ss} \x1b[36mautowsgr \x1b[33m{level:^7}\x1b[0m| {message}\n'
            return '\x1b[32m{time:HH:mm:ss} \x1b[36mautowsgr \x1b[31m{level:^7}| {message}\n'

        # 添加文件日志记录器
        logger.add(
            os.path.join(self.log_dir, 'log_{time}.log'),
            level=log_level,
            colorize=True,
            format='{time:HH:mm:ss} autowsgr {level:^7}| {message}',
            catch=True,
            retention='1 week',
        )

        # 添加控制台日志记录器
        # logger.add(
        #    sys.stdout,
        #    level=log_level,
        #    colorize=True,
        #    format="<green>{time:HH:mm:ss}</green> <level>{level}</level> <cyan>autowsgr:</cyan> <level>{message}</level>",
        #    catch=True,
        # )

        # 添加控制台日志记录器
        logger.add(
            lambda msg: print(msg, end=''),
            level=log_level,
            colorize=True,
            format=custom_format,
            catch=True,
        )

    def save_config(self, config):
        # write config file
        config_str = json.dumps(
            vars(config),
            ensure_ascii=False,
            indent=4,
            sort_keys=True,
        )
        with open(
            os.path.join(self.log_dir, 'config.json'),
            'w',
            encoding='utf-8',
        ) as f:
            f.write(config_str)
        return config_str

    def reset_level(self):
        logger.remove()
        self._configure_logger(self.log_level)

    def debug(self, *args):
        logger.debug(str(args))

    def info(self, string):
        logger.info(string)
        # st.write(string)

    def warning(self, string):
        logger.warning('===================WARNING===================')
        logger.warning(string)
        logger.warning('====================END====================')
        # st.write(string)

    def error(self, string):
        logger.error('===================ERROR===================')
        logger.error(string)
        logger.error('====================END====================')

    def log_image(
        self,
        image,
        name=None,
        ignore_existed_image=False,
    ):
        """向默认数据记录路径记录图片
        Args:
            image: 图片,PIL.Image.Image 格式或者 numpy.ndarray 格式
            name (str): 图片文件名
        """
        if name is None:
            name = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

        if 'png' not in name and 'PNG' not in name:
            name += '.PNG'
        path = os.path.join(self.log_dir, name)

        save_image(
            path=path,
            image=image,
            ignore_existed_image=ignore_existed_image,
        )
        self.info(f'图片已保存至{path}')
