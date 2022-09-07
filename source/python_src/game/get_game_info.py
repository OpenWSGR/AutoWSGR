import math
import os
import time

import constants.settings as S
import numpy as np
from constants.color_info import (BLOOD_COLORS, CHALLENGE_BLUE,
                                  SUPPOER_DISABLE, SUPPORT_ENALBE)
from constants.image_templates import FightImage
from constants.keypoint_info import BLOODLIST_POSITION, TYPE_SCAN_AREA
from constants.other_constants import (AADG, ASDG, AV, BB, BBV, BC, BG, BM, CA,
                                       CAV, CBG, CL, CLT, CV, CVL, DD, INFO1,
                                       NAP, NO, RESOURCE_NAME, SAP, SC, SS)
from ocr.digit import get_resources
from PIL import Image as PIM
from controller.run_timer import Timer, ImagesExist, PixelChecker
from utils.io import delete_file, read_file, save_image, write_file
from utils.logger import logit
from utils.math_functions import CalcDis, CheckColor, matri_to_str

from game.switch_page import goto_game_page


class ExpeditionStatus():
    def __init__(self, timer: Timer):
        self.exist_ready = False
        self.timer = timer
        self.last_check = time.time()

    def is_ready(self):
        return self.exist_ready

    @logit(level=INFO1)
    def update(self, force=False):
        self.timer.UpdateScreen()
        if self.timer.now_page.name in ['expedition_page', 'map_page', 'battle_page', 'exercise_page', 'decisive_battle_entrance']:
            self.exist_ready = bool(PixelChecker(self.timer, (464, 11), bgr_color=(45, 89, 255)))
        else:
            if (force or time.time() - self.last_check > 1800):
                goto_game_page(self.timer, 'main_page')
            if (self.timer.now_page.name == 'main_page'):
                self.exist_ready = bool(PixelChecker(self.timer, (933, 454), bgr_color=(45, 89, 255)))


class Resources():

    def __init__(self, timer: Timer):
        self.timer = timer
        self.resources = {}

    def detect_resources(self, name=None):
        timer = self.timer
        if name is not None:
            if name in ('normal', 'oil', 'ammo', 'steel', 'aluminum'):
                goto_game_page(timer, 'main_page')
                self.detect_resources()
            if name == 'quick_repair':
                goto_game_page(timer, 'choose_repair_page')
                self.detect_resources()
            if name == 'quick_build':
                goto_game_page(timer, 'build_page')
                self.detect_resources()
            if name == 'ship_blueprint':
                goto_game_page(timer, 'build_page')
                self.detect_resources()
            if name == 'equipment_blueprint':
                goto_game_page(timer, 'develop_page')
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
    timer.enemy_type_count = {CV: 0, BB: 0, SS: 0, BC: 0, NAP: 0, DD: 0, ASDG: 0, AADG: 0,
                              CL: 0, CA: 0, CLT: 0, CVL: 0, NO: 0, AV: 0, "all": 0, CAV: 0, AV: 0,
                              BM: 0, SAP: 0, BG: 0, CBG: 0, SC: 0, BBV: 0, 'AP': 0}
    if (type == 'exercise'):
        type = 0
    if (type == 'fight'):
        type = 1

    if (ImagesExist(timer, FightImage[12])):
        # 特殊补给舰
        timer.enemy_type_count[SAP] = 1

    PIM.fromarray(timer.screen).convert("L").resize((960, 540)).save(".\\Data\\Tmp\\screen.PNG")
    img = PIM.open(".\\Data\\Tmp\\screen.PNG")
    input_path = os.path.join(S.TUNNEL_PATH, "args.in")
    output_path = os.path.join(S.TUNNEL_PATH, "res.out")

    delete_file(input_path)
    delete_file(output_path)
    args = "recognize\n6\n"

    for i, area in enumerate(TYPE_SCAN_AREA[type]):
        arr = np.array(img.crop(area))
        save_image(os.path.join(S.TUNNEL_PATH, str(i) + ".PNG"), arr, True)
        args += matri_to_str(arr)

    write_file(input_path, args)

    os.chdir(S.TUNNEL_PATH)
    os.system(".\Source.exe")
    os.chdir("..\\..\\")

    res = read_file(S.WORK_PATH + "Data\\Tunnel\\res.out").split()
    timer.enemy_type_count["ALL"] = 0
    for i, x in enumerate(res):
        timer.enemy_ship_type[i] = x
        timer.enemy_type_count[x] += 1
        timer.enemy_ship_type[i] = x
        if (x != NO):
            timer.enemy_type_count["ALL"] += 1

    timer.enemy_type_count[NAP] -= timer.enemy_type_count['AP'] - timer.enemy_type_count[SAP]

    if (S.DEBUG):
        for key, value in timer.enemy_type_count.items():
            if (value != 0 and key != 'AP'):
                print(key, ':', value, end=',')
        print("")


@logit(level=INFO1)
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

    timer.UpdateScreen()
    result = [-1, 0, 0, 0, 0, 0, 0]
    if type == 'prepare':
        for i in range(1, 7):
            pixel = timer.get_pixel(*BLOODLIST_POSITION[0][i])
            result[i] = CheckColor(pixel, BLOOD_COLORS[0])
            if result[i] in [3, 2]:
                result[i] = 2
            elif result[i] == 0:
                result[i] = 0
            elif result[i] == 4:
                result[i] = -1
            else:
                result[i] = 1
    if type == 'sumup':
        for i in range(1, 7):
            if timer.ship_status[i] == -1:
                result[i] = -1
                continue
            pixel = timer.get_pixel(*BLOODLIST_POSITION[1][i])
            result[i] = CheckColor(pixel, BLOOD_COLORS[1])
    timer.ship_status = result
    if S.DEBUG:
        print(type, ":ship_status =", result)
    return result


@logit(level=INFO1)
def DetectShipType(timer: Timer):
    """ToDo
    在出征准备界面读取我方所有舰船类型并返回该列表
    """


@logit(level=INFO1)
def get_exercise_status(timer: Timer):
    """检查演习界面,第 position 个位置,是否为可挑战状态,强制要求屏幕中只有四个目标

    Args:
        position (_type_): 编号从屏幕中的位置编起,如果滑动显示了第 2-5 个敌人,那么第二个敌人编号为 1

    Returns:
        bool: 如果可挑战,返回 True ,否则为 False,1-based
    """
    timer.Android.swipe(800, 200, 800, 400)
    timer.UpdateScreen()
    result = [None, ]
    for position in range(1, 5):
        result.append(bool(math.sqrt(CalcDis(timer.get_pixel(770, position * 110 - 10), CHALLENGE_BLUE)) <= 50))
    timer.Android.swipe(800, 400, 800, 200)
    timer.UpdateScreen()
    result.append(bool(math.sqrt(CalcDis(timer.get_pixel(770, 4 * 110 - 10), CHALLENGE_BLUE)) <= 50))
    timer.Android.swipe(800, 200, 800, 400)
    return result


@logit(level=INFO1)
def CheckSupportStatu(timer: Timer):
    """在出征准备界面检查是否开启了战役支援(有开始出征按钮的界面)

    Returns:
        bool: 如果开启了返回 True,否则返回 False
    """
    timer.UpdateScreen()
    pixel = timer.get_pixel(623, 75)
    d1 = CalcDis(pixel, SUPPORT_ENALBE)
    d2 = CalcDis(pixel, SUPPOER_DISABLE)
    return d1 < d2
