import copy
import datetime
import os
import time
from typing import Iterable, Tuple

import cv2

from autowsgr.constants.custom_exceptions import ImageNotFoundErr
from autowsgr.constants.image_templates import make_dir_templates
from autowsgr.utils.api_image import MyTemplate, convert_position, locateCenterOnImage
from autowsgr.utils.math_functions import CalcDis
from autowsgr.utils.new_logger import Logger

from .android_controller import AndroidController
from .windows_controller import WindowsController


class Emulator:
    """模拟器管理单位, 可以用于其它游戏, 对 AndroidController 的进一步封装"""

    def __init__(self, config, logger: Logger):
        # 获取设置，初始化windows控制器
        self.config = config
        self.logger = logger
        self.Windows = WindowsController(config.emulator, logger)

        # 获取额外图像数据
        self._add_extra_images()

        # 初始化android控制器
        dev = self.Windows.connect_android()
        self.Android = AndroidController(config, logger, dev)
        self.update_screen()
        self.config.resolution = self.screen.shape[:2]
        self.config.resolution = self.config.resolution[::-1]  # 转换为 （宽x高）
        self.logger.info(f"resolution:{str(self.config.resolution)}")

    # ==========初始化函数==========

    def _add_extra_images(self):
        if "EXTRA_IMAGE_ROOT" in self.config.__dict__ and self.config.EXTRA_IMAGE_ROOT is not None:
            if os.path.isdir(self.config.EXTRA_IMAGE_ROOT):
                self.images = make_dir_templates(self.config.EXTRA_IMAGE_ROOT)
                self.logger.info(f"Extra Images Loaded:{len(self.images)}")
            elif self.config.EXTRA_IMAGE_ROOT is not None:
                self.logger.warning("配置文件参数 EXTRA_IMAGE_ROOT 存在但不是合法的路径")

    # ===========命令函数===========

    def shell(self, cmd, *args, **kwargs):
        """向链接的模拟器发送 adb shell 命令"""
        return self.Android.ShellCmd(cmd)

    def get_frontend_app(self):
        """获取前台应用的包名"""
        return self.shell("dumpsys window | grep mCurrentFocus")

    def start_app(self, package_name):
        """启动应用"""
        self.Android.start_app(package_name)

    def stop_app(self, package_name):
        """停止应用"""
        self.Android.stop_app(package_name)

    def list_apps(self):
        """列出所有正在运行的应用"""
        return self.shell("ps")

    def is_running(self, app="zhanjian2"):
        """检查一个应用是否在运行

        Args:
            app (str, optional): 应用名, 默认为 "战舰少女R".

        Returns:
            bool:
        """

        return "zhanjian2" in self.list_apps()

    # ===========控制函数============

    def text(self, str):
        """输入文本

        需要焦点在输入框时才能输入
        """
        self.Android.text(str)

    def click(self, x, y):
        """点击模拟器坐标
        Args:
            x (int): 相对横坐标(标准为 960x540 大小的屏幕)
            y (int): 相对纵坐标
        Examples:
            >>> emulator=Emulator(config, logger)
            >>> emulator.click(432, 221)
        """
        self.Android.click(x, y, delay=0.1)

    def swipe(self, x0, y0, x1, y1, duration=0.5):
        """从 (x0, y0) 滑动到 (x1, y1)
        Args:
            x0: 相对横坐标(标准为 960x540 大小的屏幕)

            duration (float): 滑动时间, 单位为秒
        """
        self.Android.swipe(x0, y0, x1, y1, duration=duration, delay=0.1)

    # ===========图像函数============

    def update_screen(self):
        """记录现在的屏幕信息,以 numpy.array 格式覆盖保存到 self.screen"""
        self.screen = self.Android.snapshot()

    def get_screen(self, resolution=(1280, 720), need_screen_shot=True):
        if need_screen_shot:
            self.update_screen()
        return cv2.resize(self.screen, resolution)

    def get_pixel(self, x, y, screen_shot=False) -> list:
        """获取当前屏幕相对坐标 (x,y) 处的像素值
        Args:
            x (int): [0, 960)
            y (int): [0, 540)
        Returns:
            list[]: RGB 格式的像素值
        """
        if screen_shot:
            self.update_screen()
        if len(self.screen) != 540:
            self.screen = cv2.resize(self.screen, (960, 540))
        return [self.screen[y][x][2], self.screen[y][x][1], self.screen[y][x][0]]

    def check_pixel(self, position, bgr_color, distance=30, screen_shot=False) -> bool:
        """检查像素点是否满足要求
        Args:
            position (_type_): (x, y) 坐标, x 是长, 相对 960x540 的值, x \in [0, 960)

            bgr_color (_type_): 三元组, 顺序为 blue green red, 值为像素值

            distance (int, optional): 最大相差欧氏距离. Defaults to 30.

            screen_shot (bool, optional): 是否重新截图. Defaults to False.
        """
        color = self.get_pixel(*position, screen_shot)
        color.reverse()
        return CalcDis(color, bgr_color) < distance**2

    def locateCenterOnScreen(self, query: MyTemplate, confidence=0.85, this_methods=None):
        """从屏幕中找出和模板图像匹配度最高的矩阵区域的中心坐标
            参考 locateCenterOnImage
        Returns:
            如果找到返回一个二元组表示绝对坐标

            否则返回 None
        """
        if this_methods is None:
            this_methods = ["tpl"]
        return locateCenterOnImage(self.screen, query, confidence, this_methods)

    def get_image_position(self, image, need_screen_shot=1, confidence=0.85, this_methods=None):
        """从屏幕中找出和多张模板图像匹配度超过阈值的矩阵区域的中心坐标,如果有多个,返回第一个
            参考 locateCenterOnScreen
        Args:
            need_screen_shot (int, optional): 是否重新截取屏幕. Defaults to 1.
        Returns:
            如果找到:返回一个二元组表示相对坐标 (相对 960x540 屏幕)

            否则返回 None
        """
        if this_methods is None:
            this_methods = ["tpl"]
        images = image
        if not isinstance(images, Iterable):
            images = [images]
        if need_screen_shot == 1:
            self.update_screen()
        for image in images:
            res = self.locateCenterOnScreen(image, confidence, this_methods)
            if res is not None:
                return convert_position(res[0], res[1], self.config.resolution, mode="this_to_960")
        return None

    def get_images_position(self, images, need_screen_shot=1, confidence=0.85, this_methods=None):
        """同 get_image_position"""
        if this_methods is None:
            this_methods = ["tpl"]
        return self.get_image_position(images, need_screen_shot, confidence, this_methods)

    def image_exist(self, images, need_screen_shot=1, confidence=0.85, this_methods=None):
        """判断图像是否存在于屏幕中
        Returns:
            bool:如果存在为 True 否则为 False
        """
        if this_methods is None:
            this_methods = ["tpl"]
        if not isinstance(images, list):
            images = [images]
        if need_screen_shot:
            self.update_screen()
        return any(self.get_image_position(image, 0, confidence, this_methods) is not None for image in images)

    def images_exist(self, images, need_screen_shot=1, confidence=0.85, this_methods=None):
        """判断图像是否存在于屏幕中
        Returns:
            bool:如果存在为 True 否则为 False
        """
        if this_methods is None:
            this_methods = ["tpl"]
        return self.image_exist(images, need_screen_shot, confidence, this_methods)

    def wait_image(
        self,
        image: MyTemplate,
        confidence=0.85,
        timeout=10,
        gap=0.15,
        after_get_delay=0,
        this_methods=None,
    ):
        """等待一张图片出现在屏幕中,置信度超过一定阈值(支持多图片)

        Args:
            timeout (int, optional): 最大等待时间. Defaults to 10.
        Returns:
            如果在 timeout 秒内发现,返回一个二元组表示其相对(960x540 屏幕)位置

            否则返回 False
        """
        if this_methods is None:
            this_methods = ["tpl"]
        if timeout < 0:
            raise ValueError("arg 'timeout' should at least be 0 but is ", str(timeout))
        StartTime = time.time()
        while True:
            x = self.get_image_position(image, 1, confidence, this_methods)
            if x != None:
                time.sleep(after_get_delay)
                return x
            if time.time() - StartTime > timeout:
                time.sleep(gap)
                return False
            time.sleep(gap)

    def wait_images(self, images=None, confidence=0.85, gap=0.15, after_get_delay=0, timeout=10):
        """等待一系列图片中的一个在屏幕中出现

        Args:
            images (list, optional): 很多图片,可以是列表或字典. Defaults to [].
            confidence (_type_, optional): 置信度. Defaults to 0.85.
            timeout (int, optional): 最长等待时间. Defaults to 10.

        Raises:
            TypeError: image_list 中有不合法参数

        Returns:
            None: 未找到任何图片
            a number of int: 第一个出现的图片的下标(0-based) if images is a list
            the key of the value: if images is a dict
        """
        if timeout < 0:
            raise ValueError("arg 'timeout' should at least be 0 but is ", str(timeout))
        if images is None:
            return None

        if isinstance(images, MyTemplate):
            images = [(0, images)]
        elif isinstance(images, (list, Tuple)) and isinstance(images[0], MyTemplate):
            images = list(enumerate(images))
        elif isinstance(images, dict):
            images = images.items()

        StartTime = time.time()
        while True:
            self.update_screen()
            for res, image in images:
                if self.image_exist(image, False, confidence):
                    time.sleep(after_get_delay)
                    return res
            time.sleep(gap)
            if time.time() - StartTime > timeout:
                return None

    def wait_images_position(self, images=None, confidence=0.85, gap=0.15, after_get_delay=0, timeout=10):
        """等待一些图片,并返回第一个匹配结果的位置

        参考 wait_images
        """
        if images is None:
            images = []
        if not isinstance(images, Iterable):
            images = [images]
        rank = self.wait_images(images, confidence, gap, after_get_delay, timeout)
        if rank is None:
            return None
        return self.get_image_position(images[rank], 0, confidence)

    def click_image(self, image, must_click=False, timeout=0, delay=0.5):
        """点击一张图片的中心位置

        Args:
            image (MyTemplate): 目标图片

            must_click (bool, optional): 如果为 True,点击失败则抛出异常. Defaults to False.

            timeout (int, optional): 等待延时. Defaults to 0.

            delay (float, optional): 点击后延时. Defaults to 0.5.

        Raises:
            NotFoundErr: 如果在 timeout 时间内未找到则抛出该异常
        """
        pos = self.wait_images_position(image, gap=0.03, timeout=timeout)
        if pos is None:
            if not must_click:
                return False
            else:
                raise ImageNotFoundErr(f"Target image not found:{str(image.filepath)}")

        self.Android.click(*pos, delay=delay)
        return True

    def click_images(self, images, must_click=False, timeout=0, delay=0.5):
        """点击一些图片中第一张出现的,如果有多个,点击第一个
        Returns:
            bool:如果找到图片返回true，未找到则返回false，或者抛出一个异常
        """
        return self.click_image(images, must_click, timeout)

    def log_screen(self, need_screen_shot=False, resolution=(960, 540), name=None):
        """向默认数据记录路径记录当前屏幕数据,带时间戳保存,960x540大小
        Args:
            need_screen_shot (bool, optional): 是否新截取一张图片. Defaults to False.
        """
        if need_screen_shot:
            self.update_screen()
        screen = copy.deepcopy(self.screen)
        screen = cv2.resize(screen, resolution)
        if name is None:
            name = datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        self.logger.log_image(image=screen, name=name)
