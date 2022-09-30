import copy
import os
import threading as th
import time
from typing import Iterable, Tuple

from airtest.core.cv import ST
from airtest.core.helper import G
from airtest.core.settings import Settings as ST
from constants.custom_expections import (CriticalErr, ImageNotFoundErr,
                                         NetworkErr)
from constants.other_constants import ALL_PAGES, INFO1, INFO2, INFO3, NO
from constants.image_templates import IMG
from constants.settings import S
from utils.api_image import convert_position, locateCenterOnImage, MyTemplate
from utils.io import save_image, write_file
from utils.logger import get_time_as_string, logit
from utils.math_functions import CalcDis

from .android_controller import AndroidController
from .windows_controller import WindowsController

class Emulator():
    """模拟器管理单位,可以用于其它游戏
    """
    def __init__(self):
        self.start_time = time.time()
        self.log_filepre = get_time_as_string()
        self.screen = None
        self.resolution = (960, 540)
        self.device_name = 'emulator-5554'  # 设备名,雷电模拟器默认值
        self.Windows = WindowsController(self.device_name)
        self.Android = AndroidController(self.resolution)
    
    def connect(self, emulator):
        if(not self.Windows.is_android_online()):self.Windows.RestartAndroid()
        self.device_name = emulator
        self.Windows.ConnectAndroid()
        self.update_screen()
        self.resolution = self.screen.shape[:2]
        self.resolution = self.resolution[::-1]
        from utils.logger import time_path
        self.log_filepre = time_path
    
    @logit()
    def update_screen(self, *args, **kwargs):
        """记录现在的屏幕信息,以 numpy.array 格式覆盖保存到 RD.screen
        """
        self.screen = G.DEVICE.snapshot(filename=None, quality=99)

    def get_pixel(self, x, y):
        """获取当前屏幕相对坐标 (x,y) 处的像素值

        Args:
            x (int): [0, 960)
            y (int): [0, 549)

        Returns:
            Tuple(int,int,int): RGB 格式的像素值
        """

        (x, y) = convert_position(x, y, self.resolution)
        return (self.screen[y][x][2], self.screen[y][x][1], self.screen[y][x][0])

    def check_pixel(self, position, bgr_color, distance=30):
        color = self.screen[position[1]][position[0]]
        return CalcDis(color, bgr_color) < distance ** 2

    def locateCenterOnScreen(self, query: MyTemplate, confidence=0.85, this_mehods=["tpl"]):
        """从屏幕中找出和模板图像匹配度最高的矩阵区域的中心坐标
            参考 locateCenterOnImage
        Returns:
            如果找到返回一个二元组表示绝对坐标

            否则返回 None
        """
        return locateCenterOnImage(self.screen, query, confidence, this_mehods)

    @logit()
    def get_image_position(self, image, need_screen_shot=1, confidence=0.85, this_methods=["tpl"]):
        """从屏幕中找出和模板图像匹配度最高的矩阵区域的中心坐标
            参考 locateCenterOnScreen
        Args:
            need_screen_shot (int, optional): 是否重新截取屏幕. Defaults to 1.
        Returns:
            如果找到:返回一个二元组表示相对坐标 (相对 960x540 屏幕)

            否则返回 None
        """
        images = image
        if(not isinstance(images, Iterable)):
            images = [images]
        if (need_screen_shot == 1):
            self.update_screen()
        for image in images:
            res = self.locateCenterOnScreen(image, confidence, this_methods)
            if(res is not None):
                return convert_position(res[0], res[1], self.resolution, mode='this_to_960')
        return None

    def get_images_position(self, images, need_screen_shot=1, confidence=0.85, this_methods=["tpl"]):
        """从屏幕中找出和模板图像匹配度最高的矩阵区域的中心坐标
            参考 locateCenterOnScreen
        Args:
            need_screen_shot (int, optional): 是否重新截取屏幕. Defaults to 1.
        Returns:
            如果找到:返回一个二元组表示相对坐标 (相对 960x540 屏幕)

            否则返回 None
        """
        return self.get_image_position(images, need_screen_shot, confidence, this_methods)

    @logit()
    def image_exist(self, images, need_screen_shot=1, confidence=0.85, this_methods=["tpl"]):
        """判断图像是否存在于屏幕中
        Returns:
            bool:如果存在为 True 否则为 False 
        """
        if not isinstance(images, list):
            images = [images]
        if need_screen_shot:
            self.update_screen()
        return any(self.get_image_position(image, 0, confidence, this_methods, no_log=True) is not None for image in images)
    
    def images_exist(self, images, need_screen_shot=1, confidence=0.85, this_methods=["tpl"]):
        """判断图像是否存在于屏幕中
        Returns:
            bool:如果存在为 True 否则为 False 
        """
        return self.image_exist(images, need_screen_shot, confidence, this_methods)
    
    @logit()
    def wait_image(self, image: MyTemplate, confidence=0.85, timeout=10, gap=.15, after_get_delay=0, this_methods=["tpl"]):
        """等待一张图片出现在屏幕中,置信度超过一定阈值

        Args:
            timeout (int, optional): 最大等待时间. Defaults to 10.
        Returns:
            如果在 timeout 秒内发现,返回一个二元组表示其相对(960x540 屏幕)位置

            否则返回 False
        """
        if (timeout < 0):
            raise ValueError("arg 'timeout' should at least be 0 but is ", str(timeout))
        StartTime = time.time()
        while (True):
            x = self.get_image_position(image, 1, confidence, this_methods, no_log=True)
            if (x != None):
                time.sleep(after_get_delay)
                return x
            if (time.time()-StartTime > timeout):
                time.sleep(gap)
                return False
            time.sleep(gap)

    @logit()
    def wait_images(self, images=[], confidence=0.85, gap=.15, after_get_delay=0, timeout=10, *args, **kwargs):
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
        images = copy.copy(images)
        if (isinstance(images, MyTemplate)):
            images = [images]
        if isinstance(images, (list, Tuple)):
            for i in range(len(images)):
                images[i] = (i, images[i])
        if (isinstance(images, dict)):
            images = images.items()

        if (timeout < 0):
            raise ValueError("arg 'timeout' should at least be 0 but is ", str(timeout))

        StartTime = time.time()
        while (True):
            self.update_screen(no_log=True)
            for res, image in images:
                if (self.image_exist(image, 0, confidence, no_log=True)):
                    time.sleep(after_get_delay)
                    return res
            time.sleep(gap)
            if (time.time() - StartTime > timeout):
                return None

    def wait_images_position(self, images=[], confidence=0.85, gap=.15, after_get_delay=0, timeout=10, *args, **kwargs):
        """等待一些图片,并返回第一个匹配结果的位置
        
        参考 wait_images     
        """
        rank = self.wait_images(images, confidence, gap, after_get_delay, timeout, *args, **kwargs)
        if(rank == None):
            return None
        return self.get_image_position(images[rank], 0, confidence)
    
    @logit(level=INFO1)
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
        pos = self.wait_images_position(image, gap=.03, timeout=timeout)
        if (pos == False):
            if (must_click == False):
                return False
            else:
                raise ImageNotFoundErr("Target image not found:" + str(image.filepath))

        self.Android.click(pos[0], pos[1], delay=delay)
        return True

    def click_image(self, image: MyTemplate, must_click=False, timeout=0, delay=0.5):
        """点击一张图片的中心位置
        Args:
            image (MyTemplate): 目标图片
            must_click (bool, optional): 如果为 True,点击失败则抛出异常. Defaults to False.
            timeout (int, optional): 等待延时. Defaults to 0.
            delay (float, optional): 点击后延时. Defaults to 0.5.

        Raises:
            NotFoundErr: 如果在 timeout 时间内未找到则抛出该异常
        """
        if (timeout < 0):
            raise ValueError("arg 'timeout' should at least be 0 but is ", str(timeout))
        if (delay < 0):
            raise ValueError("arg 'delay' should at least be 0 but is ", str(delay))
        pos = self.wait_image(image, timeout=timeout)
        if (pos == None):
            if (must_click == False):
                return False
            else:
                raise ImageNotFoundErr("Target image not found:" + str(image.filepath))

        self.Android.click(*pos, delay=delay)
        return True
    
    def click_images(self, images, must_click=False, timeout=0, delay=0.5):
        """点击一些图片中第一张出现的,如果有多个,点击第一个
        """
        self.click_image(images, must_click, timeout)
    
    @logit(level=INFO2)
    def ConfirmOperation(self, must_confirm=0, delay=0.5, confidence=.9, timeout=0):
        """等待并点击弹出在屏幕中央的各种确认按钮

        Args:
            must_confirm (int, optional): 是否必须按. Defaults to 0.
            delay (float, optional): 点击后延时(秒). Defaults to 0.5.
            timeout (int, optional): 等待延时(秒),负数或 0 不等待. Defaults to 0.

        Raises:
            ImageNotFoundErr: 如果 must_confirm = True 但是 timeout 之内没找到确认按钮排除该异常
        Returns:
            bool:True 为成功,False 为失败
        """
        pos = self.wait_images(IMG.confirm_image[1:], confidence, timeout=timeout)
        if pos is None:
            if (must_confirm == 1):
                raise ImageNotFoundErr("no confirm image found")
            else:
                return False
        res = self.get_image_position(IMG.confirm_image[pos + 1], 0)
        self.Android.click(res[0], res[1], delay=delay)
        return True

    def log_image(self, image, name, ndarray_mode="BGR", ignore_existed_image=False, *args, **kwargs):
        """向默认数据记录路径记录图片
    Args:
        image: 图片,PIL.Image.Image 格式或者 numpy.ndarray 格式
        name (str): 图片文件名
        """
        if ('png' not in name and 'PNG' not in name):
            name += '.PNG'
        path = os.path.join(self.log_filepre, name)

        save_image(path=path, image=image, ignore_existed_image=ignore_existed_image, *args, **kwargs)

    def log_screen(self, need_screen_shot=False):
        """向默认数据记录路径记录当前屏幕数据,带时间戳保存
        Args:
            need_screen_shot (bool, optional): 是否新截取一张图片. Defaults to False.
        """
        if (need_screen_shot):
            self.update_screen()
        self.log_image(image=self.screen, name=get_time_as_string(accuracy='second')+'screen')

    def log_info(self, info):
        """向默认信息记录文件记录信息自带换行

        Args:
            info (str): 要记录的信息

        """
        write_file(filename=os.path.join(S.LOG_PATH, "log.txt"), contents=info+'\n')

    def log_debug_info(self, info):
        """当调试时向默认信息记录文件记录信息自带换行
        Args:
            info (str): 需要记录的信息
        """
        if (S.DEBUG):
            self.log_info(info)

    