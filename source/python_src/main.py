
import datetime
import os
import sys
import time

import keyboard as kd

from constants.settings import S
from controller.run_timer import Timer
from fight.battle import BattlePlan
from fight.exercise import NormalExercisePlan
from fight.normal_fight import NormalFightPlan
from game.game_operation import GainBounds, RepairByBath
# from ocr.ship_name import recognize_ship

sys.path.append(os.getcwd())
sys.path.append(os.path.dirname(__file__))


event_pressed = set()
script_end = 0
S.DEBUG = True

def lencmp(s1, s2):
    if(len(s1) < len(s2)):
        return 1
    if(len(s1) > len(s2)):
        return -1
    return 0


def start_script(device_name="emulator-5554", account=None, password=None):
    """启动脚本,返回一个 Timer 记录器

    Returns:
        Timer: 该模拟器的记录器
    """
    timer = Timer()
    timer.setup(device_name, account, password)
    
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

