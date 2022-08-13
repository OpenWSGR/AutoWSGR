import logging
import os
import sys

import keyboard as kd

from digit_recognition import *
from fight_dh import BattlePlan, NormalFightPlan
from pre_set import *
from save_load import *

sys.path.append(os.getcwd())
sys.path.append(os.path.dirname(__file__))
print(sys.path)


finished = 1
timer = None


def start_script(device_name="emulator-5554", account=None, password=None):
    """启动脚本,返回一个 Timer 记录器

    Returns:
        Timer: 该模拟器的记录器
    """
    timer = Timer()
    timer.device_name = device_name
    load_all_data(timer)
    load_game_ui(timer)
    init_decisive()
    ConnectAndroid(timer)
    UpdateScreen(timer)
    timer.resolution = timer.screen.shape[:2]
    from supports.logger import time_path
    timer.log_filepre = time_path
    if(account != None and password != None):
        restart(timer, account=account, password=password)

    if(is_game_running(timer) == False):
        start_game(timer)

    print("resolution:", timer.resolution)
    timer.ammo = 10
    timer.defaul_repair_logic = RepairBlock()
    timer.defaul_decision_maker = DecisionBlock()
    timer.expedition_status = ExpeditionStatus(timer)
    timer.fight_result = FightResult(timer)
    timer.resources = Resources(timer)
    GetEnemyCondition(timer)
    DetectShipStatu(timer)
    #  GoMainPage(timer)
    try:
        timer.set_page(page_name=get_now_page(timer))
    except:
        if(S.DEBUG):
            timer.set_page('main_page')
        else:
            restart(timer)
            timer.set_page(page_name=get_now_page(timer))

    print(timer.now_page.name)
    return timer


def listener(event: kd.KeyboardEvent):
    global main_thread
    on_press = Globals.event_pressed
    if(event.event_type == 'down'):
        if(event.name in on_press):
            return
        on_press.add(event.name)
    if(event.event_type == 'up'):
        on_press.discard(event.name)

    if('ctrl' in on_press and 'alt' in on_press and 'c' in on_press):
        Globals.script_end = 1
        print("Script end by user request")
        quit()


def main_function():
    global timer
    timer = start_script()
    decisive_fight(timer, '2A')
    normal_exercise(timer, 1)
    friend_exercise(timer, 1)
    battle(timer, 9, 8)

 #   battle(timer, 2, 100, DecisionBlock(SL=True))

 #   normal_exercise(timer, 1)
 #   work(timer, lambda:normal_fight(timer, 8, 5, 4, mod=1), times=300)
 #   decisive_fight(timer,'2A')
 #   normal_exercise(timer, 1)
 #   friend_exercise(timer, 1)
 #   week8(timer, change=0, times=5)
 #   friend_exercise(timer, 1)
 #   timer = start_script()
 #   weekliy(timer)
 #   normal_exercise(timer, 1)
 #   decisive_fight(timer, start='2A')
 #   kd.hook(listener)
 #   kd.hook(keyborad_input)
 #   time.sleep(100000)
    """SetSupport(timer, False)
    SetSupport(timer, False)
    SetSupport(timer, True)
    SetSupport(timer, True)
    week8(timer, change=0)"""


if __name__ == "__main__":

    timer = start_script(account=None, password=None)
    start_time = time.time()

    # # 战役
    # plan2 = BattlePlan(timer, "plans/battle/hard_AircraftCarrier.yaml", "plans/default.yaml")
    # for _ in range(8):
    #     plan2.run()

    # # 8-2B 单点刷
    # plan = NormalFightPlan(timer, "plans/normal_fight/8-2BJ.yaml", "plans/default.yaml")
    # total_time = 0
    # each_time = 10
    # while total_time < 250:
    #     expedition(timer)
    #     print(f"time_passed: {time.time() - start_time}  Finish expedition")
    #     GainBounds(timer)

    #     for _ in range(each_time):
    #         plan.run()
    #     total_time += each_time
    #     print(f"time_passed: {time.time() - start_time}  total_time: {total_time}")

    #     if total_time % 30 == 0:
    #         DestoryShip(timer, reserve=0, amount=0)

    while True:
        # TODO: bug 在前往远征界面之后 远征，会检测不到
        expedition(timer)
        print(f"time_passed: {time.time() - start_time}  Finish expedition")
        GainBounds(timer)

        time.sleep(60 * 5)
