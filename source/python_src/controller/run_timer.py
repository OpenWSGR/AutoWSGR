import copy
import os
import time
from typing import Tuple

import numpy as np
from airtest.core.cv import (MATCHING_METHODS, ST, InvalidMatchingMethodError,
                             TargetPos, Template)
from airtest.core.helper import G
from airtest.core.settings import Settings as ST
from constants import settings as S
from constants.custom_expections import ImageNotFoundErr
from constants.image_templates import ErrorImages, SymbolImage, BackImage, GameUI, IdentifyImages
from constants.other_constants import INFO1, INFO2, NO, ALL_UI
from constants.ui import Node, load_game_ui
from PIL import Image as PIM
from utils.api_image import convert_position
from utils.io import save_image, write_file
from utils.logger import get_time_as_string, logit
from utils.math_functions import CalcDis

from .android_controller import AndroidController
from .windows_controller import WindowsController


class Timer():
    """ 程序运行记录器,用于记录和传递部分数据,同时用于区分多开 """

    def __init__(self):
        """Todo
        参考银河远征的战斗模拟写一个 Ship 类,更好的保存信息
        """
        self.start_time = time.time()
        self.log_filepre = get_time_as_string()
        self.screen = None
        self.resolution = (960, 540)
        self.now_page = None
        self.ui = load_game_ui()
        # self.ship_position = (0, 0)
        # self.ship_point = "A"  # 常规地图战斗中,当前战斗点位的编号
        # self.chapter = 1  # 章节名,战役为 'battle', 演习为 'exercise'
        # self.node = 1  # 节点名
        self.ship_status = [0, 0, 0, 0, 0, 0, 0]  # 我方舰船状态
        self.enemy_type_count = {}  # 字典,每种敌人舰船分别有多少
        self.now_page = None  # 当前所在节点名
        self.device_name = 'emulator-5554'  # 设备名,雷电模拟器默认值
        self.expedition_status = None  # 远征状态记录器
        self.team = 1  # 当前队伍名
        self.defaul_decision_maker = None  # 默认决策模块
        self.ammo = 10
        self.oil = 10
        self.resources = None
        self.last_error_time = time.time() - 1800
        self.decisive_battle_data = None
        """
        以上时能用到的
        以下是暂时用不到的
        """

        self.friends = []
        self.enemies = []
        self.enemy_ship_type = [None, NO, NO, NO, NO, NO, NO]
        self.friend_ship_type = [None, NO, NO, NO, NO, NO, NO]
        self.defaul_repair_logic = None
        self.fight_result = None
        self.last_mission_compelted = 0
        self.last_expedition_checktime = time.time()

        # DH新增，模块化
        self.Android = AndroidController(self.resolution)
        self.Windows = WindowsController(self.device_name)

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

    def __str__(self):
        return "this is a timer"

    @logit()
    def UpdateScreen(self, *args, **kwargs):
        """记录现在的屏幕信息,以 numpy.array 格式覆盖保存到 RD.screen
        """
        self.screen = G.DEVICE.snapshot(filename=None, quality=ST.SNAPSHOT_QUALITY)

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
            self.UpdateScreen()
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

    @logit()
    def intergrative_page_identify(self):
        positions = [(171, 47), (300, 47), (393, 47), (504, 47), (659, 47)]
        for i, position in enumerate(positions):
            if (PixelChecker(self, position, (225, 130, 16))):
                return i + 1

    @logit()
    def identify_page(self, name, need_screen_shot=True):
        if need_screen_shot:
            self.UpdateScreen()

        if (name == 'main_page') and (self.identify_page('options_page', 0)):
            return False
        if (name == 'map_page') and ((self.intergrative_page_identify() != 1 or PixelChecker(self, (35, 297), (47, 253, 226)))):
            return False
        if (name == 'build_page') and (self.intergrative_page_identify() != 1):
            return False
        if (name == 'develop_page') and (self.intergrative_page_identify() != 3):
            return False

        return any(ImagesExist(self, template, 0) for template in IdentifyImages[name])

    @logit()
    def wait_pages(self, names, timeout=5, gap=.1, after_wait=0.1):
        start_time = time.time()
        if (isinstance(names, str)):
            names = [names]
        while (True):
            self.UpdateScreen()
            for i, name in enumerate(names):
                if(self.identify_page(name, 0)):
                    time.sleep(after_wait)
                    return i + 1

            if (time.time() - start_time > timeout):
                break
            time.sleep(gap)

        raise TimeoutError("identify timeout of" + str(names))

    @logit(level=INFO1)
    def get_now_page(self):
        self.UpdateScreen()
        for page in ALL_UI:
            if (self.identify_page(page, need_screen_shot=False, no_log=True)):
                return page
        return None

    @logit()
    def check_now_page(self):
        return self.identify_page(name=self.now_page.name, no_log=True)
    
    def operate(self, end: Node):
        ui_list = self.ui.find_path(self.now_page, end)
        for next in ui_list[1:]:
            edge = self.now_page.find_edge(next)
            opers = edge.operate()
            self.now_page = next
            for oper in opers:
                fun, args = oper
                if(fun == "click"):
                    self.Android.click(*args)
                else:
                    print("==================================")
                    print("unknown function name:", fun)
                    raise BaseException()
                
            if (edge.other_dst is not None):
                dst = self.wait_pages(names=[self.now_page.name, edge.other_dst.name])
                if (dst == 1):
                    continue
                if S.DEBUG:
                    print(f"Go page {self.now_page.name} but arrive ", edge.other_dst.name)
                self.now_page = self.ui.get_node_by_name([self.now_page.name, edge.other_dst.name][dst - 1])
                if S.DEBUG:
                    print(self.now_page.name)

                self.operate(end)
                return
            else:
                self.wait_pages(names=[self.now_page.name])
            time.sleep(.25)
    
    def set_page(self, page_name=None, page=None):
        
        if(page_name is None and page is None):
            now_page = self.get_now_page(self.timer)
            if(now_page == None):
                raise ImageNotFoundErr("Can't identify the page")
            else:
                self.now_page = self.ui.get_node_by_name(now_page)
            
        elif(page is not None):
            if(not isinstance(page, Node)):
                print("==============================")
                print("arg:page must be an controller.ui.Node object")
                raise ValueError
            
            if (self.ui.page_exist(page)):
                self.now_page = page
            
            raise ValueError('give page do not exist')
        
        page = self.ui.get_node_by_name(page_name)
        if (page is None):
            raise ValueError("can't find the page:", page_name)
        self.now_page = page
    
    def walk_to(self, end, try_times=0):
        try:
            if (isinstance(end, Node)):
                self.operate(end)
                self.wait_pages(end.name)
                return
            if (isinstance(end, str)):
                self.walk_to(self.ui.get_node_by_name(end))

        except TimeoutError as exception:
            if try_times > 3:
                raise TimeoutError("can't access the page")
            if is_bad_network(self, timeout=0) == False:
                print("wrong path is operated,anyway we find a way to solve,processing")
                print('wrong info is:', exception)
                self.GoMainPage()
                self.walk_to(end, try_times + 1)
            else:
                while True:
                    if process_bad_network(self, "can't walk to the position because a TimeoutError"):
                        try:
                            if not self.wait_pages(names=self.now_page.name, timeout=1):
                                self.set_page(self.get_now_page(self.timer))
                        except:
                            try:
                                self.GoMainPage()
                            except:
                                pass
                            else:
                                break
                        else:
                            break
                    else:
                        raise ValueError('unknown error')
                self.walk_to(end)

    @logit(level=INFO2)
    def GoMainPage(self, QuitOperationTime=0, List=[], ExList=[]):
        """回退到游戏主页

        Args:
            timer (Timer): _description_
            QuitOperationTime (int, optional): _description_. Defaults to 0.
            List (list, optional): _description_. Defaults to [].
            ExList (list, optional): _description_. Defaults to [].

        Raises:
            ValueError: _description_
        """
        if (QuitOperationTime > 200):
            raise ValueError("Error,Couldn't go main page")

        self.now_page = self.ui.get_node_by_name('main_page')
        if (len(List) == 0):
            List = BackImage[1:] + ExList
        type = WaitImages(self, List + [GameUI[3]], 0.8, timeout=0)

        if type is None:
            self.GoMainPage(QuitOperationTime + 1, List, no_log=True)
            return

        if (type >= len(List)):
            type = WaitImages(self, List, timeout=0)
            if type is None:
                return

        pos = GetImagePosition(self, List[type], 0, 0.8)
        self.Android.click(pos[0], pos[1])

        NewList = List[1:] + [List[0]]
        self.GoMainPage(QuitOperationTime + 1, NewList, no_log=True)
    
    @logit(level=INFO2)
    def goto_game_page(self, target='main'):
        """到某一个游戏界面

        Args:
            timer (Timer): _description_
            target (str, str): 目标章节名(见 ./constants/other_constants). Defaults to 'main'.
        """
        self.walk_to(target)
        # wait_pages(names=[timer.now_page.name])
        



class MyTemplate(Template):
    def match_in(self, screen, this_methods=None):
        match_result = self._cv_match(screen, this_methods)
        G.LOGGING.debug("match result: %s", match_result)
        if not match_result:
            return None
        focus_pos = TargetPos().getXY(match_result, self.target_pos)
        return focus_pos

    def _cv_match(self, screen, this_methods=None):
        ori_image = self._imread()
        image = self._resize_image(ori_image, screen, ST.RESIZE_METHOD)
        ret = None
        if this_methods is None:
            this_methods = ST.CVSTRATEGY
        for method in this_methods:
            # get function definition and execute:
            func = MATCHING_METHODS.get(method, None)
            if func is None:
                raise InvalidMatchingMethodError(
                    "Undefined method in CVSTRATEGY: '%s', try 'kaze'/'brisk'/'akaze'/'orb'/'surf'/'sift'/'brief' instead." % method)
            else:
                if method in ["mstpl", "gmstpl"]:
                    ret = self._try_match(func, ori_image, screen, threshold=self.threshold, rgb=self.rgb, record_pos=self.record_pos,
                                          resolution=self.resolution, scale_max=self.scale_max, scale_step=self.scale_step)
                else:
                    ret = self._try_match(func, image, screen, threshold=self.threshold, rgb=self.rgb)
            if ret:
                break
        return ret


class PixelChecker():
    def __init__(self, timer: Timer, position, bgr_color, distance=30):
        self.timer = timer
        self.position = convert_position(*position, self.timer.resolution)
        self.color = bgr_color
        self.distance = distance

    def __bool__(self):
        color = self.timer.screen[self.position[1]][self.position[0]]
        return bool(CalcDis(color, self.color) < self.distance ** 2)


def locateCenterOnImage(timer: Timer, image: np.ndarray, query: MyTemplate, confidence=0.85, this_mehods=['tpl']):
    """从原图像中尝试找出一个置信度相对于模板图像最高的矩阵区域的中心坐标

    Args:
        timer (Timer): 数据记录器
        image (np.ndarray): 原图像
        query (MyTemplate): 模板图像
        confidence (float, optional): 置信度阈值. Defaults to 0.85.
        this_mehods (list, optional): 匹配方式. Defaults to ['tpl'].

    Returns:
        如果匹配结果中有超过阈值的,返回置信度最高的结果的中心绝对坐标:Tuple(int,int)

        否则返回 None 
    """
    query.threshold = confidence
    match_pos = query.match_in(image, this_methods=this_mehods)
    return match_pos or None


def locateCenterOnScreen(timer: Timer, query: MyTemplate, confidence=0.85, this_mehods=["tpl"]):
    """从屏幕中找出和模板图像匹配度最高的矩阵区域的中心坐标
        参考 locateCenterOnImage
    Returns:
        如果找到返回一个二元组表示绝对坐标

        否则返回 None
    """
    return locateCenterOnImage(timer, timer.screen, query, confidence, this_mehods)


@logit()
def GetImagePosition(timer: Timer, image: MyTemplate, need_screen_shot=1, confidence=0.85, this_methods=["tpl"]):
    """从屏幕中找出和模板图像匹配度最高的矩阵区域的中心坐标
        参考 locateCenterOnScreen
    Args:
        need_screen_shot (int, optional): 是否重新截取屏幕. Defaults to 1.
    Returns:
        如果找到:返回一个二元组表示相对坐标 (相对 960x540 屏幕)

        否则返回 None
    """
    if (need_screen_shot == 1):
        timer.UpdateScreen()
    res = locateCenterOnScreen(timer, image, confidence, this_methods)
    if res is None:
        return None
    return convert_position(res[0], res[1], timer.resolution, mode='this_to_960')


@logit()
def ImagesExist(timer: Timer, images, need_screen_shot=1, confidence=0.85, this_methods=["tpl"]):
    """判断图像是否存在于屏幕中
    Returns:
        bool:如果存在为 True 否则为 False 
    """
    if not isinstance(images, list):
        images = [images]
    if need_screen_shot:
        timer.UpdateScreen()
    return any(GetImagePosition(timer, image, 0, confidence, this_methods, no_log=True) is not None for image in images)


@logit()
def WaitImage(timer: Timer, image: MyTemplate, confidence=0.85, timeout=10, gap=.15, after_get_delay=0, this_methods=["tpl"]):
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
        x = GetImagePosition(timer, image, 1, confidence, this_methods, no_log=True)
        if (x != None):
            time.sleep(after_get_delay)
            return x
        if (time.time()-StartTime > timeout):
            time.sleep(gap)
            return False
        time.sleep(gap)


@logit(level=INFO1)
def ClickImage(timer: Timer, image: MyTemplate, must_click=False, timeout=0, delay=0.5):
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
    pos = WaitImage(timer, image, timeout=timeout)
    if (pos == False):
        if (must_click == False):
            return False
        else:
            raise ImageNotFoundErr("Target image not found:" + str(image.filepath))

    timer.Android.click(pos[0], pos[1], delay=delay)
    return True


@logit()
def WaitImages(timer: Timer, images=[], confidence=0.85, gap=.15, after_get_delay=0, timeout=10, *args, **kwargs):
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
        the key of the value if images is a dict
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
        timer.UpdateScreen(no_log=True)
        for res, image in images:
            if (ImagesExist(timer, image, 0, confidence, no_log=True)):
                time.sleep(after_get_delay)
                return res
        time.sleep(gap)
        if (time.time() - StartTime > timeout):
            return None


@logit(level=INFO1)
def is_bad_network(timer:Timer, timeout=10):
    return WaitImages(timer, [ErrorImages['bad_network'][0], SymbolImage[10]], timeout=timeout) != None


@logit(level=INFO2)
def process_bad_network(timer:Timer, extra_info=""):
    """判断并处理网络状况问题

    Args:
        timer (Timer): _description_
        extra_info (_type_): 额外的输出信息

    Returns:
        bool: 如果为 True 则表示为网络状况问题,并已经成功处理,否则表示并非网络问题或者处理超时.
    Raise:
        TimeoutError:处理超时
    """
    start_time = time.time()
    while (is_bad_network(timer)):
        print("bad network at", time.time())
        print('extra info:', extra_info)
        while True:
            if (time.time() - start_time >= 180):
                raise TimeoutError("Process bad network timeout")
            if timer.Windows.CheckNetWork() != False:
                break

        start_time2 = time.time()
        while (ImagesExist(timer, [SymbolImage[10]] + ErrorImages['bad_network'])):
            time.sleep(.5)
            if (time.time() - start_time2 >= 60):
                break
            if (ImagesExist(timer, ErrorImages['bad_network'])):
                timer.Android.click(476, 298, delay=2)

        if (time.time() - start_time2 < 60):
            if (S.DEBUG):
                print("ok network problem solved, at", time.time())
            return True

    return False


def GoMainPage(timer:Timer, *args, **kwargs):
    timer.Game.GoMainPage(*args, **kwargs)


def goto_game_page(timer:Timer, *args, **kwargs):
    timer.goto_game_page(*args, **kwargs)