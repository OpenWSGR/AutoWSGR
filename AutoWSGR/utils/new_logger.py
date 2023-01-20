import json
import logging
import os
import sys

from AutoWSGR.utils.io import save_image

# import wandb



class Logger:
    def __init__(self, config):
        self.config = config
        self.log_dir = config['log_dir']
        log_level = "INFO"
        if config["DEBUG"]:
            log_level = "DEBUG"
        self.console_logger = self._get_logger(log_level)

        # self.use_wandb = config["use_wandb"]

        # if config["use_wandb"] and not config["evaluate"]:
        #     self.wandb_last_log_t = -1
        #     self._setup_wandb(self.log_dir)  # will automatically create "wandb" subfolder

    def save_config(self, config):
        # write config file
        config_str = json.dumps(vars(config), ensure_ascii=False, indent=4, sort_keys=True)
        with open(os.path.join(self.log_dir, "config.json"), "w") as f:
            f.write(config_str)
        return config_str

    # def _setup_wandb(self, directory_name):
    #     group_name = self.config['env']
    #     if 'map_name' in self.config['env_args']:
    #         group_name += '.' + self.config['env_args']['map_name']
    #     job_name = self.config['name'] + self.config.get('remark', '')

    #     wandb.init(project="pymarl-ext",
    #                group=group_name,
    #                job_type=job_name,
    #                dir=directory_name,
    #                reinit=True,
    #                config=self.config)

    def debug(self, *args):
        self.console_logger.debug(str(args))

    def info(self, string):
        self.console_logger.info(string)

    def warning(self, string):
        self.console_logger.warning("===================WARNING===================")
        self.console_logger.warning(string)
        self.console_logger.warning("====================END====================")

    def error(self, string):
        self.console_logger.error("===================ERROR===================")
        self.console_logger.error(string)
        self.console_logger.error("====================END====================")

    def log_stat(self, key, value, t, tag='train'):
        self.info(f"{tag} {key}: {value:.4f}")

        # if self.use_wandb:
        #     if self.wandb_last_log_t != t:
        #         wandb.log({"timesteps": self.wandb_last_log_t})
        #     wandb.log(f"{tag}/{key}", commit=False)
        #     self.wandb_last_log_t = t

    def log_image(self, image, name, ndarray_mode="BGR", ignore_existed_image=False, *args, **kwargs):
        """向默认数据记录路径记录图片
    Args:
        image: 图片,PIL.Image.Image 格式或者 numpy.ndarray 格式
        name (str): 图片文件名
        """
        if ('png' not in name and 'PNG' not in name):
            name += '.PNG'
        path = os.path.join(self.log_dir, name)

        save_image(path=path, image=image, ignore_existed_image=ignore_existed_image, *args, **kwargs)

    def _get_logger(self, log_level="INFO") -> logging.Logger:
        logger = logging.getLogger()
        logger.handlers = []
        logger.setLevel(log_level)

        # Stream
        ch_formatter = logging.Formatter('[%(levelname)s %(asctime)s %(name)s] %(message)s', '%H:%M:%S')
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(ch_formatter)
        logger.addHandler(ch)

        # File
        self.log_file_path = os.path.join(self.log_dir, "console.log")
        ch = logging.FileHandler(self.log_file_path)
        ch.setFormatter(ch_formatter)
        logger.addHandler(ch)

        return logger
