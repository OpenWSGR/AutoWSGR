import copy
import os
import threading as th
import time
from typing import Tuple

from airtest.core.api import start_app, text
from airtest.core.cv import ST
from airtest.core.helper import G
from airtest.core.settings import Settings as ST
from constants import IMG, MyTemplate, S
from constants.custom_expections import (CriticalErr, ImageNotFoundErr,
                                         NetworkErr)
from constants.other_constants import ALL_PAGES, INFO1, INFO2, INFO3, NO
from constants.ui import WSGR_UI, Node
from utils.api_image import convert_position, locateCenterOnImage
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
        self.ui = WSGR_UI
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

    def setup(self, device_name, account, password):
        self.device_name = device_name
        self.Windows.ConnectAndroid()
        self.update_screen()
        self.resolution = self.screen.shape[:2]
        self.resolution = self.resolution[::-1]
        from utils.logger import time_path
        self.log_filepre = time_path
        if account != None and password != None:
            self.restart(account=account, password=password)
        if self.Android.is_game_running() == False:
            self.start_game()
        print("resolution:", self.resolution)
        self.ammo = 10
        # self.resources = Resources(self)
        self.go_main_page()
        try:
            self.set_page()
        except Exception:
            if S.DEBUG:
                self.set_page('main_page')
            else:
                self.restart()
                self.set_page()
        print(self.now_page)

    # ========================= 初级游戏控制 =========================
    @logit(level=INFO3)
    def log_in(self, account, password):
        pass

    @logit(level=INFO3)
    def log_out(self, account, password):
        """在登录界面登出账号

        Args:
            timer (Timer): _description_
            account (_type_): _description_
            password (_type_): _description_
        """
        pass

    @logit(level=INFO3)
    def start_game(self, account=None, password=None, delay=1.0):
        """启动游戏(实现不优秀,需重写)

        Args:
            timer (Timer): _description_
            TryTimes (int, optional): _description_. Defaults to 0.

        Raises:
            NetworkErr: _description_
        """
        start_app("com.huanmeng.zhanjian2")
        res = self.wait_images([IMG.StartImage[2]] + IMG.ConfirmImage[1:], 0.85, timeout=60 * delay)

        if res is None:
            raise TimeoutError("start_app timeout")
        if res != 0:
            self.ConfirmOperation()
            if self.wait_image(IMG.StartImage[2], timeout=200) == False:
                raise TimeoutError("resource downloading timeout")
        if account != None and password != None:
            self.Android.click(75, 450)
            if self.wait_image(IMG.StartImage[3]) == False:
                raise TimeoutError("can't enter account manage page")
            self.Android.click(460, 380)
            if self.wait_image(IMG.StartImage[4]) == False:
                raise TimeoutError("can't logout successfully")
            self.Android.click(540, 180)
            for _ in range(20):
                p = th.Thread(target=lambda: self.Android.ShellCmd('input keyevent 67'))
                p.start()
            p.join()
            text(str(account))
            self.Android.click(540, 260)
            for _ in range(20):
                p = th.Thread(target=lambda: self.Android.ShellCmd('input keyevent 67'))
                p.start()
            p.join()
            time.sleep(0.5)
            text(str(password))
            self.Android.click(400, 330)
            res = self.wait_images([IMG.StartImage[5], IMG.StartImage[2]])
            if res is None:
                raise TimeoutError("login timeout")
            if res == 0:
                raise BaseException("password or account is wrong")
        while self.image_exist(IMG.StartImage[2]):
            self.click_image(IMG.StartImage[2])
        try:
            self.go_main_page()
        except:
            raise BaseException("fail to start game")

    @logit(level=INFO3)
    def restart(self, times=0, *args, **kwargs):

        try:
            self.Android.ShellCmd("am force-stop com.huanmeng.zhanjian2")
            self.Android.ShellCmd("input keyevent 3")
            self.start_game(**kwargs)
        except:
            if (self.Windows.is_android_online() == False):
                pass

            elif (times == 1):
                raise CriticalErr("on restart,")

            elif (self.Windows.CheckNetWork() == False):
                for i in range(11):
                    time.sleep(10)
                    if (self.Windows.CheckNetWork() == True):
                        break
                    if (i == 10):
                        raise NetworkErr()

            elif (self.Android.is_game_running()):
                raise CriticalErr("CriticalErr on restart function")

            self.Windows.ConnectAndroid()
            self.restart(times + 1, *args, **kwargs)

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
        pos = self.wait_images(IMG.ConfirmImage[1:], confidence, timeout=timeout)
        if pos is None:
            if (must_confirm == 1):
                raise ImageNotFoundErr("no confirm image found")
            else:
                return False
        res = self.get_image_position(IMG.ConfirmImage[pos + 1], 0)
        self.Android.click(res[0], res[1], delay=delay)
        return True

    @logit(level=INFO1)
    def is_bad_network(self, timeout=10):
        return self.wait_images([IMG.ErrorImages['bad_network'][0], IMG.SymbolImage[10]], timeout=timeout) != None

    @logit(level=INFO2)
    def process_bad_network(self, extra_info=""):
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
        while self.is_bad_network():
            print("bad network at", time.time())
            print('extra info:', extra_info)
            while True:
                if (time.time() - start_time >= 180):
                    raise TimeoutError("Process bad network timeout")
                if self.Windows.CheckNetWork() != False:
                    break

            start_time2 = time.time()
            while (self.image_exist([IMG.SymbolImage[10]] + IMG.ErrorImages['bad_network'])):
                time.sleep(.5)
                if (time.time() - start_time2 >= 60):
                    break
                if (self.image_exist(IMG.ErrorImages['bad_network'])):
                    self.Android.click(476, 298, delay=2)

            if (time.time() - start_time2 < 60):
                if (S.DEBUG):
                    print("ok network problem solved, at", time.time())
                return True

        return False

    # ========================= 当前屏幕与图片搜索 =========================
    @logit()
    def update_screen(self, *args, **kwargs):
        """记录现在的屏幕信息,以 numpy.array 格式覆盖保存到 RD.screen
        """
        self.screen = G.DEVICE.snapshot(filename=None, quality=ST.SNAPSHOT_QUALITY)

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
    def get_image_position(self, image: MyTemplate, need_screen_shot=1, confidence=0.85, this_methods=["tpl"]):
        """从屏幕中找出和模板图像匹配度最高的矩阵区域的中心坐标
            参考 locateCenterOnScreen
        Args:
            need_screen_shot (int, optional): 是否重新截取屏幕. Defaults to 1.
        Returns:
            如果找到:返回一个二元组表示相对坐标 (相对 960x540 屏幕)

            否则返回 None
        """
        if (need_screen_shot == 1):
            self.update_screen()
        res = self.locateCenterOnScreen(image, confidence, this_methods)
        if res is None:
            return None
        return convert_position(res[0], res[1], self.resolution, mode='this_to_960')

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
            self.update_screen(no_log=True)
            for res, image in images:
                if (self.image_exist(image, 0, confidence, no_log=True)):
                    time.sleep(after_get_delay)
                    return res
            time.sleep(gap)
            if (time.time() - StartTime > timeout):
                return None

    @logit(level=INFO1)
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
        if (pos == False):
            if (must_click == False):
                return False
            else:
                raise ImageNotFoundErr("Target image not found:" + str(image.filepath))

        self.Android.click(pos[0], pos[1], delay=delay)
        return True

    # ========================= 维护当前所在游戏界面 =========================
    @logit()
    def _intergrative_page_identify(self):
        positions = [(171, 47), (300, 47), (393, 47), (504, 47), (659, 47)]
        for i, position in enumerate(positions):
            if self.check_pixel(position, (225, 130, 16)):
                return i + 1

    @logit()
    def identify_page(self, name, need_screen_shot=True):
        if need_screen_shot:
            self.update_screen()

        if (name == 'main_page') and (self.identify_page('options_page', 0)):
            return False
        if (name == 'map_page') and (self._intergrative_page_identify() != 1 or self.check_pixel((35, 297), (47, 253, 226))):
            return False
        if (name == 'build_page') and (self._intergrative_page_identify() != 1):
            return False
        if (name == 'develop_page') and (self._intergrative_page_identify() != 3):
            return False

        return any(self.image_exist(template, 0) for template in IMG.IdentifyImages[name])

    @logit()
    def wait_pages(self, names, timeout=5, gap=.1, after_wait=0.1):
        start_time = time.time()
        if (isinstance(names, str)):
            names = [names]
        while (True):
            self.update_screen()
            for i, name in enumerate(names):
                if (self.identify_page(name, 0)):
                    time.sleep(after_wait)
                    return i + 1

            if (time.time() - start_time > timeout):
                break
            time.sleep(gap)

        raise TimeoutError("identify timeout of" + str(names))

    @logit(level=INFO1)
    def get_now_page(self):
        self.update_screen()
        for page in ALL_PAGES:
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
                if (fun == "click"):
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

        if (page_name is None and page is None):
            now_page = self.get_now_page()

            if now_page is None:
                raise ImageNotFoundErr("Can't identify the page")
            else:
                self.now_page = self.ui.get_node_by_name(now_page)

        elif (page is not None):
            if (not isinstance(page, Node)):

                print("==============================")
                print("arg:page must be an controller.ui.Node object")
                raise ValueError

            if (self.ui.page_exist(page)):
                self.now_page = page

            raise ValueError('give page do not exist')
        else:
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
            if self.is_bad_network(timeout=0) == False:
                print("wrong path is operated,anyway we find a way to solve,processing")
                print('wrong info is:', exception)
                self.go_main_page()
                self.walk_to(end, try_times + 1)
            else:
                while True:
                    if self.process_bad_network("can't walk to the position because a TimeoutError"):
                        try:
                            if not self.wait_pages(names=self.now_page.name, timeout=1):
                                self.set_page(self.get_now_page())
                        except:
                            try:
                                self.go_main_page()
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
    def go_main_page(self, QuitOperationTime=0, List=[], ExList=[]):
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
            List = IMG.BackImage[1:] + ExList
        type = self.wait_images(List + [IMG.GameUI[3]], 0.8, timeout=0)

        if type is None:
            self.go_main_page(QuitOperationTime + 1, List, no_log=True)
            return

        if (type >= len(List)):
            type = self.wait_images(List, timeout=0)
            if type is None:
                return

        pos = self.get_image_position(List[type], 0, 0.8)
        self.Android.click(pos[0], pos[1])

        NewList = List[1:] + [List[0]]
        self.go_main_page(QuitOperationTime + 1, NewList, no_log=True)

    @logit(level=INFO2)
    def goto_game_page(self, target='main', extra_check=False):
        """到某一个游戏界面

        Args:
            timer (Timer): _description_
            target (str, str): 目标章节名(见 ./constants/other_constants). Defaults to 'main'.
        """
        self.walk_to(target)
        if extra_check:
            self.wait_pages(names=[self.now_page.name])

    # ========================= 记录 =========================
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
