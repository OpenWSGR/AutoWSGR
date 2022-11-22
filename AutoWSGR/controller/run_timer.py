import os
import threading as th
import time

from airtest.core.api import text

from AutoWSGR.constants.custom_exceptions import (CriticalErr,
                                                  ImageNotFoundErr, NetworkErr)
from AutoWSGR.constants.data_roots import DATA_ROOT
from AutoWSGR.constants.image_templates import IMG
from AutoWSGR.constants.other_constants import (ALL_PAGES, INFO1, INFO2, INFO3,
                                                NO)
from AutoWSGR.constants.ui import WSGR_UI, Node
from AutoWSGR.utils.io import yaml_to_dict
# from AutoWSGR.utils.logger import logit
from AutoWSGR.utils.operator import unzip_element

from .emulator import Emulator


class Timer(Emulator):
    """ 程序运行记录器,用于记录和传递部分数据,同时用于区分多开 """

    def __init__(self, config, logger):
        """Todo
        参考银河远征的战斗模拟写一个 Ship 类,更好的保存信息
        """
        # 模拟器通用设置
        super().__init__(config, logger)

        # 战舰少女R专用
        self.now_page = None
        self.ui = WSGR_UI
        self.ship_status = [0, 0, 0, 0, 0, 0, 0]  # 我方舰船状态
        self.enemy_type_count = {}  # 字典,每种敌人舰船分别有多少
        self.now_page = None  # 当前所在节点名
        self.expedition_status = None  # 远征状态记录器
        self.team = 1  # 当前队伍名
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

        ship_name_path = os.path.join(DATA_ROOT, "default_ship_names.yaml")
        self.ship_names = unzip_element(list(yaml_to_dict(ship_name_path).values()))

        if self.config.account is not None and self.config.password != None:
            self.restart(account=self.config.account, password=self.config.password)
        if self.Android.is_game_running() == False:
            self.start_game()

        self.ammo = 10
        # self.resources = Resources(self)
        self.go_main_page()
        try:
            self.set_page()
        except:
            if self.config.DEBUG:
                self.set_page('main_page')
            else:
                self.restart()
                self.set_page()
        self.logger.info(f"Now at: {self.now_page}")

    # ========================= 初级游戏控制 =========================
    #@logit(level=INFO3)
    def log_in(self, account, password):
        pass

    #@logit(level=INFO3)
    def log_out(self, account, password):
        """在登录界面登出账号
        """
        pass

    #@logit(level=INFO3)
    def start_game(self, account=None, password=None, delay=1.0):
        """启动游戏(实现不优秀,需重写)

        Args:
            timer (Timer): _description_
            TryTimes (int, optional): _description_. Defaults to 0.

        Raises:
            NetworkErr: _description_
        """
        self.Android.start_app("com.huanmeng.zhanjian2")
        res = self.wait_images([IMG.start_image[2]] + IMG.confirm_image[1:], 0.85, timeout=70 * delay)

        if res is None:
            raise TimeoutError("start_app timeout")
        if res != 0:
            self.ConfirmOperation()
            if self.wait_image(IMG.start_image[2], timeout=200) == False:
                raise TimeoutError("resource downloading timeout")
        if account != None and password != None:
            self.Android.click(75, 450)
            if self.wait_image(IMG.start_image[3]) == False:
                raise TimeoutError("can't enter account manage page")
            self.Android.click(460, 380)
            if self.wait_image(IMG.start_image[4]) == False:
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
            res = self.wait_images([IMG.start_image[5], IMG.start_image[2]])
            if res is None:
                raise TimeoutError("login timeout")
            if res == 0:
                raise BaseException("password or account is wrong")
        delay = 2
        while self.image_exist(IMG.start_image[2]):
            self.click_image(IMG.start_image[2])
            time.sleep(delay)
            delay *= 2
            if (delay > 16):
                raise ImageNotFoundErr("can't start game")
        try:
            if self.everyday_check:
                if (self.wait_image(IMG.start_image[6], timeout=2) != False):  # 新闻与公告,设为今日不再显示
                    if (not self.check_pixel((70, 485), (201, 129, 54))):
                        self.Android.click(70, 485)
                    self.Android.click(30, 30)
                if (self.wait_image(IMG.start_image[7], timeout=7) != False):  # 每日签到
                    self.Android.click(474, 357)
                    self.ConfirmOperation(must_confirm=1, timeout=2)
                self.everyday_check = False
            self.go_main_page()
        except:
            raise BaseException("fail to start game")

    #@logit(level=INFO3)
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

    #@logit(level=INFO1)
    def is_bad_network(self, timeout=10):
        return self.wait_images([IMG.error_image['bad_network'][0], IMG.symbol_image[10]], timeout=timeout) != None

    # @logit(level=INFO2)
    def process_bad_network(self, extra_info="", timeout=10):
        """判断并处理网络状况问题
        Returns:
            bool: 如果为 True 则表示为网络状况问题,并已经成功处理,否则表示并非网络问题或者处理超时.
        Raise:
            TimeoutError:处理超时
        """
        start_time = time.time()
        while self.is_bad_network(timeout):
            self.logger.error(f"bad network: {extra_info}")
            while True:
                if (time.time() - start_time >= 180):
                    raise TimeoutError("Process bad network timeout")
                if self.Windows.CheckNetWork() != False:
                    break

            start_time2 = time.time()
            while (self.image_exist([IMG.symbol_image[10]] + IMG.error_image['bad_network'])):
                time.sleep(.5)
                if (time.time() - start_time2 >= 60):
                    break
                if (self.image_exist(IMG.error_image['bad_network'])):
                    self.Android.click(476, 298, delay=2)

            if (time.time() - start_time2 < 60):
                self.logger.debug("ok network problem solved, at", time.time())
                return True

        return False

    # ========================= 维护当前所在游戏界面 =========================
    #@logit()
    def _intergrative_page_identify(self):
        positions = [(171, 47), (300, 47), (393, 47), (504, 47), (659, 47)]
        for i, position in enumerate(positions):
            if self.check_pixel(position, (225, 130, 16)):
                return i + 1

    #@logit()
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

        return any(self.image_exist(template, 0) for template in IMG.identify_images[name])

    #@logit()
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

        raise TimeoutError(f"identify timeout of{str(names)}")

    #@logit(level=INFO1)
    def get_now_page(self):
        """获取并返回当前页面名称
        """
        self.update_screen()
        for page in ALL_PAGES:
            if (self.identify_page(page, need_screen_shot=False)):
                return page
        return 'unknown_page'

    #@logit()
    def check_now_page(self):
        return self.identify_page(name=self.now_page.name)

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
                    self.logger.error(f"unknown function name: {fun}")
                    raise BaseException()

            if (edge.other_dst is not None):
                dst = self.wait_pages(names=[self.now_page.name, edge.other_dst.name])
                if (dst == 1):
                    continue
                self.logger.debug(f"Go page: {self.now_page.name}, but arrive: {edge.other_dst.name}")
                self.now_page = self.ui.get_node_by_name([self.now_page.name, edge.other_dst.name][dst - 1])
                self.logger.debug(f"Now page: {self.now_page.name}")

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
                if (now_page != 'unknown_page'):
                    self.now_page = self.ui.get_node_by_name(now_page)
                else:
                    self.now_page = now_page
        elif (page is not None):
            if (not isinstance(page, Node)):
                self.logger.error("arg:page must be an controller.ui.Node object")
                raise ValueError()

            self.now_page = page if (self.ui.page_exist(page)) else 'unknown_page'
        else:
            page = self.ui.get_node_by_name(page_name)
            if (page is None):
                page = "unknown_page"

            self.now_page = page

    def walk_to(self, end, try_times=0):
        try:
            if (isinstance(self.now_page, str) and "unknow" in self.now_page):
                self.go_main_page()
            if (isinstance(end, Node)):
                self.operate(end)
                self.wait_pages(end.name)
                return
            if (isinstance(end, str)):
                end = self.ui.get_node_by_name(end)
                if end is None:
                    self.logger.error("unacceptable value of end: {end}")
                    raise ValueError("illegal value:end, in Timer.walk_to")
                self.walk_to(end)

        except TimeoutError as exception:
            if try_times > 3:
                raise TimeoutError("can't access the page")
            if self.is_bad_network(timeout=0) == False:
                self.logger.debug("wrong path is operated,anyway we find a way to solve,processing")
                self.logger.debug('wrong info is:', exception)
                self.go_main_page()
                self.walk_to(end, try_times + 1)
            else:
                while True:
                    if self.process_bad_network("can't walk to the position because a TimeoutError"):
                        try:
                            if not self.wait_pages(names=self.now_page.name, timeout=1):
                                self.set_page(self.get_now_page())
                        except:
                            self.go_main_page()
                        else:
                            break
                    else:
                        raise ValueError('unknown error')
                self.walk_to(end)

    #@logit(level=INFO2)
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
            List = IMG.back_buttons[1:] + ExList
        type = self.wait_images(List + [IMG.game_ui[3]], 0.8, timeout=0)

        if type is None:
            self.go_main_page(QuitOperationTime + 1, List)
            return

        if (type >= len(List)):
            type = self.wait_images(List, timeout=0)
            if type is None:
                return

        pos = self.get_image_position(List[type], 0, 0.8)
        self.Android.click(pos[0], pos[1])

        NewList = List[1:] + [List[0]]
        self.go_main_page(QuitOperationTime + 1, NewList)

    #@logit(level=INFO2)
    def goto_game_page(self, target='main', extra_check=False):
        """到某一个游戏界面

        Args:
            target (str, str): 目标章节名(见 ./constants/other_constants). Defaults to 'main'.
        """
        self.walk_to(target)
        if extra_check:
            self.wait_pages(names=[self.now_page.name])

    #@logit(level=INFO2)
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


def process_error(timer: Timer):
    print("processing errors")
    if timer.Windows.is_android_online() == False or timer.Android.is_game_running() == False:
        timer.Windows.RestartAndroid()
        timer.Windows.ConnectAndroid()

        return "Andoird Restarted"

    return "ok,bad network" if timer.process_bad_network() else "ok,unknown error"
