import copy
import datetime
import threading as th
import time
from collections.abc import Iterable

import cv2
from airtest.core.android import Android

from autowsgr.constants.custom_exceptions import CriticalErr, ImageNotFoundErr
from autowsgr.ocr.ship_name import recognize
from autowsgr.user_config import UserConfig
from autowsgr.utils.api_image import (
    MyTemplate,
    absolute_to_relative,
    crop_rectangle_relative,
    locate_image_center,
    relative_to_absolute,
)
from autowsgr.utils.logger import Logger
from autowsgr.utils.math_functions import cal_dis


class AndroidController:
    """安卓控制器

    用于提供底层的控制接口
    """

    def __init__(
        self,
        dev: Android,
        config: UserConfig,
        logger: Logger,
    ) -> None:
        self.dev = dev
        self.show_android_input = config.show_android_input
        self.delay = config.delay
        self.logger = logger
        self.screen = None
        self.update_screen()
        self.resolution = self.screen.shape[:2]
        self.resolution = self.resolution[::-1]
        self.logger.info(f'resolution:{self.resolution}')

    # ========= 基础命令 =========
    def shell(self, cmd):
        """向链接的模拟器发送 shell 命令
        Args:
            cmd (str):命令字符串
        """
        return self.dev.shell(cmd)

    def get_frontend_app(self):
        """获取前台应用的包名"""
        return self.shell('dumpsys window | grep mCurrentFocus')

    def start_background_app(self, package_name):
        self.dev.start_app(package_name)
        self.shell('input keyevent 3')

    def start_app(self, package_name):
        self.dev.start_app(package_name)

    def stop_app(self, package_name):
        self.dev.stop_app(package_name)

    def list_apps(self):
        """列出所有正在运行的应用"""
        return self.dev.shell('ps')

    def is_game_running(self, app='zhanjian2'):
        """检查一个应用是否在运行

        Args:
            app (str, optional): 应用名, 默认为 "战舰少女R".

        Returns:
            bool:
        """
        return app in self.list_apps()

    # ========= 输入控制信号 =========
    def text(self, t):
        """输入文本
        需要焦点在输入框时才能输入
        """
        if hasattr(self, 'first_type') and self.first_type:
            self.logger.debug('第一次尝试输入, 测试中...')
            self.dev.text('T')
            time.sleep(0.5)
            self.dev.shell('input keyevent 67')
            self.first_type = False
        self.logger.debug(f'正在输入: {t}')
        self.dev.text(t)

    def relative_click(self, x, y, times=1, delay=0.5, enable_subprocess=False) -> th.Thread | None:
        """点击模拟器相对坐标 (x,y).
        Args:
            x,y:相对坐标
            delay:点击后延时(单位为秒)
            enable_subprocess:是否启用多线程加速
            Note:
                if 'enable_subprocess' is True,arg 'times' must be 1
        Returns:
            enable_subprocess == False:None
            enable_subprocess == True:A class threading.Thread refers to this click subprocess
        """
        if self.show_android_input:
            self.logger.debug(f'click ({x:.3f} {y:.3f})')
        x, y = relative_to_absolute((x, y), self.resolution)

        if times < 1:
            raise ValueError("invalid arg 'times' " + str(times))
        if delay < 0:
            raise ValueError("arg 'delay' should be positive or 0")
        if enable_subprocess and times != 1:
            raise ValueError(
                "subprocess enabled but arg 'times' is not 1 but " + str(times),
            )
        if enable_subprocess:
            p = th.Thread(target=lambda: self.shell(f'input tap {x!s} {y!s}'))
            p.start()
            return p

        for _ in range(times):
            self.shell(f'input tap {x!s} {y!s}')
            time.sleep(delay * self.delay)
        return None

    def click(self, x, y, times=1, delay=0.3, enable_subprocess=False):
        """点击模拟器相对坐标 (x,y).
        Args:
            x,y:相对横坐标  (相对 960x540 屏幕)
            delay:点击后延时(单位为秒)
            enable_subprocess:是否启用多线程加速
            Note:
                if 'enable_subprocess' is True,arg 'times' must be 1
        Returns:
            enable_subprocess == False:None
            enable_subprocess == True:A class threading.Thread refers to this click subprocess
        """
        x, y = absolute_to_relative((x, y), (960, 540))
        self.relative_click(x, y, times, delay, enable_subprocess)

    # ===========图像函数============
    def recognize_screen_relative(self, left, top, right, bottom, update=False):
        if update:
            self.update_screen()
        return recognize(
            crop_rectangle_relative(self.screen, left, top, right - left, bottom - top),
        )

    def relative_swipe(self, x1, y1, x2, y2, duration=0.5, delay=0.5):
        """匀速滑动模拟器相对坐标 (x1, y1) 到 (x2, y2).
        Args:
            x1, y1, x2, y2: 相对坐标
            duration: 滑动总时间
            delay: 滑动后延时(单位为秒)
        """
        if delay < 0:
            raise ValueError("arg 'delay' should be positive or 0")
        x1, y1 = relative_to_absolute((x1, y1), self.resolution)
        x2, y2 = relative_to_absolute((x2, y2), self.resolution)
        duration = int(duration * 1000)
        input_str = f'input swipe {x1!s} {y1!s} {x2!s} {y2!s} {duration}'
        if self.show_android_input:
            self.logger.debug(input_str)
        self.shell(input_str)
        time.sleep(delay)

    def swipe(self, x1, y1, x2, y2, duration=0.5, delay=0.5):
        """匀速滑动模拟器相对坐标 (x1,y1) 到 (x2,y2).
        Args:
            x1, y1, x2, y2:相对坐标 (960x540 屏幕)
            duration: 滑动总时间
            delay: 滑动后延时(单位为秒)
        """
        x1, y1 = absolute_to_relative((x1, y1), (960, 540))
        x2, y2 = absolute_to_relative((x2, y2), (960, 540))
        self.relative_swipe(x1, y1, x2, y2, duration, delay)

    def relative_long_tap(self, x, y, duration=1, delay=0.5):
        """长按相对坐标 (x, y)
        Args:
            x, y: 相对坐标
            duration (int, optional): 长按时间(秒). Defaults to 1.
            delay (float, optional): 操作后等待时间(秒). Defaults to 0.5.
        """
        if delay < 0:
            raise ValueError("arg 'delay' should be positive or 0")
        if duration <= 0.2:
            raise ValueError(
                "duration time too short,arg 'duration' should greater than 0.2",
            )
        x, y = relative_to_absolute((x, y), self.resolution)
        self.swipe(x, y, x, y, duration=duration, delay=delay)

    def long_tap(self, x, y, duration=1, delay=0.5):
        """长按相对坐标 (x,y)
        Args:
            x,y: 相对 (960x540 屏幕) 横坐标
            duration (int, optional): 长按时间(秒). Defaults to 1.
            delay (float, optional): 操作后等待时间(秒). Defaults to 0.5.
        """
        x, y = absolute_to_relative((x, y), (960, 540))
        self.relative_long_tap(x, y, duration, delay)

    # ======== 屏幕相关 ========
    def update_screen(self):
        start_time = time.time()
        while (screen := self.dev.snapshot(quality=99)) is None:
            if time.time() - start_time > 10:
                raise CriticalErr('截图持续返回 None，模拟器可能已经失去响应')
            time.sleep(0.1)
        self.screen = screen

    def get_screen(self, resolution=(1280, 720), need_screen_shot=True):
        """获取屏幕图片

        return (ndarray): 宽x长 array[720][1280]
        """
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
        r"""检查像素点是否满足要求
        Args:
            position (_type_): (x, y) 坐标, x 是长, 相对 960x540 的值, x \in [0, 960)

            bgr_color (_type_): 三元组, 顺序为 blue green red, 值为像素值

            distance (int, optional): 最大相差欧氏距离. Defaults to 30.

            screen_shot (bool, optional): 是否重新截图. Defaults to False.
        return:
            bool:是否满足要求
        """
        color = self.get_pixel(*position, screen_shot)
        color.reverse()
        return cal_dis(color, bgr_color) < distance**2

    def locate_center_on_screen(
        self,
        query: MyTemplate,
        confidence=0.85,
        this_methods=None,
    ):
        """从屏幕中找出和模板图像匹配度最高的矩阵区域的中心坐标
            参考 locate_image_center
        Returns:
            如果找到返回一个二元组表示绝对坐标

            否则返回 None
        """
        if this_methods is None:
            this_methods = ['tpl']
        return locate_image_center(self.screen, query, confidence, this_methods)

    def get_image_position(
        self,
        image,
        need_screen_shot=True,
        confidence=0.85,
        this_methods=None,
    ):
        """从屏幕中找出和多张模板图像匹配度超过阈值的矩阵区域的中心坐标,如果有多个,返回第一个
            参考 locate_center_on_screen
        Args:
            need_screen_shot (int, optional): 是否重新截取屏幕. Defaults to 1.
        Returns:
            如果找到:返回一个二元组表示相对坐标 (相对 960x540 屏幕)

            否则返回 None
        """
        if this_methods is None:
            this_methods = ['tpl']
        images = image
        if not isinstance(images, Iterable):
            images = [images]
        if need_screen_shot:
            self.update_screen()
        for image in images:
            res = self.locate_center_on_screen(image, confidence, this_methods)
            if res is not None:
                rel_pos = absolute_to_relative(res, self.resolution)
                return relative_to_absolute(rel_pos, (960, 540))
        return None

    def image_exist(
        self,
        images,
        need_screen_shot=True,
        confidence=0.85,
        this_methods=None,
    ):
        """判断图像是否存在于屏幕中
        Returns:
            bool:如果存在为 True 否则为 False
        """
        if this_methods is None:
            this_methods = ['tpl']
        if not isinstance(images, list):
            images = [images]
        if need_screen_shot:
            self.update_screen()
        return any(
            self.get_image_position(image, False, confidence, this_methods) is not None
            for image in images
        )

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
            this_methods = ['tpl']
        if timeout < 0:
            raise ValueError("arg 'timeout' should at least be 0 but is ", str(timeout))
        start_time = time.time()
        while True:
            x = self.get_image_position(image, True, confidence, this_methods)
            if x is not None:
                time.sleep(after_get_delay)
                return x
            if time.time() - start_time > timeout:
                time.sleep(gap)
                return False
            time.sleep(gap)

    def wait_images(
        self,
        images=None,
        confidence=0.85,
        gap=0.15,
        after_get_delay=0,
        timeout=10,
    ):
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
        elif isinstance(images, list | tuple) and isinstance(images[0], MyTemplate):
            images = list(enumerate(images))  # 把列表转化为元组
        # TODO: 后续优化此内容，当图片结尾有数字的时候会生成一个列表，也就是列表里面嵌套列表，先前不支持此类型
        elif isinstance(images, list | tuple) and isinstance(images[0], list | tuple):
            images = list(enumerate(images))
        elif isinstance(images, dict):
            images = images.items()
        else:
            images = images.__dict__.items()

        start_time = time.time()
        while True:
            self.update_screen()
            for res, image in images:
                if self.image_exist(image, False, confidence):
                    time.sleep(after_get_delay)
                    return res
            time.sleep(gap)
            if time.time() - start_time > timeout:
                return None

    def wait_images_position(
        self,
        images=None,
        confidence=0.85,
        gap=0.15,
        after_get_delay=0,
        timeout=10,
    ):
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
        return self.get_image_position(images[rank], False, confidence)

    def click_image(self, image, must_click=False, timeout=0, delay=0.5):
        """点击一张图片的中心位置

        Args:
            image (MyTemplate): 目标图片

            must_click (bool, optional): 如果为 True,点击失败则抛出异常. Defaults to False.

            timeout (int, optional): 等待延时. Defaults to 0.

            delay (float, optional): 点击后延时. Defaults to 0.5.

        Raises:
            NotFoundErr: 如果在 timeout 时间内未找到则抛出该异常
        Returns:
            bool:如果找到图片返回匹配位置，未找到则返回None
        """
        pos = self.wait_images_position(image, gap=0.03, timeout=timeout)
        if pos is None:
            if not must_click:
                return False
            raise ImageNotFoundErr(f'Target image not found:{image.filepath!s}')

        self.click(*pos, delay=delay)
        return pos

    def click_images(self, images, must_click=False, timeout=0, delay=0.5):
        """点击一些图片中第一张出现的,如果有多个,点击第一个
        Returns:
            bool:如果找到图片返回匹配位置，未找到则返回None
        """
        return self.click_image(images, must_click, timeout, delay)

    def log_screen(
        self,
        need_screen_shot=False,
        resolution=(960, 540),
        ignore_existed_image=True,
        name=None,
    ):
        """向默认数据记录路径记录当前屏幕数据,带时间戳保存,960x540大小
        Args:
            need_screen_shot (bool, optional): 是否新截取一张图片. Defaults to False.
        """
        if need_screen_shot:
            self.update_screen()
        screen = copy.deepcopy(self.screen)
        screen = cv2.resize(screen, resolution)
        if name is None:
            self.logger.log_image(
                image=screen,
                name=datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S'),
                ignore_existed_image=ignore_existed_image,
            )
        else:
            self.logger.log_image(
                image=screen,
                name=name,
                ignore_existed_image=ignore_existed_image,
            )
