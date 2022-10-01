import os, sys, re

sys.path.append(os.path.dirname(os.path.dirname(__file__))) 

from wsgr import start_script
from source.python_src.controller.run_timer import Timer
from source.python_src.utils.io import listdir, dict_to_yaml, yaml_to_dict
from source.python_src.utils.api_image import relative_to_absolute
import easyocr 
import keyboard
import cv2
# en_reader = easyocr.Reader(['en'], gpu=False)
timer = None
point = 'A'

def ocr(image):
    img = cv2.imread(image)
    
    # cv2.imshow("window", img)
    # cv2.waitKey(0)
    # result = en_reader.readtext(img)
    # for box in result:
    #    print(box)
    pass


def log_image(event:keyboard.KeyboardEvent):
    if(event.event_type != 'down' or event.name != 'P'):
        return 
    print("Screen Processing")
    
    timer.update_screen()
    timer.log_screen()
    

def SetPoints(windowname, img):
    """
    输入图片，打开该图片进行标记点，返回的是标记的几个点的字符串
    """
    global point
    point = 'A'
    print('(提示：单击需要标记的坐标，Enter确定，Esc跳过，其它重试。)')
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
        print('坐标为：', points)
        del temp_img
        cv2.destroyAllWindows()
        str(points)
    elif key == 27:  # ESC
        print('跳过该张图片')
        del temp_img
        cv2.destroyAllWindows()
    else:
        print('重试!')
        SetPoints(windowname, img)
    
    print(points)
    return points


def get_image():
    global timer
    timer = start_script(to_main_page=False)
    print("HOOKED")
    keyboard.hook(callback=log_image)
    import time
    time.sleep(1000)


def make_map(image_path):
    files = listdir(image_path)
    dict_dir = r'data\map\event\20220928'
    for file in files:
        name = os.path.basename(file)
        dict_value = SetPoints(name, cv2.imread(file))
        dict_to_yaml(dict_value, os.path.join(dict_dir, name + '.yaml'))


def coverter(dst_path=r"data\map\normal"):
    with open(r"data\map\image\normal\points.txt", mode='r') as f:
        lines = f.read().split('\n')
        res = {}
        for line in lines:
            result = re.findall(r'\(.{5,13}\)', line)
            point, position = eval(result[0]), eval(result[1])
            # print(point, position)
            key1, key2 = point[:2], point[2]
            if(key1 not in res.keys()):
                res[key1] = {}
            res[key1][key2] = position
            
    print(res) 
    for key, value in res.items():
        file_name = str(key[0]) + "-" + str(key[1]) + '.yaml'
        dict_to_yaml(value, os.path.join(dst_path, file_name))
        

def coverter_9_1():
    print(relative_to_absolute((-0.22, -0.18)))
    print(relative_to_absolute((-0.272, -0.029)))
    print(relative_to_absolute((-0.361, 0.07)))
    print(relative_to_absolute((0.139, -0.158)))
    print(relative_to_absolute((-0.005, -0.1)))
    print(relative_to_absolute((-0.109, 0.052)))
    print(relative_to_absolute((-0.189, 0.154)))
    print(relative_to_absolute((-0.048, 0.242)))
    print(relative_to_absolute((-0.001, 0.186)))
    print(relative_to_absolute((0.062, 0.13)))
    print(relative_to_absolute((0.131, -0.064)))
    print(relative_to_absolute((0.296, -0.203)))
    print(relative_to_absolute((0.265, -0.04)))
    print(relative_to_absolute((0.406, 0.06)))
    print(relative_to_absolute((0.264, 0.157)))

coverter_9_1()
# coverter()
# make_map(r'data\map\image\event\20220928')
# get_image()