import copy
import time

import yaml
from api import ClickImage, ImagesExist, UpdateScreen, click
from constants import FIGHT_CONDITIONS_POSITON, FightImage, identify_images
from game import (ConfirmOperation, DetectShipStatu, GetEnemyCondition,
                  MoveTeam, QuickRepair, UpdateShipPoint, UpdateShipPosition,
                  change_fight_map, goto_game_page, identify_page,
                  process_bad_network)
from supports import SymbolImage, Timer
from utils.io import recursive_dict_update

from .common import FightInfo, FightPlan, NodeLevelDecisionBlock, Ship

"""
常规战决策模块
TODO: 1.资源点 2.依据敌方选择阵型
"""


class NormalFightInfo(FightInfo):
    """ 存储战斗中需要用到的所有状态信息 """

    def __init__(self, timer: Timer) -> None:
        super().__init__(timer)

        self.start_page = "map_page"

        self.successor_states = {
            "proceed": {
                "yes": ["fight_condition", "spot_enemy_success", "formation", "fight_period"],
                "no": ["map_page"]
            },
            "fight_condition": ["spot_enemy_success", "formation", "fight_period"],
            "spot_enemy_success": {
                "detour": ["fight_condition", "spot_enemy_success", "formation"],
                "retreat": ["map_page"],
                "fight": ["formation"],
            },
            "formation": ["fight_period"],
            "fight_period": ["night", "result"],
            "night": {
                "yes": ["night_fight_period"],
                "no": [["result", 5]],
            },
            "night_fight_period": ["result"],
            "result": ["proceed", "map_page", "get_ship", "flagship_severe_damage"],    # 两页战果
            "get_ship": ["proceed", "map_page", "flagship_severe_damage"],  # 捞到舰船
            "flagship_severe_damage": ["map_page"],
        }

        self.state2image = {
            "proceed": [FightImage[5], 5],
            "fight_condition": [FightImage[10], 15],
            "spot_enemy_success": [FightImage[2], 15],
            "formation": [FightImage[1], 15],
            "fight_period": [SymbolImage[4], 3],
            "night": [FightImage[6], .85, 120],
            "night_fight_period": [SymbolImage[4], 3],
            "result": [FightImage[3], 60],
            "get_ship": [SymbolImage[8], 5],
            "flagship_severe_damage": [FightImage[4], 5],
            "map_page": [identify_images["map_page"][0], 5]
        }

    def reset(self):
        self.last_state = "proceed"
        self.last_action = "yes"
        self.state = "proceed"  # 初始状态等同于 proceed选择yes

        # TODO: 舰船信息，暂时不用
        self.ally_ships = [Ship() for _ in range(6)]  # 我方舰船状态
        self.enemy_ships = [Ship() for _ in range(6)]  # 敌方舰船状态

    def _before_match(self):
        # 点击加速
        if self.state in ["proceed", "fight_condition"]:
            p = click(self.timer, 380, 520, delay=0, enable_subprocess=True, print=0, no_log=True)

        UpdateScreen(self.timer)

        # TODO：在少数情况下会获取错误，需要找到原因
        if self.state in ["proceed", "fight_condition"]:
            UpdateShipPosition(self.timer)
            UpdateShipPoint(self.timer)

        # TODO：试试资源点能不能行
        if self.state in ["proceed", "fight_condition", "get_ship"]:
            ConfirmOperation(self.timer, delay=0)

    def _after_match(self):
        # 在某些State下可以记录额外信息
        if self.state == "spot_enemy_success":
            GetEnemyCondition(self.timer, 'fight')
        elif self.state == "result":
            DetectShipStatu(self.timer, 'sumup')
            self.timer.fight_result.detect_result()

    @property
    def node(self):
        return self.timer.ship_point


class NormalFightPlan(FightPlan):
    """" 常规战斗的决策模块 """

    def __init__(self, timer: Timer, plan_path, default_path) -> None:
        super().__init__(timer)

        default_args = yaml.load(open(default_path, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
        plan_defaults, node_defaults = default_args["normal_fight_defaults"], default_args["node_defaults"]
        # 加载地图计划
        plan_args = yaml.load(open(plan_path, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
        args = recursive_dict_update(plan_defaults, plan_args, skip=['node_args'])
        self.__dict__.update(args)
        # 加载各节点计划
        self.nodes = {}
        for node_name in self.selected_nodes:
            node_args = copy.deepcopy(node_defaults)
            node_args = recursive_dict_update(node_args, plan_args['node_args'][node_name])
            self.nodes[node_name] = NodeLevelDecisionBlock(timer, node_args)

        # 构建信息存储结构
        self.Info = NormalFightInfo(self.timer)

    def _enter_fight(self) -> str:
        """
        从任意界面进入战斗.

        :return: 进入战斗状态信息，包括['success', 'dock is full].
        """

        goto_game_page(self.timer, 'map_page')
        change_fight_map(self.timer, self.chapter, self.map)
        goto_game_page(self.timer, 'fight_prepare_page')
        MoveTeam(self.timer, self.fleet_id)  # TODO: 支持按列表修改舰船
        QuickRepair(self.timer, self.repair_mode)

        # 异常处理
        start_time = time.time()
        UpdateScreen(self.timer)
        while identify_page(self.timer, 'fight_prepare_page', need_screen_shot=False):
            click(self.timer, 900, 500, 1, delay=0)  # 点击：开始出征
            UpdateScreen(self.timer)
            if ImagesExist(self.timer, SymbolImage[3], need_screen_shot=0):
                return "dock is full"
            if False:  # TODO: 大破出征确认
                pass
            if False:  # TODO: 补给为空
                pass
            if time.time() - start_time > 15:
                if process_bad_network(self.timer):
                    if identify_page(self.timer, 'fight_prepare_page'):
                        return self._enter_fight(self.timer)
                else:
                    raise TimeoutError("map_fight prepare timeout")

        return "success"

    def _make_decision(self) -> str:

        self.Info.update_state()
        state = self.Info.state

        # 进行MapLevel的决策
        if state == "map_page":
            return "fight end"

        elif state == "fight_condition":
            value = self.fight_condition
            click(self.timer, *FIGHT_CONDITIONS_POSITON[value])
            self.Info.last_action = value
            return "fight continue"

        elif state == "spot_enemy_success":
            if self.Info.node not in self.selected_nodes:  # 不在白名单之内直接SL
                click(self.timer, 677, 492, delay=0)
                self.Info.last_action = "retreat"
                return "fight end"

        elif state == "proceed":
            is_proceed = self.nodes[self.Info.node].proceed
            if is_proceed:
                click(self.timer, 325, 350)
                self.Info.last_action = "yes"
                return "fight continue"
            else:
                click(self.timer, 615, 350)
                self.Info.last_action = "no"
                return "fight end"

        elif state == "flagship_severe_damage":
            ClickImage(self.timer, FightImage[4], must_click=True, delay=0.25)
            return 'fight end'

        # 进行通用NodeLevel决策
        action, fight_stage = self.nodes[self.Info.node].make_decision(state, self.Info.last_state, self.Info.last_action)
        self.Info.last_action = action
        return fight_stage
