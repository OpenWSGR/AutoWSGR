import os
import pathlib
import sys


sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import cv2
import keyboard
from numpy.typing import NDArray

from autowsgr.timer import Timer
from autowsgr.utils.io import dict_to_yaml, listdir


class LightweightTimer(Timer):
    """轻量级 Timer，仅用于截图功能，跳过不必要的模块加载"""

    def __init__(self, config, logger) -> None:
        # 只初始化必要的属性
        self.config = config
        self.logger = logger

        # 初始化日志相关的基础属性
        self.everyday_check = True
        self.ship_stats = [0, 0, 0, 0, 0, 0, 0]
        self.enemy_type_count = {}
        self.now_page = None
        self.resources = None
        self.got_ship_num = 0
        self.got_loot_num = 0
        self.quick_repaired_cost = 0
        self.can_get_loot = False

        # 跳过 initialize_resources()、initialize_controllers()、initialize_ocr() 和 init()
        # 直接调用父类的 AndroidController 初始化以获得截图功能
        self.initialize_controllers()


# en_reader = easyocr.Reader(['en'], gpu=False)
timer = None
point = 'A'
screen_shot_count = 0


def log_image(event: keyboard.KeyboardEvent):
    global screen_shot_count
    assert isinstance(timer, Timer)
    if event.event_type != 'down' or event.name != 'P':
        return
    print('Screen Processing:', screen_shot_count)
    screen_shot_count += 1
    timer.update_screen()
    timer.log_screen()


def set_points(windowname, img: NDArray):
    """
    输入图片，打开该图片进行标记点，返回的是标记的几个点的字符串和相对坐标
    """
    global point
    point = 'A'
    print('(提示：单击需要标记的坐标，Enter确定，Esc跳过，其它重试。)')
    points = {}
    relative_points = {}

    def on_mouse(event, x, y, flags, param):
        global point
        if event == cv2.EVENT_LBUTTONDOWN:
            cv2.circle(temp_img, (x, y), 10, (102, 217, 239), -1)
            points[point] = (x, y)
            relative_points[point] = (x / img.shape[1], y / img.shape[0])
            point = chr(ord(point) + 1)
            cv2.imshow(windowname, temp_img)

    temp_img = img.copy()
    cv2.namedWindow(windowname)
    cv2.imshow(windowname, temp_img)
    cv2.setMouseCallback(windowname, on_mouse)
    key = cv2.waitKey(0)
    if key == 13:  # Enter
        print('坐标为：', points)
        print('相对坐标为：', relative_points)
        del temp_img
        cv2.destroyAllWindows()
        str(points)
    elif key == 27:  # ESC
        print('跳过该张图片')
        del temp_img
        cv2.destroyAllWindows()
    else:
        print('重试!')
        set_points(windowname, img)

    print(points)
    print(relative_points)
    return points, relative_points


def get_image() -> None:
    global timer
    # 使用轻量级 Timer 而不是完整的 Timer
    from autowsgr.configs import UserConfig
    from autowsgr.utils.io import yaml_to_dict
    from autowsgr.utils.logger import Logger

    config_dict = yaml_to_dict('../examples/user_settings.yaml')
    config = UserConfig.from_dict(config_dict)
    logger = Logger(config.log_dir, config.log_level)
    timer = LightweightTimer(config, logger)

    import time

    keyboard.hook(log_image)
    time.sleep(1000)


def make_map(image_path: str, dict_dir: str) -> None:
    """根据图像目录下的所有图片文件,打开后顺次点击ABCD,生成对应文件名的地图文件

    Args:
        image_path (_type_): _description_
        dict_dir (_type_): _description_
    """
    files = listdir(image_path)
    for file in files:
        f = pathlib.Path(file)
        if f.suffix != '.PNG':
            continue
        name = f.stem
        dict_value, relative_value = set_points(name, cv2.imread(file))
        dict_to_yaml(dict_value, os.path.join(dict_dir, 'E-' + name[1:] + '.yaml'))
        dict_to_yaml(dict_value, os.path.join(dict_dir, 'H-' + name[1:] + '.yaml'))
        dict_to_yaml(
            relative_value,
            os.path.join(dict_dir, 'E-' + name[1:] + '_relative.yaml'),
        )


if __name__ == '__main__':
    print(
        """Input operation type:
          1: log image when 'P' pressed.
          2: make map .yaml files""",
    )
    oper = input().split()[0]
    if oper == '1':
        get_image()
    elif oper == '2':
        print('Enter image_path:')
        image_path = input()
        print('Enter dict_path')
        dict_path = input()
        make_map(image_path, dict_path)
