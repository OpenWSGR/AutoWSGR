from typing import List, Tuple

import cv2
import numpy as np

from autowsgr.constants.image_templates import MyTemplate


def relative_to_absolute(record_pos, resolution=(960, 540)):
    """将相对坐标转换为绝对坐标"""
    rel_x, rel_y = record_pos
    _w, _h = resolution
    assert 0 <= rel_x <= 1 and 0 <= rel_y <= 1, "rel_x and rel_y should be in [0, 1]"
    abs_x = _w * rel_x
    abs_y = _h * rel_y
    return abs_x, abs_y


def cv_show_image(img):
    """调试用, 展示图像, 按任意键关闭窗口

    img: numpy.ndarray 格式的图片
    """
    cv2.imshow("Image", img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def absolute_to_relative(absolute_pos, resolution=(960, 540)):
    """将绝对坐标转换为相对坐标"""
    abs_x, abs_y = absolute_pos
    _w, _h = resolution
    assert (
        0 <= abs_x <= _w and 0 <= abs_y <= _h
    ), "abs_x and abs_y should be in [0, resolution]"
    rel_x = abs_x / _w
    rel_y = abs_y / _h
    return rel_x, rel_y


# https://github.com/leimao/Rotated-Rectangle-Crop-OpenCV/blob/master/rotated_rect_crop.py
def inside_rect(rect, num_cols, num_rows):
    # Determine if the four corners of the rectangle are inside the rectangle with width and height
    # rect tuple
    # center (x,y), (width, height), angle of rotation (to the row)
    # center  The rectangle mass center.
    # center tuple (x, y): x is regarding to the width (number of columns) of the image, y is regarding to the height (number of rows) of the image.
    # size    Width and height of the rectangle.
    # angle   The rotation angle in a clockwise direction. When the angle is 0, 90, 180, 270 etc., the rectangle becomes an up-right rectangle.
    # Return:
    # True: if the rotated sub rectangle is side the up-right rectange
    # False: else

    rect_center = rect[0]
    rect_center_x = rect_center[0]
    rect_center_y = rect_center[1]

    rect_width, rect_height = rect[1]

    rect_angle = rect[2]

    if (rect_center_x < 0) or (rect_center_x > num_cols):
        return False
    if (rect_center_y < 0) or (rect_center_y > num_rows):
        return False

    # https://docs.opencv.org/3.0-beta/modules/imgproc/doc/structural_analysis_and_shape_descriptors.html
    box = cv2.boxPoints(rect)

    x_max = int(np.max(box[:, 0]))
    x_min = int(np.min(box[:, 0]))
    y_max = int(np.max(box[:, 1]))
    y_min = int(np.min(box[:, 1]))

    if (x_max <= num_cols) and (x_min >= 0) and (y_max <= num_rows) and (y_min >= 0):
        return True
    else:
        return False


def rect_bbx(rect):
    # Rectangle bounding box for rotated rectangle
    # Example:
    # rotated rectangle: height 4, width 4, center (10, 10), angle 45 degree
    # bounding box for this rotated rectangle, height 4*sqrt(2), width 4*sqrt(2), center (10, 10), angle 0 degree

    box = cv2.boxPoints(rect)

    x_max = int(np.max(box[:, 0]))
    x_min = int(np.min(box[:, 0]))
    y_max = int(np.max(box[:, 1]))
    y_min = int(np.min(box[:, 1]))

    # Top-left
    # (x_min, y_min)
    # Top-right
    # (x_min, y_max)
    # Bottom-left
    #  (x_max, y_min)
    # Bottom-right
    # (x_max, y_max)
    # Width
    # y_max - y_min
    # Height
    # x_max - x_min
    # Center
    # (x_min + x_max) // 2, (y_min + y_max) // 2

    center = (int((x_min + x_max) // 2), int((y_min + y_max) // 2))
    width = int(x_max - x_min)
    height = int(y_max - y_min)
    angle = 0

    return (center, (width, height), angle)


def image_rotate_without_crop(mat, angle):
    # https://stackoverflow.com/questions/22041699/rotate-an-image-without-cropping-in-opencv-in-c
    # angle in degrees

    height, width = mat.shape[:2]
    image_center = (width / 2, height / 2)

    rotation_mat = cv2.getRotationMatrix2D(image_center, angle, 1)

    abs_cos = abs(rotation_mat[0, 0])
    abs_sin = abs(rotation_mat[0, 1])

    bound_w = int(height * abs_sin + width * abs_cos)
    bound_h = int(height * abs_cos + width * abs_sin)

    rotation_mat[0, 2] += bound_w / 2 - image_center[0]
    rotation_mat[1, 2] += bound_h / 2 - image_center[1]

    rotated_mat = cv2.warpAffine(mat, rotation_mat, (bound_w, bound_h))

    return rotated_mat


def crop_rectangle_relative(image, x_ratio, y_ratio, width_ratio, height_ratio):
    """
    根据相对坐标和尺寸裁剪图像。

    参数:
    image -- 输入的 numpy 数组格式的图像。image[row][col]
    x_ratio -- 左上角 x 坐标的相对位置
    y_ratio -- 左上角 y 坐标的相对位置
    width_ratio -- 裁剪区域的宽度相对图像宽度的比例
    height_ratio -- 裁剪区域的高度相对图像高度的比例

    返回:
    cropped_image -- 裁剪后的图像。
    """
    # 获取图像的尺寸
    height, width = image.shape[:2]

    # 计算裁剪区域的左上角坐标和尺寸
    start_x = int(width * x_ratio)
    start_y = int(height * y_ratio)
    end_x = start_x + int(width * width_ratio)
    end_y = start_y + int(height * height_ratio)

    # 裁剪图像
    cropped_image = image[start_y:end_y, start_x:end_x]

    return cropped_image


def crop_rectangle(image, rect):
    # rect has to be upright

    num_rows = image.shape[0]
    num_cols = image.shape[1]

    if not inside_rect(rect=rect, num_cols=num_cols, num_rows=num_rows):
        print("Proposed rectangle is not fully in the image.")
        return None

    rect_center = rect[0]
    rect_center_x = rect_center[0]
    rect_center_y = rect_center[1]
    rect_width = rect[1][0]
    rect_height = rect[1][1]

    return image[
        rect_center_y
        - rect_height // 2 : rect_center_y
        + rect_height
        - rect_height // 2,
        rect_center_x - rect_width // 2 : rect_center_x + rect_width - rect_width // 2,
    ]


def crop_rotated_rectangle(image, rect):
    # Crop a rotated rectangle from a image

    num_rows = image.shape[0]
    num_cols = image.shape[1]

    if not inside_rect(rect=rect, num_cols=num_cols, num_rows=num_rows):
        print("Proposed rectangle is not fully in the image.")
        return None

    rotated_angle = rect[2]

    rect_bbx_upright = rect_bbx(rect=rect)
    rect_bbx_upright_image = crop_rectangle(image=image, rect=rect_bbx_upright)

    rotated_rect_bbx_upright_image = image_rotate_without_crop(
        mat=rect_bbx_upright_image, angle=rotated_angle
    )

    rect_width = rect[1][0]
    rect_height = rect[1][1]

    crop_center = (
        rotated_rect_bbx_upright_image.shape[1] // 2,
        rotated_rect_bbx_upright_image.shape[0] // 2,
    )

    return rotated_rect_bbx_upright_image[
        crop_center[1]
        - rect_height // 2 : crop_center[1]
        + (rect_height - rect_height // 2),
        crop_center[0]
        - rect_width // 2 : crop_center[0]
        + (rect_width - rect_width // 2),
    ]


def crop_image(image, pos1, pos2, rotation=0, debug=False):
    """裁剪出矩形, pos1 左下角相对位置, pos2 右上角相对位置。如果指定旋转角度，则返回剪裁+旋转后的图片

    Args:
        image (np.ndarray): 图片
        pos1 (Tuple[float, float]): 左下角相对位置
        pos2 (Tuple[float, float]): 右上角相对位置
        rotation (int, optional): 旋转角度[-180, 180]. 正值逆时针旋转. Defaults to 0.
        debug (bool, optional): 是否保存调试图片. Defaults to False.
    """
    resolution = (image.shape[1], image.shape[0])
    x1, y2 = map(int, relative_to_absolute(pos1, resolution))
    x2, y1 = map(int, relative_to_absolute(pos2, resolution))

    if rotation == 0:
        ret = image[y1:y2, x1:x2]
    else:
        # 矩形的对角线长度，以及对角线角度
        diag = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        diag_orientation = np.arctan2(y2 - y1, x2 - x1)
        diag_angle = diag_orientation - np.radians(rotation)
        # 计算矩形长、宽
        width = int(diag * np.cos(diag_angle))
        height = int(diag * np.sin(diag_angle))
        # 结构化表示矩形
        rect = ((x1 + x2) // 2, (y1 + y2) // 2), (width, height), 360 - rotation
        ret = crop_rotated_rectangle(image, rect)

    if debug:
        cv2.imwrite("crop_image.png", ret)

    return ret


def locateCenterOnImage(
    image: np.ndarray, query: MyTemplate, confidence=0.85, this_methods=None
):
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


def match_nearest_index(
    pos: Tuple[int, int], positions: List[Tuple[int, int]], metric: str = "l2"
):
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
