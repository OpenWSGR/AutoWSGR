
import os

from AutoWSGR.controller.run_timer import Timer
from AutoWSGR.fight.battle import BattlePlan, BattleInfo
from AutoWSGR.fight.common import start_march
from AutoWSGR.constants.image_templates import IMG
from AutoWSGR.constants.settings import S
from AutoWSGR.constants.custom_expections import ImageNotFoundErr
from AutoWSGR.constants.data_roots import MAP_ROOT
from AutoWSGR.game.get_game_info import DetectShipStatu
from AutoWSGR.game.game_operation import QuickRepair, get_ship
from AutoWSGR.utils.io import yaml_to_dict, count
from AutoWSGR.ocr.ship_name import recognize_number, _recognize_ship
from AutoWSGR.port.ship import Fleet, count_ship

import cv2, time
"""决战结构:
上层控制+单点战斗
"""

def is_ship(element):
    return not element in ["长跑训练", "肌肉记忆", "黑科技"]


def get_formation(fleet:Fleet, enemy:list):
    anti_sub = count(['CL', 'DD', 'CVL'], enemy)
    if fleet.exist("U-1206"):
        if(anti_sub <= 1):
            return 4
    else:
        if(anti_sub <= 0):
            return 4
        return 2


class DB():
    def __init__(self, *args, **kwargs):
        self.__dict__.update(kwargs)
    
    def make_decision(self, state):
        rule = self.__dict__
        if(state in rule):
            return rule[state]

        
class Logic():
    """决战逻辑模块,可以自行编写
    """
    def __init__(self):
        self.level1 = ["肥鱼", "U-1206", "狼群47", "射水鱼", "U-96", "U-1405"]
        self.level2 = ["长跑训练", "肌肉记忆"] + self.level1 + ["大青花鱼", "U-81", "黑科技"]
        self.flag_ships = [["U-1405"], ["狼群47", "U-96", "U-1206"]]
    
    def _choose_ship(self, elements:dict, *args, **kwargs):
        lim = 6
        score = kwargs['score']
        if(kwargs['fleet'].count() <= 1):
            choose = self.level1
        elif(kwargs['fleet'].count() < 6):
            choose = [element for element in self.level2 if is_ship(element)]
        else:
            lim = score
            choose = self.level1 + [element for element in self.level2 if not is_ship(element)]
        result = []
        for target in choose:
            if(target in elements.keys()):
                cost, position = elements[target]
                if(score >= cost and cost <= lim):
                    score -= cost
                    result.append(target)
        if(len(result) == 0 and 'must' in kwargs):
            if(kwargs['must']):
                result.append(list(elements.keys())[0])
        return result
    
    def _use_skill(self, *args, **kwargs):
        if(kwargs['node'] == 'A'):
            return 3
        return 0
    
    def need_repair(self, *args, **kwargs):
        ship_status = kwargs['ship_status']
        if(1 in ship_status or 2 in ship_status):
            return True
        return False
    
    def _up_level(self, *args, **kwargs):
        if(kwargs["need"] - kwargs["exp"] <= 5 and kwargs['score'] >= 5):
            return True
        return False
        
    def formation(self, *args, **kwargs):
        pass
    
    def night(self, *args, **kwargs):
        pass
    
    def get_best_fleet(self, ships):
        print("ALL SHIPS:",ships)
        best_ships = [None, ]
        for ship in self.level1:
            if(ship not in ships or len(best_ships) == 7):
                continue
            best_ships.append(ship)
        for ship in self.level2:
            if(ship not in ships or len(best_ships) == 7 or ship in self.level1):
                continue
            best_ships.append(ship)
        for _flag_ships in self.flag_ships:
            ok = False
            for flag_ship in _flag_ships:
                if(flag_ship in best_ships):
                    p = best_ships.index(flag_ship)
                    best_ships[p], best_ships[1] = best_ships[1], best_ships[p]
                    ok = True
                    break
            if(ok):
                break
        for i in range(len(best_ships), 7):
            best_ships.append(None)
        print("BEST FLEET:",best_ships)
        return best_ships
    
    def _retreat(self, fleet:list):
        if(count_ship(fleet) < 2):
            return True
        return False
        
    def _leave(self):
        return False
    

class DecisiveStatu():
    """决战状态模块,暂时不启用
    """
    def __init__(self) -> None:
        pass


class DecisiveBattle():
    """决战控制模块
    """
    def __init__(self, timer:Timer, version=3, *args, **kwargs):
        self.statu = DecisiveStatu()
        self.key_points = [["",]] # [chpater][map] (str)
        self.map_end = ["",] # [chapter] (str)
        self.enemy = [[["", ]]] # [chapter][map][node(str)] (lst["", enemys])
        self.__dict__.update(yaml_to_dict(os.path.join(MAP_ROOT, 'decisive_battle', f"{str(version)}.yaml" )  + {str(version)} + ".yaml"))
        self.timer = timer
        self.fleet = Fleet(self.timer)
        self.ships = set()
        self.CHOOSE_POSITION = [(320 * .75, 251), (490 * .75, 251), (645 * .75, 251), (812 * .75, 251), (956 * .75, 251)] # 选择战备舰队的点击位置
        self.score = 10
        self.exp = 0
        self.chapter = 6 # 大关
        self.map = 1 # 小关
        self.node = 'A'
        self.ship_status = [-1] * 7
        self.timer = timer
        self.logic = Logic()
        self.__dict__.update(kwargs)
    
    def buy_ticket(self, use='steel', times=3):
        self.enter_decisive_battle()
        position = {"oil":184, "ammo":235, "steel":279, "aluminium":321}
        self.timer.Android.click(458 * .75, 665 * .75, delay=1.5)
        self.timer.Android.click(638, position[use], delay=1, times=times)
        self.timer.Android.click(488, 405)
    
    def detect(self, type='enter_map'):
        """检查当前关卡状态
        Args:
            type:
                enter_map: 决战入口检查
                running: 检查地图是否在战斗准备页面
                
        Returns:
            str: ['challenging', 'refreshed', 'refresh']
            str: ['fight_prepare', 'map']
        """
        if(type == 'enter_map'):
            _res = ['challenging', 'refreshed', 'refresh']
            res = self.timer.wait_images(IMG.decisive_battle_image[3:6], after_get_delay=.2)
        if(type == 'running'):
            _res = ['map', 'fight_prepare']
            res = self.timer.wait_images([IMG.decisive_battle_image[1]] + IMG.identify_images['fight_prepare_page'], gap=.03, after_get_delay=.2)
        return _res[res]
    
    def go_map_page(self):
        if(self.detect('running') == 'fight_prepare'):
            self.timer.Android.click(30, 30)
            self.timer.wait_image(IMG.decisive_battle_image[1])
        
    def go_fleet_page(self):
        if(self.detect('running') == 'map'):
            self.timer.Android.click(900 * .75, 667 * .75)
            self.timer.wait_images(IMG.identify_images['fight_prepare_page'], timeout=4)
    
    def repair(self):
        self.go_fleet_page()
        QuickRepair(self.timer, 1)
    
    def next(self):
        if(self.node == self.map_end[self.chapter][self.map]):
            self.timer.ConfirmOperation()
            self.timer.ConfirmOperation()
            get_ship(self.timer, 5)
            self.map += 1
            self.node = 'A'
            return 'next'
        else:
            self.node = chr(ord(self.node) + 1)

    def choose(self, refreshed=False):
        
        # ===================获取备选项信息======================
        DSP = [(250, 390), (410, 550), (570, 710), (730, 870), (890, 1030)] # 扫描战备舰队获取的位置 (1280x720)
        screen = self.timer.get_screen()
        self.score = int(recognize_number(screen[25:55, 1162:1245], min_size=5, text_threshold=.05, low_text=.02)[0][1]) # 应该能保证数字读取成功...
        costs = recognize_number(screen[550:585, 245:1031], 'x')
        _costs, ships, real_position  = [], [], []
        for i, cost in enumerate(costs):
            try:
                if(int(cost[1][1:]) > self.score):
                    continue
                ships.append(_recognize_ship(screen[488:515,DSP[i][0]:DSP[i][1]], self.timer.ship_names)[0][0])
                _costs.append(int(cost[1][1:]))
                real_position.append(i)
            except:
                pass
        # print("Scan result:", costs)
        costs = _costs
        elements = {}  
        for i in range(len(costs)):
            elements[ships[i]] = (costs[i], self.CHOOSE_POSITION[real_position[i]]) 
            # elements[舰船名] = (费用, 点击位置)
            
        # ==================做出决策===================    
        choose = self.logic._choose_ship(elements, score=self.score, fleet=self.fleet, must=(self.map == 1 and self.node == 'A' and refreshed == True))
        if(len(choose) == 0 and refreshed == False):
            self.timer.Android.click(380, 500) # 刷新备选舰船
            return self.choose(True)
        
        for target in choose:
            cost, p = elements[target]
            self.score -= cost
            self.timer.Android.click(*p)
            if(is_ship(target)):
                self.ships.add(target)
        self.timer.Android.click(580, 500) # 关闭/确定
        
    def up_level_assistant(self):
        self.timer.Android.click(75, 667 * .75)
        self.score -= 5
    
    def use_skill(self, type=3):
        self.timer.Android.click(275 * .75, 644 * .75)
        if(type == 3):
            ships = _recognize_ship(self.timer.get_screen()[488:515], self.timer.ship_names)
            for ship in ships:
                self.ships.add(ship[0])
        self.timer.Android.click(275 * .75, 644 * .75)
        
    def leave(self):
        self.timer.Android.click(36, 33)
        self.timer.Android.click(360, 300)
    
    def get_chapter(self):
        return int(recognize_number(self.timer.get_screen()[588:618, 1046:1110], "Ex-X")[0][1][-1])
        
    def move_chapter(self):
        if(self.get_chapter() < self.chapter):
            self.timer.Android.click(900, 507)
        elif(self.get_chapter() > self.chapter):
            self.timer.Android.click(788, 507)
        else:
            return 
        self.move_chapter()
            
    
    def enter_decisive_battle(self):
        self.timer.goto_game_page("decisive_battle_entrance")
        self.timer.Android.click(115, 113)
        self.detect()    
    
    def enter_map(self, check_map=True):
        if(check_map):
            self.enter_decisive_battle()
            statu = self.detect()
            self.move_chapter()
            if(statu == 'refresh'):
                self.reset_chapter()
                statu = 'refreshed'
            if(statu == 'refreshed'):
                # 选用上一次的舰船并进入
                self.timer.Android.click(500, 500, delay=0)
                self.timer.click_image(IMG.decisive_battle_image[7], timeout=3)
                self.timer.Android.click(873, 500) 
            else:
                self.timer.Android.click(500, 500, delay=0)
        else:
            self.detect()
            self.timer.Android.click(500, 500, delay=0)
        res = self.timer.wait_images([IMG.decisive_battle_image[1], IMG.decisive_battle_image[6]], timeout=5, gap=.03)
        if(res == None):
            raise ImageNotFoundErr("Can't Identify on enter_map")
        if(res == 1):
            return "other chapter is running"
        return "ok"
        
    def retreat(self):
        self.go_map_page()
        self.timer.Android.click(36, 33)
        self.timer.Android.click(600, 300)
    
    def get_exp(self):
        src = recognize_number(self.timer.get_screen()[592:615,48:118], "(/)")[0][1]
        self.exp = 0
        self.need = 20
        try:
            i1 = src.index('(')
            i2 = src.index('/')
            self.exp = int(src[i1 + 1:i2])
            self.need = int(src[i2 + 1:-1])
        except:
            pass
        
    def before_fight(self):
        if(self.timer.wait_image(IMG.confirm_image[1:], timeout=1) != False):
            self.timer.Android.click(300, 225) # 选上中下路
            self.timer.ConfirmOperation(must_confirm=1)
        if(self.timer.wait_image(IMG.decisive_battle_image[2], timeout=5)):
            self.choose() # 获取战备舰队
        self.get_exp()
        while(self.logic._up_level(need=self.need, exp=self.exp, score=self.score)):
            self.up_level_assistant()
            self.get_exp()
        if(self.logic._use_skill(node=self.node)):
            self.use_skill(self.logic._use_skill(node=self.node)) 
        if(self.fleet.empty()):
            self.check_fleet()
        _fleet = self.logic.get_best_fleet(self.ships)
        if(self.logic._retreat(_fleet)):
            self.retreat()
            return 'retreat'
        if(self.logic._leave()):
            self.leave()
            return 'leave'
        if(self.fleet != _fleet):
            self.change_fleet(_fleet)
            self.ship_status = DetectShipStatu(self.timer)
        if(self.logic.need_repair(ship_status = self.ship_status)):
            self.repair()
        
    def after_fight(self):
        self.ship_status = self.timer.ship_status
        print(self.ship_status)
        
    def check_fleet(self):
        self.go_fleet_page()
        self.fleet.detect()
        for ship in self.fleet.ships:
            self.ships.add(ship)
        self.ship_status = DetectShipStatu(self.timer)
            
    def during_fight(self):
        formation = get_formation(self.fleet, self.enemy[self.chapter][self.map][self.node])
        night = self.node in self.key_points[self.chapter][self.map]
        DecisiveBattlePlan(self.timer, decision_block=DB(formation=formation, night=night)).run()
    
    def change_fleet(self, fleet):
        self.go_fleet_page()
        self.fleet.set_ship(fleet, order=True, search_method=None)
        
    def fight(self):
        res = self.before_fight()
        if(res == 'retreat'):
            self.enter_map(check_map=False)
            self.reset()
            return self.fight()
        self.during_fight()
        self.after_fight()
        res = self.next()
        if(self.map == 4):
            return 'quit'
        if(res == 'next'):
            return 'next'
        
    
    def start_fight(self):
        self.enter_map()
        while(True):
            res = self.fight()
            if(res == 'quit'):
                return 
            elif(res == 'next'):
                self.enter_map(False)
    
    def reset_chapter(self):
        # Todo: 缺少磁盘报错
        self.move_chapter()
        self.timer.Android.click(500, 500)
        self.timer.ConfirmOperation()
    
    def reset(self):
        self.__init__(self.timer, chapter=self.chapter)


class DecisiveBattlePlan(BattlePlan):
    
    def __init__(self, timer:Timer, default_path="plans/default.yaml", decision_block=None):
        super().__init__(timer, None, default_path, decision_block=decision_block)
        self.Info = DecisiveBattleInfo(timer)

    def _enter_fight(self, *args, **kwargs):
        return start_march(self.timer)
    
    
class DecisiveBattleInfo(BattleInfo):
    
    def __init__(self, timer:Timer):
        super().__init__(timer)
        self.end_page = 'unknown_page'
        self.state2image["battle_page"] = [IMG.decisive_battle_image[1], 5]