
from digit_recognition import *
from save_load import *
from pre_set import *

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

def start_script(device_name="emulator-5554", account=None, password=None):
    """启动脚本,返回一个 Timer 记录器

    Returns:
        Timer: 该模拟器的记录器
    """
    timer = Timer()
    timer.device_name = device_name
    load_all_data(timer)
    load_game_ui(timer)
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
    GoMainPage(timer)
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

def listener(event:kd.KeyboardEvent):
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
        
        GoMainPage

def main_function():

    timer = start_script(account=None, password=None)
    
    #  work(timer, lambda:normal_fight(4, 1, 1))
    #  print("Script Finished")
    #  quit()
    #  DetectShipStatu(timer)
    #  ChangeShip
    #  work(timer, lambda:normal_fight(timer, 1, 5, 4), 3)
    #  weekliy(timer, 4)
    
    week4(timer, change=0)
    week6(timer, change=0)
    week7(timer, change=0)
    week8(timer, change=0)
    #  normal_exercise(timer, 1)
    #  friend_exercise(timer, 1)
    
    #  print(timer.fight_result.detect_result())
    #  print(timer.resources.ask_resources(name='oil', detect=True))
    
    #  restart(timer)
    #  friend_exercise(timer, 1)
    #  print(timer.fight_result.detect_result())
    #  normal_exercise(timer, 1)    
    #friend_exercise(timer, 1)
    
    #  print(ImagesExist(timer, ConfirmImage[1:]))
    """ret = get_resources(timer)
    print(ret)
    ret = get_loot_and_ship(timer)
    print(ret)"""

if __name__=="__main__":
   
    
    #  print(str(os.po("adb devices -l")).split('\n'))
    kd.hook(listener)
    main_function()
    
