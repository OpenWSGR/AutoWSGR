from asyncio.proactor_events import _ProactorBaseWritePipeTransport
from fight.apis import *
from fight.data_structures import *
from game import *
from supports import *
from api import *

__all__ = ['init_decisive', 'tmp_fight', 'decisive_fight']
decisive_objects = set()

class DecisiveObject():
    def __init__(self, name):
        self.image = None
        self.type = None
    def identify(self, timer):
        pass

class DecisiveBuff():
    def __init__(self):
        pass

class DecisiveShip():
    def __init__(self):
        self.cost=0
        self.level=0
        self.name=""

class DecisiveBattleData():
    def __init__(self):
        self.ships = set()
        
def init_decisive():
    for object in decisive_objects_images:
        if("buff" in object):
            pass

def get_choices(timer:Timer): 
    pass

def skill(timer):
    pass
def quit(timer:Timer, type=0):
    """从决战地图退出

    Args:
        timer (Timer): _description_
        type (int): 暂离还是撤退,0 暂离， 1 撤退
    """
    

def tmp_fight(timer: Timer, formation=2, night=0, join_fun=None, wait_timeout=10):
    """决战单点战斗

    Args:
        timer (Timer): _description_
        formation (int, optional): _description_. Defaults to 2.
        night (int, optional): _description_. Defaults to 1.
        join_fun (_type_, optional): _description_. Defaults to None.
    """
    timer.ammo = timer.oil = 10
    WaitImage(timer, GameUI[17], timeout=wait_timeout)
    click(timer, 613, 494, delay=1)
    if(1 in timer.ship_status or 2 in timer.ship_status):
        click(timer, 714, 500, delay=0)
        wait_pages(timer, 'fight_prepare_page')
        QuickRepair(timer)
    click(timer, 900, 500)
    fight(timer, 'fight', DecisionBlock(formation=formation, night=night, ))
    WaitImage(timer, GameUI[16])

def choose_path(timer:Timer, count=3):
    if(count == 2):
        click(timer, 230, 270)  #
    if(count == 3):
        click(timer, 300, 250)  #
    
    click(timer, 450, 450)  #

def decisive_fight(timer:Timer, start="2A"):
    
    """E6 决战,自动 2,3 图

    Args:
        timer (Timer): _description_
    """
    if(start<="2J"):
        click(timer, 500, 500)  #进入第二张图
        if(start <= "2A"):
            choose_path(timer)
            tmp_fight(timer, 2)  #2-A
        if(start <= "2B"):    
            tmp_fight(timer, 4)  #2-B
            choose_path(timer, 2)
        if(start <= "2C"):
            tmp_fight(timer, 4, 1)  # 2-C1
        if(start <= "2D"):
            tmp_fight(timer, 4, 0)  # 2-D
        if(start <= "2E"):
            tmp_fight(timer, 2, 0)  # 2-E
        if(start <= "2F"):
            tmp_fight(timer, 4, 0)  # 2-F
            choose_path(timer, 2)
        if(start <= "2G"):
            tmp_fight(timer, 4, 0)  # 2-G
        if(start <= "2H"):
            choose_path(timer, 2)
            tmp_fight(timer, 4, 1)  # 2-H1
        if(start <= "2I"):
            tmp_fight(timer, 4, 0)  # 2-I
        if(start <= "2J"):
            choose_path(timer)
            tmp_fight(timer, 4, 1)  # 2-J1 
        
        time.sleep(2)
        click(timer, 500, 450, delay=.5)
        click(timer, 500, 300, delay=.5)
        fight_end(timer, end_page="decisive_map_entrance", begin=0)  #结算并领取舰船
    
    if(start<="3J"):
        click(timer, 500, 500)  #进入第三张图
        if(start<="3A"):
            choose_path(timer)
            tmp_fight(timer, 4)  #3-A
        if(start<="3B"):
            tmp_fight(timer, 4)  #3-B
        if(start<="3C"):
            choose_path(timer, 2)  
            tmp_fight(timer, 4, 0)  # 3-C
        if(start<="3D"):
            choose_path(timer, 2)
            tmp_fight(timer, 4, 1)  # 3-D1
        if(start<="3E"):
            tmp_fight(timer, 2, 0)  # 3-E
        if(start<="3F"):
            tmp_fight(timer, 4, 0)  # 3-F
        if(start<="3G"):
            choose_path(timer, 2)
            tmp_fight(timer, 4, 1)  # 3-G
        if(start<="3H"):
            tmp_fight(timer, 4, 0)  # 3-H
        if(start<="3I"):
            tmp_fight(timer, 4, 0)  # 3-I
        if(start<="3J"):
            choose_path(timer, 2)
            tmp_fight(timer, 4, 1)  # 3-J1 
        
        # 结算并领取舰船
        time.sleep(2)
        click(timer, 500, 450, delay=.5)
        click(timer, 500, 300, delay=.5)
        fight_end(timer, end_page="decisive_map_entrance", begin=0)
    
    