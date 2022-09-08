import copy
from operator import index
import time

import yaml
from api import ClickImage, ImagesExist, UpdateScreen, click, swipe
from constants import *
from game import (ConfirmOperation, DetectShipStatu, GetEnemyCondition,
                  MoveTeam, QuickRepair, UpdateShipPoint, UpdateShipPosition,
                  change_fight_map, goto_game_page, identify_page,
                  process_bad_network, get_exercise_status)
from fight import start_fight
from supports import SymbolImage, Timer
from utils.io import recursive_dict_update
from supports import logit
from .common import FightInfo, FightPlan, DecisionBlock, Ship

"""
常规战决策模块
TODO: 1.资源点 2.依据敌方选择阵型
"""
class ExerciseDecisionBlock(DecisionBlock):

    @logit(level=INFO2)
    def make_decision(self, state, last_state, last_action):
        if state == "rival_info":
            max_times = self.max_refresh_times
            self.formation_chosen = self.formation
            while max_times >= 0:
                GetEnemyCondition(self.timer)
                act = self.check_rules()
                if act == "refresh":
                    if max_times > 0:
                        max_times -= 1
                        click(self.timer, 665, 400, delay=0.75)
                    else:
                        if self.discard:
                            click(self.timer, 878, 136, delay=1)
                            return "discard", "fight continue" 
                        else:
                            break
                elif isinstance(act, int):
                    self.formation_chosen = act
                elif act == None:
                    break
                    
            click(self.timer, 804, 390, delay=0)
            return "fight", "fight continue"
                
        elif state == "fight_prepare_page":
            MoveTeam(self.timer, self.fleet_id)
            print("OK")
            if(start_fight(self.timer) != 'ok'):
                return self.make_decision(state, last_state, last_action)
            return None, "fight continue"
        
        elif state == "spot_enemy_success":
            click(self.timer, 900, 500, delay=0)
            return None, "fight continue"
        
        elif state == "formation":
            click(self.timer, 573, self.formation_chosen * 100 - 20, delay=2)
            return None, "fight continue"
            
        return super().make_decision(state, last_state, last_action)

class NormalExerciseInfo(FightInfo):
    """ 存储战斗中需要用到的所有状态信息 """

    def __init__(self, timer: Timer) -> None:
        super().__init__(timer)
        self.start_page = "exercise_page"
        self.robot = True
        self.successor_states = {
            "exercise_page": ["rival_info"],
            "rival_info":  {
                "fight": ["fight_prepare_page"],
                "discard": ["exercise_page"], 
            },
            "fight_prepare_page": ["spot_enemy_success", "formation", "fight_period"],
            "spot_enemy_success": ["formation"],
            
            "formation": ["fight_period"],
            "fight_period": ["night", "result"],
            "night": {
                "yes": ["night_fight_period"],
                "no": [["result", 5]],
            },
            "night_fight_period": ["result"],
            "result": ["exercise_page"],    # 两页战果
        }

        self.state2image = {
            "exercise_page": [identify_images['exercise_page'], 5],
            "rival_info": [exercise_images["rival_info"], 5],
            "fight_prepare_page": [identify_images["fight_prepare_page"], 5],
            "spot_enemy_success": [FightImage[2], 15],
            "formation": [FightImage[1], 15],
            "fight_period": [SymbolImage[4], 3],
            "night": [FightImage[6], .85, 180],
            "night_fight_period": [SymbolImage[4], 3],
            "result": [FightImage[3], 90],
        }

    def reset(self):
        self.state = "rival_info"  # 初始状态等同于 "rival_info" 选择 'discard'
        self.last_action = 'discard'
        # TODO: 舰船信息，暂时不用
        self.ally_ships = [Ship() for _ in range(6)]  # 我方舰船状态
        self.enemy_ships = [Ship() for _ in range(6)]  # 敌方舰船状态

    def _before_match(self):
        # 点击加速
        if self.state in ["fight_prepare_page"]:
            p = click(self.timer, 380, 520, delay=0, enable_subprocess=True, print=0, no_log=True)

        UpdateScreen(self.timer)

    def _after_match(self):
        if self.state == "result":
            DetectShipStatu(self.timer, 'sumup')
            self.timer.fight_result.detect_result()

    @property
    def node(self):
        return self.timer.ship_point

class NormalExercisePlan(FightPlan):
    """" 常规战斗的决策模块 """

    def __init__(self, timer: Timer, plan_path, default_path):
        super().__init__(timer)
        
        default_args = yaml.load(open(default_path, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
        exercise_defaults, node_defaults = default_args["exercise_defaults"], default_args["node_defaults"]
        # 加载地图计划
        plan_args = yaml.load(open(plan_path, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
        args = recursive_dict_update(exercise_defaults, plan_args, skip=['node_args'])
        self.__dict__.update(args)
        # 加载各节点计划
        self.nodes = {}
        for node_name in self.selected_nodes:
            node_args = copy.deepcopy(node_defaults)
            if node_name in plan_args['node_args']:
                node_args = recursive_dict_update(node_args, plan_args['node_args'][node_name])
            self.nodes[node_name] = ExerciseDecisionBlock(timer, node_args)

        # 构建信息存储结构
        self.Info = NormalExerciseInfo(self.timer)

    @logit(level=INFO2)
    def _enter_fight(self) -> str:
        """
        从任意界面进入战斗.

        :return: 进入战斗状态信息，包括['success', 'dock is full].
        """
        goto_game_page(self.timer, 'exercise_page') 
        self._exercise_times = self.exercise_times
        self.exercise_status = [None, None]
        return "success"

    @logit(level=INFO2)
    def _make_decision(self):

        self.Info.update_state()
        state = self.Info.state
        # 进行MapLevel的决策
        if state == "exercise_page":
            self.exercise_status = get_exercise_status(self.timer, self.exercise_status[1])
            if(self._exercise_times > 0 and any(self.exercise_status[2:])):
                pos = self.exercise_status[2:].index(True)
                self.rival = 'player'
                click(self.timer, 770, (pos + 1) * 110 - 10)
                return 'fight continue'
            elif(self.robot and self.exercise_status[1]):
                swipe(self.timer, 800, 200, 800, 400) #上滑
                click(self.timer, 770, 100)
                self.rival = 'robot'
                self.exercise_status[1] = False
                return "fight continue"

            else:
                return "fight end"

        # 进行通用NodeLevel决策
        action, fight_stage = self.nodes[self.rival].make_decision(state, self.Info.last_state, self.Info.last_action)
        self.Info.last_action = action
        return fight_stage