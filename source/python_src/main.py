
import datetime
import os
import sys
import time

import keyboard as kd

import constants.global_attributes as Globals
import constants.settings as S
from constants.load_data import load_all_data
from controller.run_timer import Timer
from fight.battle import BattlePlan
from fight.exercise import NormalExercisePlan
from fight.normal_fight import NormalFightPlan
from game.game_operation import GainBounds, RepairByBath
from ocr.ship_name import recognize_ship
from source.python_src.constants.settings import UI

sys.path.append(os.getcwd())
sys.path.append(os.path.dirname(__file__))


finished = 1
timer = None
S.DEBUG = True

def load_data_start():
    global timer
    timer = Timer()
    load_all_data(timer)


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
    load_all_data()
    ui = UI()
    timer = Timer(ui)
    timer.setup(device_name, account, password)
    
    return timer


def listener(event: kd.KeyboardEvent):
    global main_thread
    on_press = Globals.event_pressed
    if (event.event_type == 'down'):
        if (event.name in on_press):
            return
        on_press.add(event.name)
    if (event.event_type == 'up'):
        on_press.discard(event.name)

    if ('ctrl' in on_press and 'alt' in on_press and 'c' in on_press):
        Globals.script_end = 1
        print("Script end by user request")
        quit()

