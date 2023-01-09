import time

from airtest.core.api import text
from AutoWSGR.constants.image_templates import IMG
from AutoWSGR.constants.custom_exceptions import ImageNotFoundErr
from AutoWSGR.constants.other_constants import INFO1, INFO2, INFO3
from AutoWSGR.constants.positions import BLOOD_BAR_POSITION
from AutoWSGR.controller.run_timer import Timer
# from AutoWSGR.utils.logger import logit

from .get_game_info import CheckSupportStats, DetectShipStats


class Expedition:
    def __init__(self, timer: Timer) -> None:
        self.timer = timer
        self.is_ready = False
        self.last_check = time.time()

    # @logit(level=INFO1)
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

    # @logit(level=INFO3)
    def run(self, force=False):
        """检查远征,如果有未收获远征,则全部收获并用原队伍继续

        Args:
            force (bool): 是否强制检查
        """
        self.update(force=force)
        while self.is_ready:
            self.timer.goto_game_page('expedition_page')
            pos = self.timer.wait_image(IMG.game_ui[6], timeout=2)
            if pos:
                self.timer.Android.click(pos[0], pos[1], delay=1)
                self.timer.wait_image(IMG.fight_image[3], after_get_delay=.25)
                self.timer.Android.click(900, 500, delay=1)
                self.timer.ConfirmOperation(must_confirm=1, delay=.5, confidence=.9)
                self.update()
            else:
                break


# @logit(level=INFO2)
def get_ship(timer: Timer, max_times=1):
    times = 0
    timeout = 5
    while (timer.wait_image(IMG.symbol_image[8], timeout=timeout) and times < max_times):
        timer.Android.click(900, 500, delay=.25)
        timeout = 2
        times += 1


# @logit(level=INFO3)
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


# @logit(level=INFO2)
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

    timer.timer.log_screen()
    raise ImageNotFoundErr()


# @logit(level=INFO2)
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
    print("正在切换队伍到:", target)
    timer.Android.click(110 * target, 81)
    if (verify_team(timer) != target):
        MoveTeam(timer, target, try_times + 1)


# @logit(level=INFO3)
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
    if (CheckSupportStats(timer) != target):
        timer.Android.click(628, 82, delay=1)
        timer.Android.click(760, 273, delay=1)
        timer.Android.click(480, 270, delay=1)

    if timer.is_bad_network(0) or CheckSupportStats(timer) != target:
        if timer.process_bad_network('set_support'):
            SetSupport(timer, target)
        else:
            raise ValueError("can't set right support")


# @logit(level=INFO3)
def QuickRepair(timer: Timer, repair_mode=2, *args, **kwargs):
    """战斗界面的快速修理

    Args:
        timer (Timer): _description_
        repair_mode:
            1: 快修，修中破
            2: 快修，修大破
    """
    ShipStats = DetectShipStats(timer)
    assert type(repair_mode) in [int, list]
    if type(repair_mode) == int:  # 指定所有统一修理方案
        repair_mode = [repair_mode for _ in range(6)]

    assert len(repair_mode) == 6
    need_repair = [False for _ in range(6)]
    for i, x in enumerate(repair_mode):
        assert x in [1, 2]
        if x == 1:
            need_repair[i] = ShipStats[i+1] not in [-1, 0]
        elif x == 2:
            need_repair[i] = ShipStats[i+1] not in [-1, 0, 1]

    if (timer.config.DEBUG):
        print("ShipStats:", ShipStats)
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


# @logit(level=INFO3)
def GainBounds(timer: Timer):
    """检查任务情况,如果可以领取奖励则领取

    Args:
        timer (Timer): _description_
    """
    timer.goto_game_page('main_page')
    if not timer.check_pixel((694, 457), bgr_color=(45, 89, 255)):
        return 'no'
    timer.goto_game_page('mission_page')
    timer.goto_game_page('mission_page')
    if timer.click_image(IMG.game_ui[15]):
        timer.ConfirmOperation(must_confirm=1)
        return 'ok'
    elif timer.click_image(IMG.game_ui[12]):
        timer.ConfirmOperation(must_confirm=1)
        return 'ok'
    return 'no'
    #timer.Android.click(774, 502)


# @logit(level=INFO2)
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


# @logit(level=INFO2)
def SetAutoSupply(timer: Timer, type=1):
    timer.update_screen()
    NowType = int(timer.check_pixel((48, 508), (224, 135, 35)))
    if (NowType != type):
        timer.Android.click(44, 503, delay=0.33)


# @logit(level=INFO2)
def Supply(timer: Timer, ship_ids=[1, 2, 3, 4, 5, 6], try_times=0):
    """补给指定舰船

    Args:
        timer (Timer): _description_
        ship_ids (list, optional): 补给舰船列表,可以为单个整数. Defaults to [1, 2, 3, 4, 5, 6].
        try_times (int, optional): _description_. Defaults to 0.

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


# @logit(level=INFO2)
def ChangeShip(timer: Timer, fleet_id, ship_id=None, name=None, pre=None, detect_ship_stats=True):
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
    if (detect_ship_stats):
        DetectShipStats(timer)
    if name is None and timer.ship_stats[ship_id] == -1:
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
    if (timer.ship_stats[ship_id] == -1):
        timer.Android.click(83, 167, delay=0)
    else:
        timer.Android.click(183, 167, delay=0)

    timer.wait_pages('fight_prepare_page', gap=0)


# @logit(level=INFO3)
def ChangeShips(timer: Timer, fleet_id, ship_names):
    """更换编队舰船

    Args:
        fleet_id (int): 2~4,表示舰队编号
        ship_names (舰船名称列表): 

    For instance:
        ChangeShips(timer, 2, [None, "萤火虫", "伏尔塔", "吹雪", "明斯克", None, None])

    """
    timer.logger.info(f"Change Fleet {fleet_id} to {ship_names}")
    if (fleet_id is not None):
        timer.goto_game_page('fight_prepare_page')
        MoveTeam(timer, fleet_id)
    if fleet_id == 1:
        raise ValueError("change member of fleet 1 is unsupported")
    DetectShipStats(timer)
    for i in range(1, 7):
        if (timer.ship_stats[i] != -1):
            ChangeShip(timer, fleet_id, 1, None, detect_ship_stats=False)
    ship_names = ship_names + [None] * 6
    for i in range(len(ship_names)):
        if ship_names[i] == "":
            ship_names[i] = None
    time.sleep(.3)
    DetectShipStats(timer)
    for i in range(1, 7):
        ChangeShip(timer, fleet_id, i, ship_names[i], detect_ship_stats=False)


def get_new_things(timer: Timer, lock=0):
    pass
