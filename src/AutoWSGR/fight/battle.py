import os

from AutoWSGR.constants.image_templates import IMG
from AutoWSGR.controller.run_timer import Timer
from AutoWSGR.game.game_operation import QuickRepair, get_ship
from AutoWSGR.game.get_game_info import DetectShipStats
from AutoWSGR.utils.io import recursive_dict_update, yaml_to_dict
from AutoWSGR.constants import literals

from .common import FightInfo, FightPlan, DecisionBlock, start_march

"""
战役模块/单点战斗模板
"""


class BattleInfo(FightInfo):
    def __init__(self, timer: Timer) -> None:
        super().__init__(timer)

        self.end_page = "battle_page"

        self.successor_states = {
            "proceed": ["spot_enemy_success", "formation", "fight_period"],
            "spot_enemy_success": {
                "retreat": ["battle_page"],
                "fight": ["formation", "fight_period"],
            },
            "formation": ["fight_period"],
            "fight_period": ["night", "result"],
            "night": {
                "yes": ["result"],
                "no": [["result", 10]],
            },
            "night_fight_period": ["result"],
            "result": ["battle_page"],    # 两页战果
        }

        self.state2image = {
            "proceed": [IMG.fight_image[5], 5],
            "spot_enemy_success": [IMG.fight_image[2], 15],
            "formation": [IMG.fight_image[1], 15, .8],
            "fight_period": [IMG.symbol_image[4], 5],
            "night": [IMG.fight_image[6], 120],
            "result": [IMG.fight_image[16], 60],
            "battle_page": [IMG.identify_images["battle_page"][0], 5, ]
        }
        
        self.after_match_delay = {
            "night":1.5,
        }

    def reset(self):
        self.last_state = ""
        self.last_action = ""
        self.state = "proceed"

    def _before_match(self):
        # 点击加速
        if self.state in ["proceed"]:
            p = self.timer.Android.click(380, 520, delay=0, enable_subprocess=True, not_show=True)
        self.timer.update_screen()

    def _after_match(self):
        if self.state == "result":
            DetectShipStats(self.timer, 'sumup')
            self.fight_result.detect_result()
        elif self.state == 'get_ship':
            get_ship(self.timer)


class BattlePlan(FightPlan):

    def __init__(self, timer, plan_path=None, decision_block=None) -> None:
        super().__init__(timer)

        # 加载默认配置
        default_args = yaml_to_dict(os.path.join(self.config.PLAN_ROOT, "default.yaml"))
        plan_defaults = default_args["battle_defaults"]
        plan_defaults.update({"node_defaults": default_args["node_defaults"]})

        # 加载计划配置
        if (plan_path is not None):
            plan_args = yaml_to_dict(os.path.join(self.config.PLAN_ROOT, plan_path))
            args = recursive_dict_update(plan_defaults, plan_args, skip=['node_args'])
        else:
            args = plan_defaults
        self.__dict__.update(args)

        # 加载节点配置
        node_defaults = self.node_defaults
        if (plan_path is not None):
            node_args = recursive_dict_update(node_defaults, plan_args["node_args"])
        else:
            node_args = node_defaults
        self.node = DecisionBlock(timer, node_args)
        self.Info = BattleInfo(timer)
        self.decision_block = decision_block

    def go_fight_prepare_page(self):
        self.timer.goto_game_page("battle_page")
        now_hard = self.timer.wait_images([IMG.fight_image[9], IMG.fight_image[15]])
        hard = self.map > 5
        if now_hard != hard:
            self.timer.Android.click(800, 80, delay=1)

    def _enter_fight(self, same_work=False) -> str:
        if (same_work == False):
            self.go_fight_prepare_page()
        self.timer.Android.click(180 * ((self.map - 1) % 5 + 1), 200)
        self.timer.wait_pages('fight_prepare_page', after_wait=.15)
        QuickRepair(self.timer, self.repair_mode)
        return start_march(self.timer)

    def _make_decision(self) -> str:

        _action = None
        self.update_state()
        if self.Info.state == "battle_page":
            return literals.FIGHT_END_FLAG
        if (self.decision_block is not None):
            _action = self.decision_block.make_decision(self.Info.state)
        # 进行通用NodeLevel决策
        action, fight_stage = self.node.make_decision(self.Info.state, self.Info.last_state, self.Info.last_action, _action)
        self.Info.last_action = action
        return fight_stage
