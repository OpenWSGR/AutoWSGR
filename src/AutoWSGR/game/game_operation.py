import time

from AutoWSGR.constants.image_templates import IMG
from AutoWSGR.constants.custom_exceptions import ImageNotFoundErr
from AutoWSGR.constants.positions import BLOOD_BAR_POSITION
from AutoWSGR.controller.run_timer import Timer, try_to_get_expedition
from AutoWSGR.ocr.ship_name import recognize_single_number

from .get_game_info import check_support_stats, detect_ship_stats


class Expedition():
    
    def __init__(self, timer: Timer) -> None:
        self.timer = timer
        self.is_ready = False
        self.last_check = time.time()

    def update(self, force=False):
        self.timer.update_screen()
        if (isinstance(self.timer.now_page, str) and 'unknow' in self.timer.now_page)\
                or self.timer.now_page.name not in ['expedition_page', 'map_page', 'battle_page', 'exercise_page', 'decisive_battle_entrance']:
            if (force or time.time() - self.last_check > 1800):
                self.timer.goto_game_page('main_page')
            if (self.timer.now_page.name == 'main_page'):
                self.is_ready = self.timer.check_pixel((933, 454), bgr_color=(45, 89, 255))
        else:
            self.is_ready = self.timer.check_pixel((464, 11), bgr_color=(45, 89, 255))

    def run(self, force=False):
        """检查远征, 如果有未收获远征, 则全部收获并用原队伍继续

        Args:
            force (bool): 是否强制检查
        Returns:
            bool: 是否进行了远征操作
        """
        self.update(force=force)
        if self.is_ready:
            self.timer.goto_game_page('expedition_page')
            flag = try_to_get_expedition(self.timer)
            self.timer.last_expedition_check_time = time.time()

def get_ship(timer: Timer, max_times=1):
    timer.wait_image(IMG.symbol_image[8])
    while timer.wait_image(IMG.symbol_image[8], timeout=0.5):
        timer.Android.click(900, 500, delay=.25, times=2)


def DestroyShip(timer: Timer):
    """解装舰船，目前仅支持：全部解装+保留装备"""

    if not timer.identify_page('destroy_page'):
        timer.goto_game_page('destroy_page')
    timer.set_page('destroy_page')

    timer.Android.click(90, 206, delay=1.5)  # 点添加
    timer.Android.relative_click(0.91-0.5, 0.3-0.5, delay=1.5)  # 快速选择
    timer.Android.relative_click(0.915-0.5, 0.906-0.5, delay=1.5)  # 确定
    timer.Android.relative_click(0.837-0.5, 0.646-0.5, delay=1.5)  # 卸下装备
    timer.Android.relative_click(0.9-0.5, 0.9-0.5, delay=1.5)  # 解装
    timer.Android.relative_click(0.38-0.5, 0.567-0.5, delay=1.5)  # 四星确认


def verify_team(timer: Timer):
    """检验目前是哪一个队伍(1~4)
    含网络状况处理
    Args:
        timer (Timer): _description_

    Raises:
        ImageNotFoundErr: 未找到队伍标志
        ImageNotFoundErr: 不在相关界面

    Returns:
        int: 队伍编号(1~4)
    """
    if (timer.identify_page('fight_prepare_page') == False):
        raise ImageNotFoundErr("not on fight_prepare_page")

    for _ in range(5):
        for i, position in enumerate([(64, 83), (186, 83), (310, 83), (430, 83)]):
            if (timer.check_pixel(position, bgr_color=(228, 132, 16))):
                return i + 1
        time.sleep(.2)
        timer.update_screen()

    if timer.process_bad_network():
        return verify_team(timer)

    timer.logger.log_screen()
    raise ImageNotFoundErr()


def MoveTeam(timer: Timer, target, try_times=0):
    """切换队伍
    Args:
        timer (Timer): _description_
        target (_type_): 目标队伍
        try_times: 尝试次数
    Raise:
        ValueError: 切换失败
        ImageNotFoundErr: 不在相关界面
    """
    if (try_times > 3):
        raise ValueError("can't change team")

    if (timer.identify_page('fight_prepare_page') == False):
        timer.timer.log_screen()
        raise ImageNotFoundErr("not on 'fight_prepare_page' ")

    if (verify_team(timer) == target):
        return
    timer.logger.info("正在切换队伍到:" + str(target))
    timer.Android.click(110 * target, 81)
    if (verify_team(timer) != target):
        MoveTeam(timer, target, try_times + 1)


def SetSupport(timer: Timer, target, try_times=0):
    """启用战役支援
    Args:
        timer (Timer): _description_
        target (bool, int): 目标状态
    Raise:
        ValueError: 未能成功切换战役支援状态
    """
    target = bool(target)
    timer.goto_game_page("fight_prepare_page")
    # if(bool(timer.check_pixel((623, 75), )) == ):
    #
    # 支援次数已用尽
    if (check_support_stats(timer) != target):
        timer.Android.click(628, 82, delay=1)
        timer.Android.click(760, 273, delay=1)
        timer.Android.click(480, 270, delay=1)

    if timer.is_bad_network(0) or check_support_stats(timer) != target:
        if timer.process_bad_network('set_support'):
            SetSupport(timer, target)
        else:
            raise ValueError("can't set right support")


def quick_repair(timer: Timer, repair_mode=2, ship_stats=None, *args, **kwargs):
    """战斗界面的快速修理
    Args:
        timer (Timer): _description_
        repair_mode:
            1: 快修，修中破
            2: 快修，修大破
    """
    arg = repair_mode
    try:
        if ship_stats == None:
            ship_stats = detect_ship_stats(timer)
        if not any(x in ship_stats for x in [0, 1, 2]):
            time.sleep(1)
            ship_stats = detect_ship_stats(timer)
        if not any(x in ship_stats for x in [0, 1, 2]):
            timer.logger.warning("执行修理操作时没有成功检测到舰船")
        
        assert type(repair_mode) in [int, list, tuple]
        if type(repair_mode) == int:  # 指定所有统一修理方案
            repair_mode = [repair_mode for _ in range(6)]

        assert len(repair_mode) == 6
        need_repair = [False for _ in range(6)]
        for i, x in enumerate(repair_mode):
            assert x in [1, 2]
            if x == 1:
                need_repair[i] = ship_stats[i+1] not in [-1, 0]
            elif x == 2:
                need_repair[i] = ship_stats[i+1] not in [-1, 0, 1]

        if (timer.config.DEBUG):
            timer.logger.debug("ship_stats:", ship_stats)
        if any(need_repair) or timer.image_exist(IMG.repair_image[1]):

            timer.Android.click(420, 420, times=2, delay=0.8)   # 进入修理页面
            # 快修已经开始泡澡的船
            pos = timer.get_image_position(IMG.repair_image[1])
            while (pos != None):
                timer.Android.click(pos[0], pos[1], delay=1)
                pos = timer.get_image_position(IMG.repair_image[1])
            # 按逻辑修理
            for i in range(1, 7):
                if need_repair[i-1]:
                    timer.logger.info("WorkInfo:" + str(kwargs))
                    timer.logger.info(str(i)+" Repaired")
                    timer.Android.click(BLOOD_BAR_POSITION[0][i][0], BLOOD_BAR_POSITION[0][i][1], delay=1.5)
    except AssertionError:
        raise ValueError(f"修理舰船的参数不合法, 请检查你的参数:{arg}")


def get_rewards(timer: Timer):
    """检查任务情况,如果可以领取奖励则领取
    """
    timer.goto_game_page('main_page')
    if not timer.check_pixel((694, 457), bgr_color=(45, 89, 255)):
        return 'no'
    timer.goto_game_page('mission_page')
    timer.goto_game_page('mission_page')
    if timer.click_image(IMG.game_ui[15]):
        timer.ConfirmOperation(must_confirm=1, timeout=5)
        return 'ok'
    elif timer.click_image(IMG.game_ui[12]):
        timer.ConfirmOperation(must_confirm=1)
        return 'ok'
    return 'no'
    # timer.Android.click(774, 502)


def RepairByBath(timer: Timer):
    """使用浴室修理修理时间最长的单位
    Args:
        timer (Timer): _description_
    """
    timer.goto_game_page('choose_repair_page')
    timer.Android.click(115, 233)
    if (not timer.identify_page('choose_repair_page')):
        if (timer.identify_page('bath_page')):
            timer.set_page('bath_page')
        else:
            timer.set_page()


def SetAutoSupply(timer: Timer, type=1):
    timer.update_screen()
    NowType = int(timer.check_pixel((48, 508), (224, 135, 35)))
    if (NowType != type):
        timer.Android.click(44, 503, delay=0.33)


def Supply(timer: Timer, ship_ids=[1, 2, 3, 4, 5, 6], try_times=0):
    """补给指定舰船

    Args:
        timer (Timer): _description_
        ship_ids (list, optional): 补给舰船列表, 可以为单个整数表示单艘舰船. Defaults to [1, 2, 3, 4, 5, 6].

    Raises:
        ValueError: 补给失败
        TypeError: ship_ids 参数有误
    """
    if (try_times > 3):
        raise ValueError("can't supply ship")

    if (isinstance(ship_ids, int)):
        ship_ids = [ship_ids]

    timer.Android.click(293, 420)
    for x in ship_ids:
        if not isinstance(x, int):
            raise TypeError("ship must be represent as a int but get" + str(ship_ids))
        timer.Android.click(110 * x, 241)

    if timer.is_bad_network(0):
        timer.process_bad_network('supply ships')
        Supply(timer, ship_ids, try_times + 1)


def ChangeShip(timer: Timer, fleet_id, ship_id=None, name=None, pre=None, ship_stats = None):
    """切换舰船(不支持第一舰队)

    """
    if (fleet_id is not None):
        timer.goto_game_page('fight_prepare_page')
        MoveTeam(timer, fleet_id)
        if (fleet_id >= 5):
            # 切换为预设编队
            # 暂不支持
            return

    # 切换单船
    # 懒得做 OCR 所以默认第一个
    if ship_stats is None:
        ship_stats = detect_ship_stats(timer)
    if name is None and ship_stats[ship_id] == -1:
        return
    timer.Android.click(110 * ship_id, 250, delay=0)
    res = timer.wait_images([IMG.choose_ship_image[1], IMG.choose_ship_image[2]], after_get_delay=.4, gap=0)
    if (res == 1):
        timer.Android.click(839, 113)

    if name is None:
        timer.Android.click(83, 167, delay=0)
        timer.wait_pages('fight_prepare_page', gap=0)
        return

    timer.Android.click(700, 30, delay=0)
    timer.wait_image(IMG.choose_ship_image[3], gap=0, after_get_delay=.1)

    timer.Android.text(name)
    timer.Android.click(50, 50, delay=.5)
    if (ship_stats[ship_id] == -1):
        timer.Android.click(83, 167, delay=0)
    else:
        timer.Android.click(183, 167, delay=0)

    timer.wait_pages('fight_prepare_page', gap=0)


def ChangeShips(timer: Timer, fleet_id, ship_names):
    """更换编队舰船

    Args:
        fleet_id (int): 2~4,表示舰队编号
        
        ship_names (舰船名称列表): 

    For example:
        ChangeShips(timer, 2, [None, "萤火虫", "伏尔塔", "吹雪", "明斯克", None, None])

    """
    timer.logger.info(f"Change Fleet {fleet_id} to {ship_names}")
    if (fleet_id is not None):
        timer.goto_game_page('fight_prepare_page')
        MoveTeam(timer, fleet_id)
    if fleet_id == 1:
        raise ValueError("change member of fleet 1 is unsupported")
    ship_stats = detect_ship_stats(timer)
    for i in range(1, 7):
        if (ship_stats[i] != -1):
            ChangeShip(timer, fleet_id, 1, None, ship_stats=ship_stats)
    ship_names = ship_names + [None] * 6
    for i in range(len(ship_names)):
        if ship_names[i] == "":
            ship_names[i] = None
    time.sleep(.3)
    ship_stats = detect_ship_stats(timer)
    for i in range(1, 7):
        ChangeShip(timer, fleet_id, i, ship_names[i], ship_stats=ship_stats)


def get_new_things(timer: Timer, lock=0):
    pass


def detect_resources(timer:Timer, position=None) -> list:
    """检查四项资源余量, 实验性功能
    Args:
        position (int, optional): 具体哪一项资源 [0,3], 默认为空则检测四项. Defaults to None.
    Returns:
        list: 四个元素的列表, 分别表示油弹钢铝的余量
    """
    screen = timer.get_screen(need_screen_shot=True)
    res = [0] * 4
    r = len(screen) / 540
    SIZE = (int(45 * r), int(155 * r))
    POSITION = [(int(198 * r), int(198 * r)), (int(198 * r), int(566 * r)), (int(415 * r), int(198 * r)), (int(415 * r), int(566 * r))]
    if position == None:
        for i in range(4):
            area = screen[POSITION[i][0]:POSITION[i][0] + SIZE[0], POSITION[i][1]:POSITION[i][1] + SIZE[1]]
            res[i] = recognize_single_number(area)
        return res
    area = screen[POSITION[position][0]:POSITION[position][0] + SIZE[0],\
        POSITION[position][1]:POSITION[position][1] + SIZE[1]]
    return recognize_single_number(area)


def choose_resources(timer:Timer, type, resources):
    POSITIONS = [(213, 221), (584, 221), (213, 427), (584, 427)]
    right, gap = 55, 35
    
    minv = 10
    if type == "ship":
        minv = 30
    if min(resources) < minv:
        timer.logger.error(f"用于 {type} 的资源 {resources} 过少, 最小值为 {minv}, 已自动取消操作")
        return False
    
    now_resources = detect_resources(timer)
    timer.logger.info(f"当前 {type} 的设置: {now_resources}")
    for rk, pos, src, dst in zip(range(4), POSITIONS, now_resources, resources):
        def move(id, way, adjust = 0):
            p0 = (pos[0] + id * right, pos[1])
            p1 = (pos[0] + id * right, pos[1] - way * (gap + adjust))
            timer.Android.swipe(*p0, *p1, duration=.25)
            num = str(detect_resources(timer, rk))
            if len(num) == 2: num = "0" + num
            num = int(num[id])
            if num == src[id]:
                move(id, way, adjust + 2)
                timer.logger.debug("Move Failed, Increase Adjustment")
            else:
                src[id] += way
                timer.logger.debug("Move Success")
        if src == dst:
            continue
        src, dst = str(src), str(dst)
        if len(src) == 2: src = "0" + src
        if len(dst) == 2: dst = "0" + dst
        src, dst = list(map(int, list(src))), list(map(int, list(dst)))
        print(src, dst)
        if src[0] == 0:
            move(0, 1)
        for i in range(2, -1, -1):
            while src[i] < dst[i]:
                move(i, 1)
            while src[i] > dst[i]:
                move(i, -1)
    return True
    

def get_build(timer:Timer, type):
    """获取已经建造好的舰船或装备
    Args:
        type (str): "ship"/"equipment"
    Returns:
        bool: 是否获取成功
    """
    if type == "equipment":
        timer.goto_game_page("develop_page")
        imgs = IMG.build_image[:4]
    if type == "ship":
        timer.goto_game_page("build_page")
        imgs = IMG.build_image[3:]
    if not timer.image_exist(imgs[1]):
        timer.logger.warning(f"尝试获取 {type} 但是未找到已完成的工作")
        return False
    try:
        timer.click_image(imgs[1], timeout=3, must_click=False)
    except:
        timer.logger.error(f"无法获取 {type}, 可能是对应仓库已满")
        return False
    get_ship(timer)
    return True
    

def build(timer:Timer, type, resources=None, fast=False, force=False):
    """建造操作
    Args:
        timer (Timer): _description_
        type (str): "ship"/"equipment"
        resources: 一个列表, 表示油弹钢铝四项资源. Defaults to None.
        fast (bool, optional): 是否快速建造. Defaults to False.
        force (bool, optional): 如果队列已满, 是否立刻结束一个以开始建造. Defaults to False.
    """
    if type == "equipment":
        timer.goto_game_page("develop_page")
        imgs = IMG.build_image[:4]
    if type == "ship":
        timer.goto_game_page("build_page")
        imgs = IMG.build_image[3:]
    
    get_build(timer, type)
    if not timer.image_exist(imgs[2]):
        if force:
            timer.click_image(imgs[3])
            timer.ConfirmOperation(must_confirm=1, timeout=3)
            get_build(timer, type)
        else:
            timer.logger.error(f"{type} 队列已满")
            return False
    timer.click_image(imgs[2])
    timer.wait_image(IMG.build_image[7])
    if choose_resources(timer, type, resources):
        if fast:
            timer.Android.click(855, 425)
            timer.ConfirmOperation(must_confirm=1, timeout=3)
            get_ship(timer)
            timer.Android.click(30, 30)
        else:
            timer.Android.click(850, 480)
        

def cook(timer:Timer, position:int):
    """食堂做菜
    Args:
        position (int): 第几个菜谱
    """
    if position < 1 or position > 3:
        raise ValueError(f"不支持的菜谱编号:{position}")
    POSITION = [None, (318, 276), (420, 140), (556, 217)]
    timer.goto_game_page("canteen_page")
    timer.Android.click(*POSITION[position])
    try:
        timer.click_image(IMG.restaurant_image[1], timeout=7.5, must_click=True)
        timer.logger.info("做菜成功")
        return True
    except:
        timer.logger.error(f"不支持的菜谱编号:{position}, 请检查该菜谱是否有效, 或者检查今日用餐次数是否已经用尽")
        return False
    