
from functools import partial
from save_load import *
from supports import *
from fight import *
from game import *
from digit_recognition.digit_ocr import *

import keyboard as kd

finished = 1


def tmp_fight(timer: Timer, formation=2, night=1, join_fun=None):
    if(join_fun is not None):
        join_fun()
    fight(timer, 'fight', DecisionBlock(formation=formation, night=night, ))


def keyborad_input(event: kd.KeyboardEvent):
    global timer, finished
    if(finished == 0):
        return
    finished = 0
    if(event.name == 'C' and event.event_type == 'down'):
        ConfirmOperation(timer, must_confirm=1, delay=.5)
    if(event.name == 'S' and event.event_type == 'down'):
        tmp_fight(timer, join_fun=lambda: click(timer, 852, 484), formation=2, night=1)
    if(event.name == 's' and event.event_type == 'down'):
        tmp_fight(timer, join_fun=lambda: click(timer, 852, 484), formation=2, night=0)
    if(event.name == 'T' and event.event_type == 'down'):
        tmp_fight(timer, join_fun=lambda: click(timer, 852, 484), formation=4, night=1)
    if(event.name == 't' and event.event_type == 'down'):
        tmp_fight(timer, join_fun=lambda: click(timer, 852, 484), formation=4, night=0)
    finished = 1


def start_script():
    """启动脚本,返回一个 Timer 记录器

    Returns:
        Timer: 该模拟器的记录器
    """
    timer = Timer()
    load_all_data(timer)
    load_game_ui(timer)
    ConnectAndroid(timer)
    UpdateScreen(timer)
    timer.resolution = timer.screen.shape[:2]
    print("resolution:", timer.resolution)
    timer.ammo = 10
    timer.defaul_repair_logic = RepairBlock()
    timer.defaul_decision_maker = DecisionBlock()
    timer.expedition_status = ExpeditionStatus(timer)
    timer.fight_result = FightResult(timer)
    GetEnemyCondition(timer)
    try:
        timer.set_page(page_name=get_now_page(timer))
    except:
        timer.set_page('main_page')
    print(timer.now_page.name)
    return timer


if __name__=="__main__":
    # timer = start_script()
    # kd.hook(keyborad_input)
    # time.sleep(10000)
    #ChangeShips(timer, 4, [None, "萤火虫", "伏尔塔", "吹雪", "明斯克", "基辅", "黑潮"])
    #work(lambda:normal_fight(timer, 3, 2, 4, mod=1), times=3)
    # GainBounds(timer)
    #ChangeShips(timer, 4, [None, "U-96", "鲃鱼", "大青花鱼", "U-47", "U-1206", "射水鱼"])
    # work(lambda: normal_fight(timer, 1, 1, 1, mod=1), times=15)
    # GainBounds(timer)
    #battle(timer, 10, 1)
    #battle(timer, 8, 2)
    #battle(timer, 9, 2)
    #work(lambda:normal_fight(timer, 8, 1, 3, mod=1), times=100)
    # GetEnemyCondition(timer)
    #normal_exercise(timer, 1)

    # DH add tests here
    timer = start_script()
    ret = get_resources(timer)
    print(ret)
    ret = get_loot_and_ship(timer)
    print(ret)
