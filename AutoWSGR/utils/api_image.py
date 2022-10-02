import numpy as np
from AutoWSGR.constants.image_templates import MyTemplate


def relative_to_absolute(record_pos, resolution=(960, 540)):
    """ 将相对坐标转换为绝对坐标 """
    delta_x, delta_y = record_pos
    _w, _h = resolution
    target_x = _w * (0.5 + delta_x)
    target_y = _h * (0.5 + delta_y)
    return target_x, target_y


def absolute_to_relative(absolute_pos, resolution=(960, 540)):
    """ 将绝对坐标转换为相对坐标 """
    _w, _h = resolution
    delta_x = (absolute_pos[0] - _w * 0.5) / _w
    delta_y = (absolute_pos[1] - _h * 0.5) / _h
    return delta_x, delta_y


def crop_image(image, pos1, pos2, resolution=(960, 540)):
    """ 按照给定的位置裁剪图片, pos1 左下角, pos2 右上角 """
    x1, y2 = map(int, relative_to_absolute(pos1, resolution))
    x2, y1 = map(int, relative_to_absolute(pos2, resolution))
    return image[y1:y2, x1:x2]


def convert_position(x, y, resolution, mode='960_to_this'):
    """转化坐标格式(放缩)

    Args:
        x (int): 横坐标
        y (int): 纵坐标
        mode (str): 工作模式
            values:
                '960_to_this':将 960x540 格式转化为当前模拟器屏幕坐标
                'this_to_960':将当前模拟器屏幕坐标转化为 960x540 格式

    Returns:Tuple(int,int)

        mode='960_to_this': 对应到当前模拟器屏幕上的坐标
        mode='this_to_960': 960x540 格式坐标
    Raise:
        ValueError:如果不支持这个模式
    """

    if (mode == '960_to_this'):
        return (int(x / 960 * resolution[0]), int(y / 540 * resolution[1]))
    if (mode == 'this_to_960'):
        return (int(x * 960 / resolution[0]), int(y * 540 / resolution[1]))
    raise ValueError("unsupported mode " + str(mode))


def convert_area(area, resolution, mode='960_to_this'):
    """转化矩阵格式(放缩)

    Args:
        area list(left, top, right, buttom): 矩阵,列表或者元组
        mode (str): 工作模式
            values:
                '960_to_this':将 960x540 格式转化为当前模拟器屏幕坐标
                'this_to_960':将当前模拟器屏幕坐标转化为 960x540 格式

    Returns:
        (left, top, right, buttom): 转化后的矩阵(元组)
    """
    left, top = convert_position(area[0], area[1], resolution, mode)
    right, buttom = convert_position(area[2], area[3], resolution, mode)
    return (left, top, right, buttom)


def locateCenterOnImage(image: np.ndarray, query: MyTemplate, confidence=0.85, this_mehods=['tpl']):
    """从原图像中尝试找出一个置信度相对于模板图像最高的矩阵区域的中心坐标

    Args:
        image (np.ndarray): 原图像
        query (MyTemplate): 模板图像
        confidence (float, optional): 置信度阈值. Defaults to 0.85.
        this_mehods (list, optional): 匹配方式. Defaults to ['tpl'].

    Returns:
        如果匹配结果中有超过阈值的,返回置信度最高的结果的中心绝对坐标:Tuple(int,int)

        否则返回 None 
    """
    query.threshold = confidence
    match_pos = query.match_in(image, this_methods=this_mehods)
    return match_pos or None
