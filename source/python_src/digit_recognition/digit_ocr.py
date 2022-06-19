import cv2
import pytesseract
from utils.position_utils import relative_to_absolute
from utils.io_utils import yaml_to_dict
from game import *

POS = yaml_to_dict('./source/python_src/digit_recognition/relative_location.yaml')


def crop_image(image, pos1, pos2, resolution=(960, 540)):
    """ 按照给定的位置裁剪图片 """
    x1, y2 = map(int, relative_to_absolute(pos1, resolution))
    x2, y1 = map(int, relative_to_absolute(pos2, resolution))
    return image[y1:y2, x1:x2]


def get_resources(timer):
    """ 获取资源数据 """
    goto_game_page(timer, 'main_page')
    image = timer.screen

    ret = {}
    for key in POS['main_page']['resources']:
        image_crop = crop_image(image, *POS['main_page']['resources'][key])
        ret[key] = pytesseract.image_to_string(image_crop).strip()

    return ret


def get_loot_and_ship(timer):
    """ 获取掉落数据 """
    goto_game_page(timer, 'map_page')
    image = timer.screen

    ret = {}
    for key in POS['map_page']:
        image_crop = crop_image(image, *POS['map_page'][key])
        ret[key] = pytesseract.image_to_string(image_crop).strip()

    return ret
