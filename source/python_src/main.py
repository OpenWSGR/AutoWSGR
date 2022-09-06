import datetime
import time

import keyboard as kd

import constants.global_attributes as Globals
import constants.settings as S
from api.api_android import UpdateScreen, is_game_running
from api.api_windows import ConnectAndroid
from fight.data_structures import DecisionBlock, RepairBlock
from fight.decisive_battle import init_decisive
from fight_dh.battle import BattlePlan
from fight_dh.normal_fight import NormalFightPlan
from game.game_operation import (GainBounds, RepairByBath, expedition, restart,
                                 start_game)
from game.get_game_info import ExpeditionStatus, FightResult, Resources
from game.identify_pages import get_now_page
from game.switch_page import load_game_ui
from ocr_dh.ship_name import recognize_ship
from save_load.load_data import load_all_data
from supports.run_timer import Timer


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
    if account != None and password != None:
        restart(timer, account=account, password=password)
    if is_game_running(timer) == False:
        start_game(timer)
    print("resolution:", timer.resolution)
    timer.ammo = 10
    timer.defaul_repair_logic = RepairBlock()
    timer.defaul_decision_maker = DecisionBlock()
    timer.expedition_status = ExpeditionStatus(timer)
    timer.fight_result = FightResult(timer)
    timer.resources = Resources(timer)
    # GetEnemyCondition(timer)
    # DetectShipStatu(timer)
    try:
        timer.set_page(page_name=get_now_page(timer))
    except Exception:
        if S.DEBUG:
            timer.set_page('main_page')
        else:
            restart(timer)
            timer.set_page(page_name=get_now_page(timer))
    print(timer.now_page.name)
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


def default_strategy():
    timer = start_script()

    plan2 = BattlePlan(timer, "plans/battle/hard_Cruiser.yaml",  "plans/default.yaml")
    ret = "success"
    while ret == "success":
        ret = plan2.run()

    # # 刷图练级
    # plan = NormalFightPlan(timer, "plans/normal_fight/8-5AI.yaml", "plans/default.yaml")
    # total_time = 0
    # each_time = 10
    # ret = "success"
    # while ret == "success":
    #     goto_game_page(timer, "main_page")
    #     expedition(timer, force=True)
    #     print(f"time_passed: {time.time() - start_time}  Finish expedition")
    #     GainBounds(timer)

    #     for _ in range(each_time):
    #         ret = plan.run()
    #     total_time += each_time
    #     print(f"time_passed: {time.time() - start_time}  total_time: {total_time}")

    #     # if total_time % 30 == 0:
    #     #     DestoryShip(timer, reserve=0, amount=0)
    #     #     DestoryShip(timer, reserve=0, amount=0)

    # 自动远征
    while True:
        RepairByBath(timer)
        expedition(timer, force=True)
        GainBounds(timer)
        print(f"{datetime.datetime.now()} Complete a maintenance ")
        time.sleep(60 * 5)


if __name__ == "__main__":
    default_strategy()

    # timer = start_script()
    # recognize_ship(timer)

    # while True:
    #     time.sleep(10)
