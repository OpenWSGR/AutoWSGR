
from supports import *

__all__ = ["DecisionBlock", "RepairBlock", "DecisionBlock1", "DecisionBlock2"]
    
class DecisionBlock():
    def __init__(self, *args, **kwargs):
        self.dict=kwargs
        
    def old_version(self, timer:Timer, type, c, n, mod, statu, e):
        allSS  = 0 
        if(c == 'exercise'):
            print(c, mod)
            if(mod == 1):
                return 1
        """老版本的决策方案

        Args:
            timer (Timer): _description_
            type (_type_): _description_
            c (_type_): _description_
            n (_type_): _description_
            mod (_type_): _description_
            statu (_type_): _description_
            e (_type_): _description_

        Returns:
            _type_: _description_
        """
        
        if(type == 'formation'):
            if(c == 2 and n == 1):
                if(mod == 2):
                    #2-1 4DD周常
                    if(timer.ship_point != 'F'):
                        return False
            if(c == 3 and n == 1):
                # 3-2 6DD 周常
                if(mod == 1):
                    if((10 - timer.ammo) / 2 == 1):
                        return 2
                    else:
                        return 0
            if(c == 4 and n == 1):
                
                if(mod == 1):
                    #4-1 DD周常
                    if(timer.ship_point != 'A' and (10 - timer.ammo) / 2 == 1):
                        return False
            if(c == 4 and n == 2):
                if(mod == 1):
                    #2022.5.20手电筒战利品测试
                    if(e[SAP] != 0 or (10 - timer.ammo) / 2 == 3):
                        return 0
            if(c == 4 and n == 4):
                if(mod == 1):
                    #4-4SS周常
                    if((10 - timer.ammo) / 2 == 0 and timer.ship_point != 'A'):
                        return False                   
            if(c == 5  and n == 5):
                if(mod == 1):
                    #5-5SS周常
                    if(timer.ship_point != 'C' and (10 - timer.ammo) / 2 == 0):
                        return False
            if(c == 7 and n == 4):
                if(mod and mod <= 3):
                    #6SS或5SS+1DD
                    allSS = 1
                if(mod == 3 and (timer.ship_point == 'M' or timer.ship_point == 'I')):
                    #无限制战利品打捞
                    try:
                        if(e[SAP] == 0):
                            return 0
                    except:
                        pass
                if(mod == 1 or mod == 2):
                    #mod=1:大冒险
                    #mod=2:后备弹6SS
                    if((10 - timer.ammo) / 2 == 0):
                        if(timer.ship_point == 'A'):
                            return 0
                        if(e[DD] + e[CL] >= 4):
                            return 0

                    if((10 - timer.ammo) / 2 == 4):
                        return 4
            if(c == 7 and n == 5):
                if(mod == 1):
                    #7-5练级
                    if(e["SS"] != 0):
                        return 5
                    else:
                        return 1
                if(mod == 2):
                    if(e["SS"] == 0):
                        return 1
                    else:
                        return 0
                if(mod == 3):
                    if(e["SS"] == 3):
                        return 5
                    else:
                        return 0
            if(c == 6 and n == 1):
                if(mod == 1):#5SS
                    if(e["SS"] == 5):
                        return 5
                    else:
                        return 0
                if(mod == 2):#2CLV
                    if(e["CLV"] == 2):
                        return 5
                    else:
                        return 0
                if(mod == 3):#2CLT
                    if(e["CLT" == 2]):
                        return 5
                    else:
                        return 0
            if(c == 6 and n == 3):
                if(mod == 1):
                    #6SS周常
                    if(e[CA] != 2 and timer.ship_point == 'B'):
                        return 0
            if(c == 8 and n == 1):
                if(mod == 1):
                    #8-1炸鱼
                    if(e["SS"] == 5):
                        return 5
                    else:
                        return 0
                if(mod == 2):
                    #8-1炸鱼带大船控MVP
                    if(timer.ship_point == 'A' and e["CL"] == 2):
                        return 5
                    else:
                        return 0
            if(c == 8 and n == 5):
                if(mod == 1):
                    #6SS 8-5 回血和战利品
                    if(e["CL"] == 0):
                        return 4
                    else :
                        return 0
            if(c == 8 and n == 4):
                if(mod == 1):
                    allSS = 1
            if(c == 'exercise' and n == 1):
                if(e[SS] > 0):
                    return 0
                else:
                    return 1
            if(c == 'exercise' and n != 1):
                try:
                    if(e[SS] > 0 or e[BB] + e[BC] > 2 or e[ASDG] + e[BG] > 1):
                        return 0
                except:
                    return 1
                else:
                    return 1
            if(c == 'battle' and n == 6):
                return 1
            if(c == 'battle' and n == 7):
                return 1
            if(c == 'battle' and n == 8):
                return 5
            if(c == 'battle' and n == 9):
                return 2
            if(c == 2 and n == 1):
                if(mod == 1):
                    if(e["SAP"] == 1):
                        return 2
                    else:
                        return 0
            
            if(allSS):
                try:
                    if(e[CL] + e[DD] <= 1):
                        return 4
                except:
                    pass
                return 2
            if((10 - timer.ammo) / 2 >= 3):
                return 4
            return 2
        
        if(type == 'night'):
            if(c == 1 and n == 1):
                return True
            if(c == 1 and n == 5):
                return True
            if(c == 2 and n == 1):
                if(mod == 2):
                    return True
            if(c == 3 and n == 2):
                if((10 - timer.ammo) / 2 == 3):
                    return True
            if(c == 5 and n == 5):
                if(mod == 1 and (10 - timer.ammo) / 2 == 3):
                    return True
            if(c == 3 and n == 2):
                if(mod == 1):
                    if((10 - timer.ammo) / 2 == 3):
                        return True
            if(c == 7 and n == 4):
                if(mod == 1 or mod == 2 or mod == 3):
                    if((10 - timer.ammo) / 2 == 4):
                        return 0
                    if(timer.ship_point == 'M'):
                        return True
            if(c == 7 and n == 5):
                if(mod == 1):
                    return True
            if(c == 8 and n == 5):
                if(mod == 1):
                    return False
            if(c == 'battle'):
                return 1
            if(c == 'exercise'):
                return 1
            if((10 - timer.ammo) / 2 == 4):
                return True
            return False
        
        if(type == 'proceed'):
            if(2 in statu):
                print("存在大破，停止战斗")
                return False
            if(c == 6 and n == 1):
                if(mod == 1 or mod == 2 or mod == 3):
                    return False
            if(c == 8 and n == 1):
                if(mod == 1 or mod == 2):
                    return False
            if(c == 7 and n == 4):
                if(mod == 2 or mod == 3):
                    return True
            if(c == 7 and n == 5):
                if(mod == 1 and (10 - timer.ammo) / 2 == 3):
                    return False
                if(mod == 2 or mod == 3):
                    return False
            if(c == 8 and n == 2):
                if(mod == 1 or mod == 2):
                    return False
            if((10 - timer.ammo) / 2 == 4):
                print("四战，退出")
                return False
            return True
        
        if(type == 'fight_condition'):
            if(c == 8 and n == 2):
                if(mod == 1):
                    return 4
            return 4

    def make_decision(self, timer:Timer, type, *args, **kwargs):
        
        """进行决策

        Args:
            type (str): 决策类型
                values:
                    'formation': 阵型返回 0~6 的整数,0 为撤退, 6 为迂回, 其它依次为单纵,复纵...
                    'night': 是否进行夜战返回 0/1
                    'fight_condition': 选择战况,返回 1~5, 左上为 1, 中间为 2, 右上为 3, 左下为 4
                    'proceed:' 回港或继续, 回港为 0, 继续为 1
                    'SL': 进入战斗后是否 SL
        Returns:
            int: 描述决策
        """
        print("decision info:\ntype:", type, "point:", timer.chapter , "-" , timer.node , timer.ship_point)
        print("ammo:", timer.ammo, "ship_status:", timer.ship_status)
        mod = 0
        if(type in self.dict):
            return self.dict.get(type)
        if('mod' in kwargs.keys()):
            mod = kwargs.get('mod')

        if(type == 'formation'):
            pass
        
        if(type == 'night'):
            pass
        
        if(type == 'fight_condition'):
            pass
        
        if(type == 'proceed'):
            pass
        if(type == 'SL'):
            return False
            
        return self.old_version(timer, type, timer.chapter, timer.node, mod, timer.ship_status , timer.enemy_type_count)
        
class RepairBlock():
    def __init__(self):
        pass
    
    def need_repair(self, timer:Timer, *args, **kwargs):
        return True

class DecisionBlock1(DecisionBlock):
    def make_decision(self, timer:Timer, type):
        return super().make_decision(timer, type)

class DecisionBlock2(DecisionBlock):
    def make_decision(self, timer: Timer, type):
        return super().make_decision(timer, type)

class FightType():
    def __init__(self):
        pass

class SingleFight(FightType):
    def __init__(self):
        super().__init__()

class MapFight(FightType):
    def __init__(self):
        super().__init__()
        
class ExerciseFight(SingleFight):
    def __init__(self):
        super().__init__()
        
class BattleFight(SingleFight):
    def __init__(self):
        super().__init__()

class DecisiveFight(SingleFight):
    def __init__(self):
        super().__init__()

class FightArgs():
    def __init__(self, type:FightType, chapter, node, team, supply, repair, decision, support, *args, **kwargs):
        self.type = type
        self.chapter = chapter
        self.node = node
        self.team = team
        self.supply = supply
        self.repair = repair
        self.decision = self.decision
        self.support = support
        