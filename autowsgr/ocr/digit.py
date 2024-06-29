import os

import numpy as np

from autowsgr.controller.run_timer import Timer
from autowsgr.ocr.ship_name import recognize_number
from autowsgr.constants.data_roots import OCR_ROOT
# import pytesseract
# from AutoWSGR.ocr.ship_name import recognize_number
from autowsgr.utils.api_image import crop_image
from autowsgr.utils.io import yaml_to_dict

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
        raw_str_list = recognize_number(image_crop, "KM.")
        try:
            # if raw_str_list[0][2] < 0.99:
            #     timer.logger.error(f"识别失败：{key},{raw_str_list[0][1]},confidence:{raw_str_list[0][2]}")
            #     continue
            raw_str = raw_str_list[0][1]
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
            timer.logger.error(f"读取{key}资源失败：{raw_str_list}")
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
        raw_str_list = recognize_number(image_crop, "/")
        try:
            # if raw_str_list[0][2] < 0.99:
            #     timer.logger.error(f"识别失败：{key},{raw_str_list[0][1]},confidence:{raw_str_list[0][2]}")
            #     continue
            raw_str = raw_str_list[0][1]
            ret[key] = eval(raw_str.split("/")[0])  # 当前值
            ret[key + "_max"] = eval(raw_str.split("/")[1])  # 最大值
        except:
            timer.logger.error(f"读取{key}数量失败：{raw_str_list}")
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
