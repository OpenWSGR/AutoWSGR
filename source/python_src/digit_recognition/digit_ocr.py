from curses.ascii import isdigit
import cv2
import pytesseract
from game import *
from utils.image_position import crop_image
from utils.io import yaml_to_dict

POS = yaml_to_dict('./source/python_src/digit_recognition/relative_location.yaml')


def get_resources(timer):
    """ 获取资源数据 """
    goto_game_page(timer, 'main_page')
    image = timer.screen

    ret = {}
    for key in POS['main_page']['resources']:
        image_crop = crop_image(image, *POS['main_page']['resources'][key])
        raw_str = pytesseract.image_to_string(image_crop).strip()  # 原始字符串

        if raw_str[-1] == 'K':
            num = raw_str[:-1]
            unit = 1000
        elif raw_str[-1] == 'M':
            num = raw_str[:-1]
            unit = 1000000
        else:
            num = raw_str
            unit = 1
        
        # 容错处理，如果监测出来不是数字则出错了
        try:
            ret[key] = eval(num) * unit
        except NameError:
            print("读取资源失败！")
            quit()

    return ret


def get_loot_and_ship(timer):
    """ 获取掉落数据 """
    goto_game_page(timer, 'map_page')
    image = timer.screen

    ret = {}
    for key in POS['map_page']:
        image_crop = crop_image(image, *POS['map_page'][key])
        raw_str = pytesseract.image_to_string(image_crop).strip()  # 原始字符串
        try:
            ret[key] = eval(raw_str.split('/')[0])  # 当前值
            ret[key+'_max'] = eval(raw_str.split('/')[1])  # 最大值
        except NameError:
            print("读今日战利品、捞船失败！")
            quit()

    return ret
