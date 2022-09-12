
import datetime
import time

import keyboard as kd

import constants.global_attributes as Globals
import constants.settings as S
from fight_dh.battle import BattlePlan
from fight_dh.normal_fight import NormalFightPlan
from fight_dh.exercise import NormalExercisePlan
from game.game_operation import (GainBounds, RepairByBath, expedition, restart,
                                 start_game)
from game.get_game_info import ExpeditionStatus, Resources
from ocr.ship_name import recognize_ship
from constants.load_data import load_all_data
from controller.run_timer import Timer

import os, sys

sys.path.append(os.getcwd())
sys.path.append(os.path.dirname(__file__))


finished = 1
timer = None
S.DEBUG = False

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
    timer = Timer()
    timer.device_name = device_name
    load_all_data()
    timer.Windows.ConnectAndroid()
    timer.UpdateScreen()
    timer.resolution = timer.screen.shape[:2]
    timer.resolution = timer.resolution[::-1]
    from utils.logger import time_path
    timer.log_filepre = time_path
    if account != None and password != None:
        restart(timer, account=account, password=password)
    if timer.Android.is_game_running() == False:
        start_game(timer)
    print("resolution:", timer.resolution)
    timer.ammo = 10
    timer.expedition_status = ExpeditionStatus(timer)
    # timer.fight_result = FightResult(timer)
    timer.resources = Resources(timer)
    timer.GoMainPage()
    try:
        timer.set_page()
    except Exception:
        if S.DEBUG:
            timer.set_page('main_page')
        else:
            restart(timer)
            timer.set_page()
    print(timer.now_page)
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

