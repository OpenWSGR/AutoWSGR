
from game import *
from supports import *
from fight.apis import *
from fight.data_structures import *
from api import *

__all__ = ['battle']

@logit(level=INFO3)
def battle(timer:Timer, node, times, decision_maker:DecisionBlock=None, repair_logic:RepairBlock=None, team=None, try_times=0, *args, **kwargs):
    """进行战役

    Args:
        timer (Timer): _description_
        node (int): 战役的节点,从简单(1~5)到困难(6~10),内部顺序为 驱逐,巡洋,战列...
        times (int): 次数
        decision_maker (DecisionBlock, optional): _description_. Defaults to None.
        team (_type_, optional): _description_. Defaults to None.
    
    """
    if(times == 0):
        return 'finsihed'
    if(try_times > 3):
        raise TimeoutError("can't battle normally")
    
    try:
        if(repair_logic == None):
            repair_logic = timer.defaul_repair_logic
        if(decision_maker == None):
            decision_maker = timer.defaul_decision_maker
        if(times == 0):
            return 
        
        goto_game_page(timer, "battle_page")
        now_type = WaitImages(timer, [FightImage[9], FightImage[15]])
        hard = node > 5
        
        if(now_type != hard):
            click(timer, 800, 80, delay=3)
            now_type = WaitImages(timer, [FightImage[9], FightImage[15]])
        
        timer.chapter = 'battle'
        timer.node = node
        
        click(timer, 180 * (node - hard * 5), 200)
        start_time = time.time()
        while not identify_page(timer, 'fight_prepare_page'):
            time.sleep(.15)
            if(time.time() - start_time > 15):
                raise BaseException()
            
        QuickRepair(timer)   
        click(timer, 900, 500, delay=0)    
        while(identify_page(timer, 'fight_prepare_page')):
            time.sleep(.15)
            if(ImagesExist(timer, SymbolImage[9], need_screen_shot=0)):
                return 'run out of battle times'
            if(time.time() - start_time > 15):
                raise BaseException()
            
        if(team is not None):
            ChangeShips(timer, team, team)
        
        fight(timer, 'battle', decision_maker)
        timer.set_page("battle_page")
        battle(timer, node, times - 1, decision_maker, repair_logic, team, 0 + 1)
    except Exception as exception:
        print("exception:", exception)
        return battle(timer, node, times, decision_maker, repair_logic, team, try_times + 1)
        
    
    