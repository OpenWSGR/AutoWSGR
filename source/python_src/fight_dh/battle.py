import time

import yaml
from constants.image_templates import FightImage, SymbolImage, IdentifyImages
from game.game_operation import QuickRepair, goto_game_page, identify_page, process_bad_network
from controller.run_timer import Timer, ImagesExist, WaitImages
from utils.io import recursive_dict_update

from fight_dh.common import FightInfo, FightPlan, NodeLevelDecisionBlock

"""
战役模块
"""


class BattleInfo(FightInfo):
    def __init__(self, timer: Timer) -> None:
        super().__init__(timer)

        self.start_page = "battle_page"

        self.successor_states = {
            "proceed": ["spot_enemy_success", "formation", "fight_period"],
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
            "night": [FightImage[6], 120],
            "night_fight_period": [SymbolImage[4], 3],
            "result": [FightImage[16], 60],
            "battle_page": [IdentifyImages["battle_page"][0], 5]
        }

    def reset(self):
        self.last_state = ""
        self.last_action = ""
        self.state = "proceed"

    def _before_match(self):
        # 点击加速
        if self.state in ["proceed", "fight_condition"]:
            p = self.timer.Android.click(380, 520, delay=0, enable_subprocess=True, print=0, no_log=True)
        self.timer.UpdateScreen()

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
        self.timer.chapter = 'battle'
        self.timer.node = self.map
        # 加载战役节点计划
        node_args = recursive_dict_update(node_defaults, plan_args["node_args"])
        self.node = NodeLevelDecisionBlock(timer, node_args)

        self.Info = BattleInfo(timer)

    def _enter_fight(self) -> str:
        goto_game_page(self.timer, "battle_page")
        # 切换正确难度
        now_hard = WaitImages(self.timer, [FightImage[9], FightImage[15]])
        hard = self.map > 5
        if now_hard != hard:
            self.timer.Android.click(800, 80, delay=1)
        self.timer.Android.click(180 * (self.map - hard * 5), 200)
        QuickRepair(self.timer, self.repair_mode)

        start_time = time.time()
        while True:
            self.timer.Android.click(900, 500, delay=0)    # 点“开始出征”
            self.timer.UpdateScreen()
            if ImagesExist(self.timer, SymbolImage[3], need_screen_shot=0):
                return "dock is full"
            if ImagesExist(self.timer, SymbolImage[9], need_screen_shot=0):
                return 'out of times'
            if not identify_page(self.timer, 'fight_prepare_page', need_screen_shot=False):
                break
            if time.time() - start_time > 15:
                if process_bad_network(self.timer):
                    if identify_page(self.timer, 'fight_prepare_page'):
                        return self._enter_fight(self.timer)
                else:
                    raise TimeoutError("map_fight prepare timeout")

        return 'success'

    def _make_decision(self) -> str:

        self.Info.update_state()
        if self.Info.state == "battle_page":
            return "fight end"

        # 进行通用NodeLevel决策
        action, fight_stage = self.node.make_decision(self.Info.state, self.Info.last_state, self.Info.last_action)
        self.Info.last_action = action
        return fight_stage
