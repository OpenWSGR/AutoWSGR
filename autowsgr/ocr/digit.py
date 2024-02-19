import os

import numpy as np

from autowsgr.controller.run_timer import Timer
from autowsgr.ocr.paddle__ocr import paddle_ocr
from autowsgr.ocr.ship_name import recognize_number

# import pytesseract
# from AutoWSGR.ocr.ship_name import recognize_number
from autowsgr.utils.api_image import crop_image
from autowsgr.utils.io import yaml_to_dict

POS = yaml_to_dict(os.path.join(os.path.dirname(__file__), "relative_location.yaml"))


def image_to_number(image: np.ndarray):
    """根据图片返回数字

    Args:
        image (np.ndarray): 图片

    Returns:
        int, None: 存在则返回数字,否则为 None
    """
    # result = pytesseract.image_to_string(image).strip()
    result = recognize_number(image)
    result = result[0][1]
    if len(result) == 0:
        return None
    scale = 1

    if "K" in result:
        result = result[:-2]
        scale = 1000
    if "M" in result:
        result = result[:-2]
        scale = 10**6

    return scale * int(result)


def get_resources(timer: Timer):
    """根据 timer 所处界面获取对应资源数据
    部分 case 会没掉,请重写
    """
    timer.goto_game_page("main_page")
    timer.update_screen()
    image = timer.screen
    ret = {}
    for key in POS["main_page"]["resources"]:
        image_crop = crop_image(image, *POS["main_page"]["resources"][key], resolution=timer.config.resolution)
        raw_str = paddle_ocr(image_crop)
        try:
            raw_str = raw_str[0][1][0]
            if raw_str[-1] == "K":
                num = raw_str[:-1]
                unit = 1000
            elif raw_str[-1] == "M":
                num = raw_str[:-1]
                unit = 1000000
            else:
                num = raw_str
                unit = 1

            ret[key] = eval(num) * unit
        except:
            # 容错处理，如果监测出来不是数字则出错了
            timer.logger.error(f"读取资源失败：{raw_str}")
            timer.logger.error(f"读取资源失败：{ret}")
    timer.logger.info(ret)
    return ret


def get_loot_and_ship(timer: Timer):
    """获取掉落数据"""
    timer.goto_game_page("map_page")
    timer.update_screen()
    image = timer.screen
    ret = {}
    for key in POS["map_page"]:
        image_crop = crop_image(image, *POS["map_page"][key], resolution=timer.config.resolution)
        raw_str = paddle_ocr(image_crop)
        try:
            raw_str = raw_str[0][1][0]
            ret[key] = eval(raw_str.split("/")[0])  # 当前值
            ret[key + "_max"] = eval(raw_str.split("/")[1])  # 最大值
        except:
            if key == "loot":
                timer.logger.error("读今日战利品失败！")
            else:
                timer.logger.error("读今日捞船数量失败！")
    try:
        timer.got_ship_num = ret.get("ship")
    except:
        timer.logger.error("赋值给got_ship_num失败")
        timer.got_ship_num = 0

    try:
        timer.got_loot_num = ret.get("loot")
        if timer.got_loot_num == None:
            timer.got_loot_num = 0
    except:
        timer.logger.error("赋值给got_loot_num失败")
        timer.got_loot_num = 0
    timer.logger.info(f"已掉落胖次:{timer.got_loot_num}")
    timer.logger.info(f"已掉落舰船:{timer.got_ship_num}")
    return ret


def get_flop_ship(timer: Timer):
    pass
