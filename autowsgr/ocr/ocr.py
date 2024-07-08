import datetime
from typing import List

import easyocr
from thefuzz import process

from autowsgr.utils.api_image import crop_image, crop_rectangle_relative
from autowsgr.utils.io import cv_imread

# 记录中文ocr识别的错误用于替换。主要针对词表缺失的情况，会导致稳定的识别为另一个字
WORD_REPLACE = {
    "鲍鱼": "鲃鱼",
}

reader = easyocr.Reader(["ch_sim", "en"])


def recognize(
    img,
    allowlist: List[str] = None,  # 识别的字符白名单
    candidates: List[str] = None,  # 识别结果的候选项，如果指定则匹配最接近的
):
    """识别图片中的文字。注意：请确保图片中有文字！总会尝试返回且只返回一个结果"""
    if isinstance(img, str):
        img = cv_imread(img)

    result = reader.readtext(
        img,
        allowlist=allowlist,
        paragraph=True,  # 将识别结果拼成单一字符串
    )
    text = result[0][1]
    # 进行通用替换
    for k, v in WORD_REPLACE.items():
        text = text.replace(k, v)
    if candidates:
        text = process.extractOne(text, candidates)[0]
    return text


# ===== 数字 ======
def recognize_number(img):
    """识别图片中的单个数字"""
    text = recognize(img, allowlist="x0123456789.KM/").replace(" ", "")
    # 决战，费用是f"x{cost}"格式
    if text.startswith("x"):
        return eval(text[1:])
    # 资源可以是K/M结尾
    if text.endswith("K"):
        return eval(text[:-1]) * 1000
    if text.endswith("M"):
        return eval(text[:-1]) * 1000000
    # 普通数字
    return eval(text)


def recognize_time(img):
    """识别f'{hour}:{minute}:{second}'格式的时间"""
    text = recognize(img, allowlist="0123456789:").replace(" ", "")
    return datetime.datetime.strptime(text, "%H:%M:%S").time()


# ===== 文字 ======
def recognize_get_ship(screen, ship_names=None):
    """识别获取 舰船/装备 页面斜着的文字，对原始图片进行旋转裁切"""
    NAME_POSITION = [(0.754, 0.268), (0.983, 0.009), 25]
    name = recognize(crop_image(screen, *NAME_POSITION), candidates=ship_names)

    TYPE_POSITION = [(0.804, 0.27), (0.881, 0.167), 25]
    type = recognize(crop_image(screen, *TYPE_POSITION))

    return name, type


def recognize_number_with_slash(img):
    text = recognize(img, allowlist="0123456789/").replace(" ", "")
    num = text.split("/")
    return num[0], num[1]


def recognize_number_with_colon(img):
    text = recognize(img, allowlist="0123456789:").replace(" ", "")
    num = text.split("/")
    return num[0], num[1]
