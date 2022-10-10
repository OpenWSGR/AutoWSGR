import math
import os
import time

import numpy as np
from AutoWSGR.constants.image_templates import IMG
from AutoWSGR.constants.colors import (BLOOD_COLORS, CHALLENGE_BLUE,
                                       SUPPOER_DISABLE, SUPPORT_ENALBE)
from AutoWSGR.constants.data_roots import DATA_ROOT, TUNNEL_ROOT
from AutoWSGR.constants.other_constants import (AADG, ASDG, AV, BB, BBV, BC,
                                                BG, BM, CA, CAV, CBG, CL, CLT,
                                                CV, CVL, DD, INFO1, NAP, NO,
                                                RESOURCE_NAME, SAP, SC, SS)
from AutoWSGR.constants.positions import BLOODLIST_POSITION, TYPE_SCAN_AREA
from AutoWSGR.constants.settings import S
from AutoWSGR.controller.run_timer import Timer
from AutoWSGR.ocr.digit import get_resources
from AutoWSGR.utils.io import delete_file, read_file, save_image, write_file
from AutoWSGR.utils.logger import logit
from AutoWSGR.utils.math_functions import CalcDis, CheckColor, matri_to_str
from PIL import Image as PIM


class Resources():

    def __init__(self, timer: Timer):
        self.timer = timer
        self.resources = {}

    def detect_resources(self, name=None):
        timer = self.timer
        if name is not None:
            if name in ('normal', 'oil', 'ammo', 'steel', 'aluminum'):
                self.timer.goto_game_page('main_page')
                self.detect_resources()
            if name == 'quick_repair':
                self.timer.goto_game_page('choose_repair_page')
                self.detect_resources()
            if name == 'quick_build':
                self.timer.goto_game_page('build_page')
                self.detect_resources()
            if name == 'ship_blueprint':
                self.timer.goto_game_page('build_page')
                self.detect_resources()
            if name == 'equipment_blueprint':
                self.timer.goto_game_page('develop_page')
                self.detect_resources()
        else:
            result = get_resources(timer)
            for key, value in result.items():
                self.resources[key] = value

    def ask_resources(self, name, detect=False):
        """查询资源量(不会从游戏中探查,会根据程序维护的数据返回)
        如果游戏脱离程序监控,可能会不准确，需要先 detect

        Args:
            name (资源名称):
                values:
                    refer to constants.other_constants.RESOURCE_NAME
            detect (bool, optional): 是否从游戏中重新探查(如果否，则使用由程序维护的数据)

        Returns:
            int: 资源量
        """
        if (name not in RESOURCE_NAME):
            raise ValueError("Unsupported resource name")
        if (detect or name not in self.resources.keys()):
            self.detect_resources(name)

        return self.resources.get(name)


@logit(level=INFO1)
def GetEnemyCondition(timer: Timer, type='exercise', *args, **kwargs):
    """获取敌方舰船类型数据并更新到 timer.enemy_type_count
    timer.enemy_type_count 为一个记录了敌方情况的字典
    使用了一个 C++ 写的识别程序叫 source.exe 在 .\\Data\\Tunnel\\ 下
    具体实现不介绍,当黑箱使用

    Args:
        type (str, optional): 描述情景. Defaults to 'exercise'.
            values:
                'exercise': 演习点击挑战后的一横排舰船
                'fight': 索敌成功后的两列三行
    """
    timer.enemy_type_count = {CV: 0, BB: 0, SS: 0, BC: 0, NAP: 0, DD: 0, ASDG: 0, AADG: 0, CL: 0, CA: 0, CLT: 0, CVL: 0, NO: 0, "all": 0, CAV: 0, AV: 0, BM: 0, SAP: 0, BG: 0, CBG: 0, SC: 0, BBV: 0, 'AP': 0}

    if (type == 'exercise'):
        type = 0
    if (type == 'fight'):
        type = 1

    if (timer.image_exist(IMG.fight_image[12])):
        # 特殊补给舰
        timer.enemy_type_count[SAP] = 1

    img = PIM.fromarray(timer.screen).convert("L")
    img = img.resize((960, 540))

    input_path = os.path.join(TUNNEL_ROOT, "args.in")
    output_path = os.path.join(TUNNEL_ROOT, "res.out")

    delete_file(input_path)
    delete_file(output_path)
    args = "recognize\n6\n"

    for i, area in enumerate(TYPE_SCAN_AREA[type]):
        arr = np.array(img.crop(area))
        args += matri_to_str(arr)

    write_file(input_path, args)
    os.system(f"{str(os.path.join(TUNNEL_ROOT, 'recognize_enemy.exe'))} {TUNNEL_ROOT}")

    res = read_file(os.path.join(TUNNEL_ROOT, "res.out")).split()
    timer.enemy_type_count["ALL"] = 0
    for i, x in enumerate(res):
        timer.enemy_ship_type[i]=x
        timer.enemy_type_count[x] += 1
        timer.enemy_ship_type[i]=x
        if (x != NO):
            timer.enemy_type_count["ALL"] += 1

    timer.enemy_type_count[NAP] -= timer.enemy_type_count['AP'] - timer.enemy_type_count[SAP]

    if (S.DEBUG):
        for key, value in timer.enemy_type_count.items():
            if (value != 0 and key != 'AP'):
                print(key, ':', value, end=',')
        print("")


@ logit(level=INFO1)
def DetectShipStatu(timer: Timer, type='prepare'):
    """检查我方舰船的血量状况(精确到红血黄血绿血)并更新到 timer.ship_status

    timer.ship_status:一个表示舰船血量状态的列表,从 1 开始编号.

        For Example:
        [-1, 0, 0, 1, 1, 2, 2] 表示 1,2 号位绿血,3,4 号位中破,5,6 号位大破

        values:
            -1:不存在该舰船
            0:绿血
            1:中破
            2:大破

    Args:
        type (str, optional): 描述在哪个界面检查. Defaults to 'prepare'.
            values:
                'prepare': 战斗准备界面
                'sumup': 单场战斗结算界面

    """
    """ToDo:
    血量检测精确到是否满血和是否触发中破保护
    血量检测精确到数值,相对误差少于 3%
    """

    timer.update_screen()
    result=[-1, 0, 0, 0, 0, 0, 0]
    for i in range(1, 7):
        if type == 'prepare':
            pixel=timer.get_pixel(*BLOODLIST_POSITION[0][i])
            result[i]=CheckColor(pixel, BLOOD_COLORS[0])
            if result[i] in [3, 2]:
                result[i]=2
            elif result[i] == 0:
                result[i]=0
            elif result[i] == 4:
                result[i]=-1
            else:
                result[i]=1
        elif type == 'sumup':
            if timer.ship_status[i] == -1:
                result[i]=-1
                continue
            pixel=timer.get_pixel(*BLOODLIST_POSITION[1][i])
            result[i]=CheckColor(pixel, BLOOD_COLORS[1])
    timer.ship_status=result
    if S.DEBUG:
        print(type, ":ship_status =", result)
    return result


@ logit(level=INFO1)
def DetectShipType(timer: Timer):
    """ToDo
    在出征准备界面读取我方所有舰船类型并返回该列表
    """


@ logit(level=INFO1)
def get_exercise_status(timer: Timer, robot=None):
    """检查演习界面,第 position 个位置,是否为可挑战状态,强制要求屏幕中只有四个目标

    Args:
        position (_type_): 编号从屏幕中的位置编起,如果滑动显示了第 2-5 个敌人,那么第二个敌人编号为 1

    Returns:
        bool: 如果可挑战,返回 True ,否则为 False,1-based
    """
    timer.update_screen()
    up=timer.check_pixel((933, 59), (177, 171, 176), distance=60)
    down=timer.check_pixel((933, 489), (177, 171, 176), distance=60)
    assert ((up and down) == False)

    result=[None, ]
    if (up == False and down == False):
        timer.Android.swipe(800, 200, 800, 400)  # 上滑
        timer.update_screen()
        up=True
    if (up):
        for position in range(1, 5):
            result.append(math.sqrt(CalcDis(timer.get_pixel(770, position * 110 - 10), CHALLENGE_BLUE)) <= 50)
        timer.Android.swipe(800, 400, 800, 200)  # 下滑
        timer.update_screen()
        result.append(math.sqrt(CalcDis(timer.get_pixel(770, 4 * 110 - 10), CHALLENGE_BLUE)) <= 50)
        return result
    if down:
        for position in range(1, 5):
            result.append(math.sqrt(CalcDis(timer.get_pixel(770, position * 110 - 10), CHALLENGE_BLUE)) <= 50)
        if (robot is not None):
            result.insert(1, robot)
        else:
            timer.Android.swipe(800, 200, 800, 400)  # 上滑
            timer.update_screen()
            result.insert(1, math.sqrt(CalcDis(timer.get_pixel(770, 4 * 110 - 10), CHALLENGE_BLUE)) <= 50)

            timer.Android.swipe(800, 400, 800, 200)  # 下滑

        return result


@ logit(level=INFO1)
def CheckSupportStatu(timer: Timer):
    """在出征准备界面检查是否开启了战役支援(有开始出征按钮的界面)

    Returns:
        bool: 如果开启了返回 True,否则返回 False
    """
    timer.update_screen()
    pixel=timer.get_pixel(623, 75)
    d1=CalcDis(pixel, SUPPORT_ENALBE)
    d2=CalcDis(pixel, SUPPOER_DISABLE)
    return d1 < d2
