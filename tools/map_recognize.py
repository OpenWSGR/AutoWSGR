import os
import pathlib
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import cv2
import easyocr
import keyboard

from AutoWSGR.controller.run_timer import Timer
from AutoWSGR.scripts.main import start_script
from AutoWSGR.utils.api_image import relative_to_absolute
from AutoWSGR.utils.io import dict_to_yaml, listdir, yaml_to_dict

# en_reader = easyocr.Reader(['en'], gpu=False)
timer = None
point = "A"
screen_shot_count = 0


def ocr(image):
    img = cv2.imread(image)

    # cv2.imshow("window", img)
    # cv2.waitKey(0)
    # result = en_reader.readtext(img)
    # for box in result:
    #    print(box)
    pass


def log_image(event: keyboard.KeyboardEvent):
    global screen_shot_count
    assert type(timer) == Timer
    if event.event_type != "down" or event.name != "P":
        return
    print("Screen Processing:", screen_shot_count)
    screen_shot_count += 1
    timer.update_screen()
    timer.log_screen()


def SetPoints(windowname, img):
    """
    输入图片，打开该图片进行标记点，返回的是标记的几个点的字符串
    """
    global point
    point = "A"
    print("(提示：单击需要标记的坐标，Enter确定，Esc跳过，其它重试。)")
    points = {}

    def onMouse(event, x, y, flags, param):
        global point
        if event == cv2.EVENT_LBUTTONDOWN:
            cv2.circle(temp_img, (x, y), 10, (102, 217, 239), -1)
            points[point] = (x, y)
            point = chr(ord(point) + 1)
            cv2.imshow(windowname, temp_img)

    temp_img = img.copy()
    cv2.namedWindow(windowname)
    cv2.imshow(windowname, temp_img)
    cv2.setMouseCallback(windowname, onMouse)
    key = cv2.waitKey(0)
    if key == 13:  # Enter
        print("坐标为：", points)
        del temp_img
        cv2.destroyAllWindows()
        str(points)
    elif key == 27:  # ESC
        print("跳过该张图片")
        del temp_img
        cv2.destroyAllWindows()
    else:
        print("重试!")
        SetPoints(windowname, img)

    print(points)
    return points


def get_image():
    global timer
    timer = start_script(settings_path="user_settings/user_settings.yaml")
    print("HOOKED")
    keyboard.hook(callback=log_image)
    import time

    time.sleep(1000)


def make_map(image_path, dict_dir):
    """根据图像目录下的所有图片文件,打开后顺次点击ABCD,生成对应文件名的地图文件

    Args:
        image_path (_type_): _description_
        dict_dir (_type_): _description_
    """
    files = listdir(image_path)
    dict_dir = dict_dir
    for file in files:
        import pathlib

        f = pathlib.Path(file)
        if f.suffix != ".PNG":
            continue
        name = f.stem
        dict_value = SetPoints(name, cv2.imread(file))
        dict_to_yaml(dict_value, os.path.join(dict_dir, "E-" + name[1:] + ".yaml"))
        dict_to_yaml(dict_value, os.path.join(dict_dir, "H-" + name[1:] + ".yaml"))


if __name__ == "__main__":
    print(
        """Input operation type:
          1: log image when 'P' pressed.
          2: make map .yaml files"""
    )
    oper = input().split()[0]
    if oper == "1":
        get_image()
    elif oper == "2":
        print("Enter image_path:")
        image_path = input()
        print("Enter dict_path")
        dict_path = input()
        make_map(image_path, dict_path)
