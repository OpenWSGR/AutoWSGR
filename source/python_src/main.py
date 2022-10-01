
import datetime
import os
import sys
import time
import keyboard as kd

sys.path.append(os.getcwd())
sys.path.append(os.path.dirname(__file__))

from constants import S
from controller.run_timer import Timer
# from ocr.ship_name import recognize_ship

event_pressed = set()
script_end = 0
print("main is imported")

def lencmp(s1, s2):
    if(len(s1) < len(s2)):
        return 1
    if(len(s1) > len(s2)):
        return -1
    return 0


def start_script(device_name="emulator-5554", account=None, password=None, to_main_page=True):
    """启动脚本,返回一个 Timer 记录器

    Returns:
        Timer: 该模拟器的记录器
    """
    timer = Timer()
    timer.setup(device_name, account, password, to_main_page)
    
    return timer


def listener(event: kd.KeyboardEvent):
    on_press = event_pressed
    if (event.event_type == 'down'):
        if (event.name in on_press):
            return
        on_press.add(event.name)
    if (event.event_type == 'up'):
        on_press.discard(event.name)

    if ('ctrl' in on_press and 'alt' in on_press and 'c' in on_press):
        global script_end
        script_end = 1
        print("Script end by user request")
        quit()

