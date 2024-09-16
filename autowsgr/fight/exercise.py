import copy
import os

from autowsgr.constants import literals
from autowsgr.constants.image_templates import IMG
from autowsgr.game.game_operation import MoveTeam, detect_ship_stats, quick_repair
from autowsgr.game.get_game_info import get_enemy_condition, get_exercise_stats
from autowsgr.timer import Timer
from autowsgr.utils.io import recursive_dict_update, yaml_to_dict

from .common import DecisionBlock, FightInfo, FightPlan, Ship, start_march

"""
演习决策模块
"""


class ExerciseDecisionBlock(DecisionBlock):
    def make_decision(self, state, last_state, last_action, Info: FightInfo):
        if state == "rival_info":
            max_times = self.max_refresh_times
            self.formation_chosen = self.formation
            while max_times >= 0:
                Info.enemys = get_enemy_condition(self.timer)
                act = self._check_rules(Info.enemys)
                if act == "refresh":
                    if max_times > 0:
                        max_times -= 1
                        self.timer.click(665, 400, delay=0.75)
                    else:
                        if False:
                            # if self.discard:
                            self.timer.click(878, 136, delay=1)
                            return "discard", literals.FIGHT_CONTINUE_FLAG
                        else:
                            break
                elif isinstance(act, int):
                    self.formation_chosen = act
                elif act == None:
                    break

            self.timer.click(804, 390, delay=0)
            return "fight", literals.FIGHT_CONTINUE_FLAG

        elif state == "fight_prepare_page":
            MoveTeam(self.timer, self.fleet_id)
            Info.ship_stats = detect_ship_stats(self.timer)
            quick_repair(self.timer, ship_stats=Info.ship_stats)
            if start_march(self.timer) != literals.OPERATION_SUCCESS_FLAG:
                return self.make_decision(state, last_state, last_action, Info)
            return None, literals.FIGHT_CONTINUE_FLAG

        elif state == "spot_enemy_success":
            self.timer.click(900, 500, delay=0)
            return None, literals.FIGHT_CONTINUE_FLAG

        elif state == "formation":
            self.timer.click(573, self.formation_chosen * 100 - 20, delay=2)
            return None, literals.FIGHT_CONTINUE_FLAG

        return super().make_decision(state, last_state, last_action, Info)


class NormalExerciseInfo(FightInfo):
    """存储战斗中需要用到的所有状态信息"""

    def __init__(self, timer: Timer) -> None:
        super().__init__(timer)
        self.end_page = "exercise_page"
        self.robot = True
        self.successor_states = {
            "exercise_page": ["rival_info"],
            "rival_info": {
                "fight": ["fight_prepare_page"],
                "discard": ["exercise_page"],
            },
            "fight_prepare_page": ["spot_enemy_success", "formation", "fight_period"],
            "spot_enemy_success": ["formation", "fight_period"],
            "formation": ["fight_period"],
            "fight_period": ["night", "result"],
            "night": {
                "yes": ["night_fight_period"],
                "no": [["result", 7]],
            },
            "night_fight_period": ["result"],
            "result": ["exercise_page"],  # 两页战果
        }

        self.state2image = {
            "exercise_page": [IMG.identify_images["exercise_page"], 7.5],
            "rival_info": [IMG.exercise_image["rival_info"], 7.5],
            "fight_prepare_page": [IMG.identify_images["fight_prepare_page"], 7.5],
            "spot_enemy_success": [IMG.fight_image[2], 15],
            "formation": [IMG.fight_image[1], 15],
            "fight_period": [IMG.symbol_image[4], 10],
            "night": [IMG.fight_image[6], 0.85, 180],
            "night_fight_period": [IMG.symbol_image[4], 10],
            "result": [IMG.fight_image[3], 90],
        }

        self.after_match_delay = {
            "night": 1.75,
        }

    def reset(self):
        self.fight_history.reset()
        self.state = "rival_info"  # 初始状态等同于 "rival_info" 选择 'discard'
        self.last_action = "discard"
        # TODO: 舰船信息，暂时不用
        self.ally_ships = [Ship() for _ in range(6)]  # 我方舰船状态
        self.enemy_ships = [Ship() for _ in range(6)]  # 敌方舰船状态

    def _before_match(self):
        # 点击加速
        if self.state in ["fight_prepare_page"]:
            p = self.timer.click(
                380, 520, delay=0, enable_subprocess=True, not_show=True
            )

        self.timer.update_screen()

    @property
    def node(self):
        return self.timer.ship_point


class NormalExercisePlan(FightPlan):
    """ " 常规战斗的决策模块"""

    def __init__(self, timer: Timer, plan_path):
        super().__init__(timer)

        # 加载默认配置
        default_args = yaml_to_dict(os.path.join(self.config.PLAN_ROOT, "default.yaml"))
        plan_defaults = default_args["exercise_defaults"]
        plan_defaults.update({"node_defaults": default_args["node_defaults"]})

        # 加载计划配置
        plan_args = yaml_to_dict(os.path.join(self.config.PLAN_ROOT, plan_path))
        args = recursive_dict_update(plan_defaults, plan_args, skip=["node_args"])
        self.__dict__.update(args)

        # 加载节点配置
        node_defaults = self.node_defaults
        self.nodes = {}
        for node_name in self.selected_nodes:
            node_args = copy.deepcopy(node_defaults)
            if node_name in plan_args["node_args"]:
                node_args = recursive_dict_update(
                    node_args, plan_args["node_args"][node_name]
                )
            self.nodes[node_name] = ExerciseDecisionBlock(timer, node_args)

        # 构建信息存储结构
        self.Info = NormalExerciseInfo(self.timer)

    def _enter_fight(self, same_work=False) -> str:
        """
        从任意界面进入战斗.

        :return: 进入战斗状态信息，包括['success', 'dock is full'].
        """
        if same_work == False:
            self.timer.goto_game_page("exercise_page")

        self._exercise_times = self.exercise_times
        self.exercise_stats = [None, None]
        return literals.OPERATION_SUCCESS_FLAG

    def _make_decision(self, *args, **kwargs):
        if "skip_update" not in kwargs.keys():
            state = self.update_state()
        else:
            state = self.Info.state
        # 进行MapLevel的决策
        if state == "exercise_page":
            self.exercise_stats = get_exercise_stats(self.timer, self.exercise_stats[1])
            if self._exercise_times > 0 and any(self.exercise_stats[2:]):
                pos = self.exercise_stats[2:].index(True)
                self.rival = "player"
                self.timer.click(770, (pos + 1) * 110 - 10)
                return literals.FIGHT_CONTINUE_FLAG
            elif self.robot and self.exercise_stats[1]:
                self.timer.swipe(800, 200, 800, 400)  # 上滑
                self.timer.click(770, 100)
                self.rival = "robot"
                self.exercise_stats[1] = False
                return literals.FIGHT_CONTINUE_FLAG

            else:
                return literals.FIGHT_END_FLAG

        # 进行通用NodeLevel决策
        action, fight_stage = self.nodes[self.rival].make_decision(
            state, self.Info.last_state, self.Info.last_action, self.Info
        )
        self.Info.last_action = action
        return fight_stage
