from supports import *
from game import *
from api import *


from fight.data_structures import *
from fight.apis import *

__all__ = ['normal_exercise', 'friend_exercise']

@logit(level=INFO3)
def normal_exercise(timer:Timer, team, decision_maker:DecisionBlock=None, refresh_times=0, *args, **kwargs):
    """常规演习:挑战所有可以挑战的

    Args:
        timer (Timer): _description_
        team (int): 用哪个队伍打
        
    """
    if(refresh_times == 0):
        """还没有点挑战
        """
        if(decision_maker == None):
            decision_maker = timer.defaul_decision_maker
        goto_game_page(timer, 'exercise_page')
        
        if('challenge_status' in kwargs):
            status = kwargs.get('challenge_status')
            kwargs.pop('challenge_status')
        else:
            status = get_exercise_status(timer)
        if not True in status:
            return 
        
        target = status.index(True)
        status[target] = False
        if(target == 5):
            target = 4
            swipe(timer, 800, 400, 800, 200)
            
        click(timer, 770, target * 110 - 10)
        
    GetEnemyCondition(timer)
    timer.chapter, timer.node = 'exercise', target
    formation = decision_maker.make_decision(timer, 'formation')
    if(formation == 0 and refresh_times <= 3):
        click(timer, 665, 400, delay=0.75)
        normal_exercise(timer, team, decision_maker, refresh_times + 1, challenge_status=status *args, **kwargs)
    else:
        click(timer, 804, 390, delay=0)
        exercise_fight(timer, team, decision_maker, *args, **kwargs)
        normal_exercise(timer, team, decision_maker, 0, challenge_status=status, *args, **kwargs)      

@logit(level=INFO3)    
def exercise_fight(timer:Timer, team, decision_maker:DecisionBlock=None, *args, **kwargs):
    print("演习中:队伍:", timer.team, "敌方:", timer.node)
    wait_pages(timer, names='fight_prepare_page')
    MoveTeam(timer, team)
    click(timer, 900, 500, delay=0)
    fight(timer, 'fight', decision_maker, mod=1, *args, **kwargs)

@logit(level=INFO3)    
def friend_exercise(timer:Timer, team, decision_maker:DecisionBlock=None, targets=[1, 2, 3], uids=None, *args, **kwargs):
    """好友演习
    目前只支持选前四个演习
    Todo:
        自动获取并识别好友,uid 识别
    Args:
        timer (Timer): _description_
        team (_type_): _description_
        times (_type_): 每一个好友打几次
        targets (_type_): 打哪些好友,如果缺省. Defaults to [1,2,3]
        ships (_type_, optional): _description_. Defaults to None.
    """
    if(len(targets) == 0):
        return 
    if(decision_maker == None):
        decision_maker = timer.defaul_decision_maker
        
    goto_game_page(timer, 'friend_page')
    target = targets[0]
    timer.chapter, timer.node = 'exercise', target
    
    click(timer, 600, (60 + target * 140) * .75, delay=.75)
    click(timer, 938 * .75, 434 * .75, delay=.74)
    click(timer, 1145 * .75, 546 * .75, delay=.75)
    click(timer, 1148 * .75, 386 * .75, delay=.75)
    click(timer, 1107 * .75, 538 * .75, delay=.75)
    
    exercise_fight(timer, team, decision_maker)
    click(timer, 50, 30, delay=.5)
    friend_exercise(timer, team, decision_maker, targets[1:])
    
    
    
    
    
