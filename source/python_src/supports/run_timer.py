from supports.models import *
from supports.math_functions import *
from functools import wraps
__all__ = ["Timer", "ImageNotFoundErr", "get_time_as_string", 'NetworkErr']


def get_time_as_string(accuracy='year'):
    """返回一个字符串时间戳,可以用于文件保存

    Args:
        accuracy (str, optional): 时间戳粒度. Defaults to "year".
            values:
                'year':记录某年某月某日某时刻
                'day':记录某天某时刻
                'second':只记录时刻
    """
    res = "".join([ch for ch in str(datetime.datetime.now()) if ch.isdigit()])
    if(accuracy == 'year'):
        return res
    if(accuracy == 'day'):
        return res[4:]
    if(accuracy == 'second'):
        return res[8:]


class Timer():
    """程序运行记录器,用于记录和传递部分数据,同时用于区分多开


    """

    def __init__(self):
        """Todo
        参考银河远征的战斗模拟写一个 Ship 类,更好的保存信息
        """
        self.start_time = time.time()
        self.log_filepre = get_time_as_string()
        self.screen = None
        self.resolution = (960, 540)
        self.ship_position = (0, 0)
        self.ship_point = "A"  # 常规地图战斗中,当前战斗点位的编号
        self.chapter = 1  # 章节名,战役为 'battle', 演习为 'exercise'
        self.node = 1  # 节点名
        self.ship_status = [0, 0, 0, 0, 0, 0, 0]  # 我方舰船状态
        self.enemy_type_count = {}  # 字典,每种敌人舰船分别有多少
        self.now_page = None  # 当前所在节点名
        self.ui = None  # ui 树
        self.device_name = 'emulator-5554'  # 设备名,雷电模拟器默认值
        self.expedition_status = None  # 远征状态记录器
        self.team = 1  # 当前队伍名
        self.defaul_decision_maker = None  # 默认决策模块
        self.ammo = 10
        self.oil = 10
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

    def covert_position(self, x, y, mode='960_to_this'):
        """转化坐标格式(放缩)

        Args:
            x (int): 横坐标
            y (int): 纵坐标
            mode (str): 工作模式
                values:
                    '960_to_this':将 960x540 格式转化为当前模拟器屏幕坐标
                    'this_to_960':将当前模拟器屏幕坐标转化为 960x540 格式

        Returns:Tuple(int,int)

            mode='960_to_this': 对应到当前模拟器屏幕上的坐标
            mode='this_to_960': 960x540 格式坐标
        Raise:
            ValueError:如果不支持这个模式
        """

        if(mode == '960_to_this'):
            return (int(x / 960 * self.resolution[1]), int(y / 540 * self.resolution[0]))
        if(mode == 'this_to_960'):
            return (int(x * 960 / self.resolution[1]), int(y * 540 / self.resolution[0]))
        raise ValueError("unsupported mode " + str(mode))

    def covert_area(self, area, mode='960_to_this'):
        """转化矩阵格式(放缩)

        Args:
            area list(left, top, right, buttom): 矩阵,列表或者元组
            mode (str): 工作模式
                values:
                    '960_to_this':将 960x540 格式转化为当前模拟器屏幕坐标
                    'this_to_960':将当前模拟器屏幕坐标转化为 960x540 格式

        Returns:
            (left, top, right, buttom): 转化后的矩阵(元组)
        """
        left, top = self.covert_position(area[0], area[1], mode)
        right, buttom = self.covert_position(area[2], area[3], mode)
        return (left, top, right, buttom)

    def get_pixel(self, x, y):
        """获取当前屏幕相对坐标 (x,y) 处的像素值

        Args:
            x (_type_): _description_
            y (_type_): _description_

        Returns:
            Tuple(int,int,int): RGB 格式的像素值
        """

        (x, y) = self.covert_position(x, y)
        return (self.screen[y][x][2], self.screen[y][x][1], self.screen[y][x][0])

    def update_ship_point(self):
        """更新黄色小船(战斗地图上那个)所在的点位 (1-1A 这种,'A' 就是点位) 

        Args:
            timer (Timer): 记录器

        """
        dir = POINT_POSITION
        self.ship_point = "A"
        for i in range(26):
            ch = chr(ord('A') + i)
            node1 = (self.chapter, self.node, ch)
            node2 = (self.chapter, self.node, self.ship_point)
            if node1 not in dir:
                break
            if(CalcDis(dir[node1], self.ship_position) < CalcDis(dir[node2], self.ship_position)):
                self.ship_point = ch

    def set_page(self, page_name=None, page=None):
        if(page is not None):
            if(self.ui.page_exist(page)):
                self.now_page = page
                return
            raise ValueError('give page do not exist')
        page = self.ui.get_node_by_name(page_name)
        if(page is None):
            raise ValueError("can't find the page:", page_name)
        self.now_page = page

    def get_ui_page_by_name(self, name):
        return self.ui.get_node_by_name(name)

    def __str__(self):
        return "this is a timer"


class ImageNotFoundErr(BaseException):
    def __init__(self, *args: object):
        super().__init__(*args)


class NetworkErr(BaseException):
    def __init__(self, *args: object):
        super().__init__(*args)


def logit(acc='str', file='log.txt'):
    def logger(fun):
        @wraps(fun)
        def log_info(*args, **kwargs):
            return fun(*args, **kwargs)
        return log_info
    return logger
