import math
import os
import subprocess

import numpy as np
from PIL import Image as PIM

from autowsgr.constants.colors import COLORS
from autowsgr.constants.data_roots import OCR_ROOT, TUNNEL_ROOT
from autowsgr.constants.image_templates import IMG
from autowsgr.constants.other_constants import (
    AADG,
    ASDG,
    AV,
    BB,
    BBV,
    BC,
    BG,
    BM,
    CA,
    CAV,
    CBG,
    CL,
    CLT,
    CV,
    CVL,
    DD,
    NAP,
    NO,
    RESOURCE_NAME,
    SAP,
    SC,
    SS,
)
from autowsgr.constants.positions import BLOOD_BAR_POSITION, TYPE_SCAN_AREA
from autowsgr.timer import Timer
from autowsgr.utils.api_image import crop_image
from autowsgr.utils.io import delete_file, read_file, yaml_to_dict
from autowsgr.utils.math_functions import CalcDis, CheckColor, matrix_to_str


class Resources:
    def __init__(self, timer: Timer):
        self.timer = timer
        self.resources = {}

    def detect_resources(self, name=None):
        timer = self.timer
        if name is not None:
            if name in ("normal", "oil", "ammo", "steel", "aluminum"):
                self.timer.goto_game_page("main_page")
                self.detect_resources()
            if name == "quick_repair":
                self.timer.goto_game_page("choose_repair_page")
                self.detect_resources()
            if name == "quick_build":
                self.timer.goto_game_page("build_page")
                self.detect_resources()
            if name == "ship_blueprint":
                self.timer.goto_game_page("build_page")
                self.detect_resources()
            if name == "equipment_blueprint":
                self.timer.goto_game_page("develop_page")
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
        if name not in RESOURCE_NAME:
            raise ValueError("Unsupported resource name")
        if detect or name not in self.resources.keys():
            self.detect_resources(name)

        return self.resources.get(name)


POS = yaml_to_dict(os.path.join(OCR_ROOT, "relative_location.yaml"))


def get_resources(timer: Timer):
    """根据 timer 所处界面获取对应资源数据
    部分 case 会没掉,请重写
    """
    timer.goto_game_page("main_page")
    timer.update_screen()
    image = timer.screen
    ret = {}
    for key in POS["main_page"]["resources"]:
        image_crop = crop_image(image, *POS["main_page"]["resources"][key])
        try:
            ret[key] = timer.recognize_number(image_crop, "KM.")[1]
        except:
            # 容错处理，如果监测出来不是数字则出错了
            timer.logger.warning(f"读取{key}资源失败")
    timer.logger.info(ret)
    return ret


def get_loot_and_ship(timer: Timer):
    """获取掉落数据"""
    timer.goto_game_page("map_page")
    timer.update_screen()
    image = timer.screen
    ret = {}
    for key in POS["map_page"]:
        image_crop = crop_image(image, *POS["map_page"][key])
        result = timer.recognize_number(image_crop, extra_chars="/", allow_nan=True)
        if result:
            if isinstance(result[1], tuple):
                ret[key], ret[key + "_max"] = result[1]
            else:
                # 如果ocr把"/"识别为"1",则使用下列方法
                if key == "loot":
                    ret[key] = result[1][0:-3]
                    ret[key + "_max"] = 50
                if key == "ship":
                    ret[key] = result[1][0:-4]
                    ret[key + "_max"] = 500
        else:
            timer.logger.warning(f"读取{key}数量失败")
    try:
        timer.got_ship_num = ret.get("ship")
    except:
        timer.logger.warning("赋值给got_ship_num失败")
        timer.got_ship_num = 0

    try:
        timer.got_loot_num = ret.get("loot")
        if timer.got_loot_num == None:
            timer.got_loot_num = 0
    except:
        timer.logger.warning("赋值给got_loot_num失败")
        timer.got_loot_num = 0
    timer.logger.info(f"已掉落胖次:{timer.got_loot_num}")
    timer.logger.info(f"已掉落舰船:{timer.got_ship_num}")
    return ret


def get_enemy_condition(timer: Timer, type="exercise", *args, **kwargs):
    """获取敌方舰船类型数据并返回一个字典, 具体图像识别为黑箱, 采用 C++ 实现

    Args:
        type (str, optional): 描述情景. Defaults to 'exercise'.
            'exercise': 演习点击挑战后的一横排舰船

            'fight': 索敌成功后的两列三行

    Returs:
        dict: {[SHIP_TYPE]:[SHIP_AMOUNT]}

        example return: {"CV":1, "BB":3, "DD": 2}
    """

    enemy_type_count = {
        CV: 0,
        BB: 0,
        SS: 0,
        BC: 0,
        NAP: 0,
        DD: 0,
        ASDG: 0,
        AADG: 0,
        CL: 0,
        CA: 0,
        CLT: 0,
        CVL: 0,
        NO: 0,
        "all": 0,
        CAV: 0,
        AV: 0,
        BM: 0,
        SAP: 0,
        BG: 0,
        CBG: 0,
        SC: 0,
        BBV: 0,
        "AP": 0,
    }

    if type == "exercise":
        type = 0
    if type == "fight":
        type = 1

    if timer.image_exist(IMG.fight_image[12]):
        # 特殊补给舰
        enemy_type_count[SAP] = 1

    # 处理图像并将参数传递给识别图像的程序
    img = PIM.fromarray(timer.screen).convert("L")
    img = img.resize((960, 540))
    input_path = os.path.join(TUNNEL_ROOT, "args.in")
    output_path = os.path.join(TUNNEL_ROOT, "res.out")
    delete_file(output_path)
    args = "recognize\n6\n"
    for i, area in enumerate(TYPE_SCAN_AREA[type]):
        arr = np.array(img.crop(area))
        args += matrix_to_str(arr)
    with open(input_path, "w") as f:
        f.write(args)
    recognize_enemy_exe = os.path.join(TUNNEL_ROOT, "recognize_enemy.exe")
    subprocess.run([recognize_enemy_exe, TUNNEL_ROOT])

    # 获取并解析结果
    res = read_file(os.path.join(TUNNEL_ROOT, "res.out")).split()
    enemy_type_count["ALL"] = 0
    for i, x in enumerate(res):
        enemy_type_count[x] += 1
        if x != NO:
            enemy_type_count["ALL"] += 1
    enemy_type_count[NAP] = enemy_type_count["AP"] - enemy_type_count[SAP]
    count = {}
    for key, value in enemy_type_count.items():
        if value:
            count[key] = value
    timer.logger.debug("enemys:" + str(count))
    return count


def detect_ship_stats(timer: Timer, type="prepare", previous=None):
    """检查我方舰船的血量状况(精确到红血黄血绿血)并返回

    Args:
        type (str, optional): 描述在哪个界面检查. .
            'prepare': 战斗准备界面

            'sumup': 单场战斗结算界面
    Returns:
        list: 表示血量状态

        example: [-1, 0, 0, 1, 1, 2, -1] 表示 1-2 号位绿血 3-4 号位中破, 5 号位大破, 6 号位不存在

    """
    # Todo: 检测是否满血/触发中保, 精确到数值的检测, 战斗结算时检测不依赖先前信息

    timer.update_screen()
    result = [-1, 0, 0, 0, 0, 0, 0]
    for i in range(1, 7):
        if type == "prepare":
            pixel = timer.get_pixel(*BLOOD_BAR_POSITION[0][i])
            result[i] = CheckColor(pixel, COLORS.BLOOD_COLORS[0])
            if result[i] in [3, 2]:
                result[i] = 2
            elif result[i] == 0:
                result[i] = 0
            elif result[i] == 4:
                result[i] = -1
            else:
                result[i] = 1
        elif type == "sumup":
            if previous and previous[i] == -1:
                result[i] = -1
                continue
            pixel = timer.get_pixel(*BLOOD_BAR_POSITION[1][i])
            result[i] = CheckColor(pixel, COLORS.BLOOD_COLORS[1])
            if result[i] == 4:
                result[i] = -1
    return result


def detect_ship_type(timer: Timer):
    """ToDo
    在出征准备界面读取我方所有舰船类型并返回该列表
    """


def get_exercise_stats(timer: Timer, robot=None):
    """检查演习界面, 第 position 个位置,是否为可挑战状态, 强制要求屏幕中只有四个目标

    Args:
        position (_type_): 编号从屏幕中的位置编起, 如果滑动显示了第 2-5 个敌人, 那么第二个敌人编号为 1

    Returns:
        bool: 如果可挑战, 返回 True , 否则为 False, 1-index
    """
    timer.update_screen()
    up = timer.check_pixel((933, 59), (177, 171, 176), distance=60)
    down = timer.check_pixel((933, 489), (177, 171, 176), distance=60)
    assert (up and down) == False

    result = [
        None,
    ]
    if up == False and down == False:
        timer.swipe(800, 200, 800, 400)  # 上滑
        timer.update_screen()
        up = True
    if up:
        for position in range(1, 5):
            result.append(
                math.sqrt(
                    CalcDis(
                        timer.get_pixel(770, position * 110 - 10), COLORS.CHALLENGE_BLUE
                    )
                )
                <= 50
            )
        timer.swipe(800, 400, 800, 200)  # 下滑
        timer.update_screen()
        result.append(
            math.sqrt(
                CalcDis(timer.get_pixel(770, 4 * 110 - 10), COLORS.CHALLENGE_BLUE)
            )
            <= 50
        )
        return result
    if down:
        for position in range(1, 5):
            result.append(
                math.sqrt(
                    CalcDis(
                        timer.get_pixel(770, position * 110 - 10), COLORS.CHALLENGE_BLUE
                    )
                )
                <= 50
            )
        if robot is not None:
            result.insert(1, robot)
        else:
            timer.swipe(800, 200, 800, 400)  # 上滑
            timer.update_screen()
            result.insert(
                1,
                math.sqrt(
                    CalcDis(timer.get_pixel(770, 4 * 110 - 10), COLORS.CHALLENGE_BLUE)
                )
                <= 50,
            )

            timer.swipe(800, 400, 800, 200)  # 下滑

        return result


def check_support_stats(timer: Timer):
    """在出征准备界面检查是否开启了战役支援(有开始出征按钮的界面)

    Returns:
        bool: 先判断是否为灰色，如果为灰色则返回True，然后判断是否开启，如果开启则返回True，否则返回False
    """
    timer.update_screen()
    pixel = timer.get_pixel(623, 75)
    d1 = CalcDis(pixel, COLORS.SUPPORT_ENABLE)  # 支援启用的黄色
    d2 = CalcDis(pixel, COLORS.SUPPORT_DISABLE)  # 支援禁用的蓝色
    d3 = CalcDis(pixel, COLORS.SUPPORT_ENLESS)  # 支援次数用尽的灰色
    if d1 > d3 and d2 > d3:
        timer.logger.info("战役支援次数已用尽")
        return True
    else:
        return d1 < d2
