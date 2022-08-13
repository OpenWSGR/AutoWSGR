import time

import yaml
from api import ImagesExist, UpdateScreen, WaitImages, click
from constants import FightImage, SymbolImage, identify_images
from game import QuickRepair, goto_game_page, identify_page
from supports import Timer
from utils.io import recursive_dict_update

from fight_dh import FightInfo, FightPlan, NodeLevelDecisionBlock

"""
战役模块
TODO: 1.区分战役次数耗尽与船坞已满导致不能进入
"""


class BattleInfo(FightInfo):
    def __init__(self, timer: Timer) -> None:
        super().__init__(timer)

        self.successor_states = {
            "proceed": ["spot_enemy_success", "formation"],
            "spot_enemy_success": {
                "retreat": ["battle_page"],
                "fight": ["formation", "fight_period"],
            },
            "formation": ["fight_period"],
            "fight_period": ["night", "result"],
            "night": {
                "yes": ["night_fight_period"],
                "no": [["result", 5]],
            },
            "night_fight_period": ["result"],
            "result": ["battle_page"],    # 两页战果
        }

        self.state2image = {
            "proceed": [FightImage[5], 5],
            "spot_enemy_success": [FightImage[2], 15],
            "formation": [FightImage[1], 15],
            "fight_period": [SymbolImage[4], 3],
            "night": [FightImage[6], .85, 120],
            "night_fight_period": [SymbolImage[4], 3],
            "result": [FightImage[3], 60], "battle_page": [identify_images["battle_page"][0], 5]
        }

    def reset(self):
        self.last_state = ""
        self.last_action = ""
        self.state = "proceed"

    def _before_match(self):
        # 点击加速
        if self.state in ["proceed", "fight_condition"]:
            p = click(self.timer, 380, 520, delay=0, enable_subprocess=True, print=0, no_log=True)
        UpdateScreen(self.timer)

    def _after_match(self):
        pass  # 战役的敌方信息固定，不用获取


class BattlePlan(FightPlan):
    def __init__(self, timer, plan_path, default_path) -> None:
        super().__init__(timer)

        default_args = yaml.load(open(default_path, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
        plan_defaults, node_defaults = default_args["battle_defaults"], default_args["node_defaults"]
        # 加载战役计划
        plan_args = yaml.load(open(plan_path, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
        args = recursive_dict_update(plan_defaults, plan_args, skip=['node_args'])
        self.__dict__.update(args)
        # 加载战役节点计划
        default_args = default_args["node_defaults"]
        node_args = recursive_dict_update(node_defaults, plan_args["node_args"])
        self.node = NodeLevelDecisionBlock(timer, node_args)

        self.Info = BattleInfo(timer)

    def _enter_fight(self) -> str:
        goto_game_page(self.timer, "battle_page")
        now_hard = WaitImages(self.timer, [FightImage[9], FightImage[15]])
        hard = self.map > 5

        if now_hard != hard:
            click(self.timer, 800, 80, delay=3)

        self.timer.chapter = 'battle'
        self.timer.node = self.map

        click(self.timer, 180 * (self.map - hard * 5), 200)
        start_time = time.time()
        while not identify_page(self.timer, 'fight_prepare_page'):
            time.sleep(.15)
            if(time.time() - start_time > 15):
                raise BaseException()

        QuickRepair(self.timer)
        click(self.timer, 900, 500, delay=0)
        while(identify_page(self.timer, 'fight_prepare_page')):
            time.sleep(.15)
            if(ImagesExist(self.timer, SymbolImage[9], need_screen_shot=0)):
                return 'run out of battle times'
            if(time.time() - start_time > 15):
                raise BaseException()

        return 'success'

    def _make_decision(self) -> str:
        match self.Info.state:
            case "battle_page":
                return "fight end"
        # 进行通用NodeLevel决策
        action, fight_stage = self.node.make_decision(self.Info.state, self.Info.last_state, self.Info.last_action)
        self.Info.last_action = action
        return fight_stage
