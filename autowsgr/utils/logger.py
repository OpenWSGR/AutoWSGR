import json
import logging
import os
import sys

from autowsgr.utils.io import save_image

# import streamlit as st


class Logger:
    def __init__(self, config):
        self.config = config
        self.log_dir = config["log_dir"]
        if "log_level" in config.keys():
            log_level = config["log_level"]
        else:
            log_level = "INFO"
        self.log_level = log_level
        self.console_logger = self._get_logger(log_level)

    def save_config(self, config):
        # write config file
        config_str = json.dumps(vars(config), ensure_ascii=False, indent=4, sort_keys=True)
        with open(os.path.join(self.log_dir, "config.json"), "w", encoding="utf-8") as f:
            f.write(config_str)
        return config_str

    def reset_level(self):
        self.console_logger.setLevel(self.log_level)

    def debug(self, *args):
        self.console_logger.debug(str(args))

    def info(self, string):
        self.console_logger.info(string)
        # st.write(string)

    def warning(self, string):
        self.console_logger.warning("===================WARNING===================")
        self.console_logger.warning(string)
        self.console_logger.warning("====================END====================")
        # st.write(string)

    def error(self, string):
        self.console_logger.error("===================ERROR===================")
        self.console_logger.error(string)
        self.console_logger.error("====================END====================")
        # st.write(string)

    def log_stat(self, key, value, t, tag="train"):
        self.info(f"{tag} {key}: {value:.4f}")

    def log_image(
        self,
        image,
        name,
        ndarray_mode="BGR",
        ignore_existed_image=False,
        *args,
        **kwargs,
    ):
        """向默认数据记录路径记录图片
        Args:
            image: 图片,PIL.Image.Image 格式或者 numpy.ndarray 格式
            name (str): 图片文件名
        """
        if "png" not in name and "PNG" not in name:
            name += ".PNG"
        path = os.path.join(self.log_dir, name)

        save_image(
            path=path,
            image=image,
            ignore_existed_image=ignore_existed_image,
            *args,
            **kwargs,
        )

    def _get_logger(self, log_level="INFO") -> logging.Logger:
        logger = logging.getLogger("autowsgr")
        logger.propagate = False
        logger.handlers = []
        logger.setLevel(log_level)

        # Stream
        ch_formatter = logging.Formatter("[%(levelname)s %(asctime)s %(name)s] %(message)s", "%H:%M:%S")
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(ch_formatter)
        logger.addHandler(ch)

        # File
        self.log_file_path = os.path.join(self.log_dir, "console.log")
        ch = logging.FileHandler(self.log_file_path, encoding="utf-8")
        ch.setFormatter(ch_formatter)
        logger.addHandler(ch)

        return logger
