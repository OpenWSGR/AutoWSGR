from typing import List, Tuple

import numpy as np
from PIL import Image

from autowsgr.constants.image_templates import MyTemplate


def relative_to_absolute(record_pos, resolution=(960, 540)):
    """将相对坐标转换为绝对坐标"""
    rel_x, rel_y = record_pos
    _w, _h = resolution
    assert 0 <= rel_x <= 1 and 0 <= rel_y <= 1, "rel_x and rel_y should be in [0, 1]"
    abs_x = _w * rel_x
    abs_y = _h * rel_y
    return abs_x, abs_y


def absolute_to_relative(absolute_pos, resolution=(960, 540)):
    """将绝对坐标转换为相对坐标"""
    abs_x, abs_y = absolute_pos
    _w, _h = resolution
    assert 0 <= abs_x <= _w and 0 <= abs_y <= _h, "abs_x and abs_y should be in [0, resolution]"
    rel_x = abs_x / _w
    rel_y = abs_y / _h
    return rel_x, rel_y


def crop_image(image, pos1, pos2, resolution=(960, 540), debug=False):
    """按照给定的位置裁剪图片, pos1 左下角, pos2 右上角"""
    x1, y2 = map(int, relative_to_absolute(pos1, resolution))
    x2, y1 = map(int, relative_to_absolute(pos2, resolution))
    ret = image[y1:y2, x1:x2]

    if debug:
        print((x1, y1), (x2, y2))
        img = Image.fromarray(ret, "RGB")
        img.save("crop_image.png")

    return ret


def locateCenterOnImage(image: np.ndarray, query: MyTemplate, confidence=0.85, this_methods=None):
    """从原图像中尝试找出一个置信度相对于模板图像最高的矩阵区域的中心坐标

    Args:
        image (np.ndarray): 原图像
        query (MyTemplate): 模板图像
        confidence (float, optional): 置信度阈值. Defaults to 0.85.
        this_methods (list, optional): 匹配方式. Defaults to ['tpl'].

    Returns:
        如果匹配结果中有超过阈值的,返回置信度最高的结果的中心绝对坐标:Tuple(int,int)

        否则返回 None
    """
    if this_methods is None:
        this_methods = ["tpl"]
    query.threshold = confidence
    match_pos = query.match_in(image, this_methods=this_methods)
    return match_pos or None


def match_nearest_index(pos: Tuple[int, int], positions: List[Tuple[int, int]], metric: str = "l2"):
    """找出离目标点最近的点的索引

    Args:
        pos (Tuple[int, int]): 目标点
        positions (List[Tuple[int, int]]): 点的列表
        metric (str, optional): 距离度量方式. Defaults to "l2".
    Returns:
        int: 最近点的索引
    """
    min_distance = float("inf")
    min_index = -1
    for i, p in enumerate(positions):
        if metric == "l2":
            distance = (p[0] - pos[0]) ** 2 + (p[1] - pos[1]) ** 2
        elif metric == "l1":
            distance = abs(p[0] - pos[0]) + abs(p[1] - pos[1])
        else:
            raise ValueError("unsupported metric " + str(metric))
        if distance < min_distance:
            min_distance = distance
            min_index = i
    return min_index
