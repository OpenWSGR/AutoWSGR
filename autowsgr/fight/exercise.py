import copy

from autowsgr.configs import ExerciseConfig
from autowsgr.constants.image_templates import IMG
from autowsgr.fight.common import DecisionBlock, FightInfo, FightPlan, start_march
from autowsgr.game.game_operation import detect_ship_stats, move_team, quick_repair
from autowsgr.game.get_game_info import get_enemy_condition, get_exercise_stats
from autowsgr.timer import Timer
from autowsgr.types import ConditionFlag, Formation, SearchEnemyAction
from autowsgr.utils.io import recursive_dict_update, yaml_to_dict


"""
演习决策模块
"""


class ExerciseDecisionBlock(DecisionBlock):
    def __init__(
        self,
        timer: Timer,
        node_args: dict,
        max_refresh_times: int,
        fleet_id: int,
    ) -> None:
        super().__init__(timer, node_args)
        self.max_refresh_times = max_refresh_times
        self.fleet_id = fleet_id

    def make_decision(self, state, last_state, last_action, info: FightInfo):
        if state == 'rival_info':
            max_times = self.max_refresh_times
            self.formation_chosen = self.config.formation
            while max_times >= 0:
                info.enemies = get_enemy_condition(self.timer)
                act = self._check_rules(info.enemies)
                if act == SearchEnemyAction.refresh:
                    if max_times > 0:
                        max_times -= 1
                        self.timer.click(665, 400, delay=0.75)
                    else:
                        break
                elif isinstance(act, Formation):
                    self.formation_chosen = act
                elif act is SearchEnemyAction.no_action:
                    break

            self.timer.click(804, 390, delay=0)
            return 'fight', ConditionFlag.FIGHT_CONTINUE

        if state == 'fight_prepare_page':
            move_team(self.timer, self.fleet_id)
            info.ship_stats = detect_ship_stats(self.timer)
            quick_repair(self.timer, ship_stats=info.ship_stats)
            if start_march(self.timer) != ConditionFlag.OPERATION_SUCCESS:
                return self.make_decision(state, last_state, last_action, info)
            return None, ConditionFlag.FIGHT_CONTINUE

        if state == 'spot_enemy_success':
            self.timer.click(900, 500, delay=0)
            return None, ConditionFlag.FIGHT_CONTINUE

        if state == 'formation':
            self.timer.click(573, self.formation_chosen * 100 - 20, delay=2)
            return None, ConditionFlag.FIGHT_CONTINUE

        return super().make_decision(state, last_state, last_action, info)


class NormalExerciseInfo(FightInfo):
    """存储战斗中需要用到的所有状态信息"""

    def __init__(self, timer: Timer) -> None:
        super().__init__(timer)
        self.end_page = 'exercise_page'
        self.successor_states = {
            'exercise_page': ['rival_info'],
            'rival_info': {
                'fight': ['fight_prepare_page'],
                'discard': ['exercise_page'],
            },
            'fight_prepare_page': ['spot_enemy_success', 'formation', 'fight_period'],
            'spot_enemy_success': ['formation', 'fight_period'],
            'formation': ['fight_period'],
            'fight_period': ['night', 'result'],
            'night': {
                'yes': ['night_fight_period'],
                'no': [['result', 7]],
            },
            'night_fight_period': ['result'],
            'result': ['exercise_page'],  # 两页战果
        }

        self.state2image = {
            'exercise_page': [IMG.identify_images['exercise_page'], 7.5],
            'rival_info': [IMG.exercise_image['rival_info'], 7.5],
            'fight_prepare_page': [IMG.identify_images['fight_prepare_page'], 7.5],
            'spot_enemy_success': [IMG.fight_image[2], 15],
            'formation': [IMG.fight_image[1], 15],
            'fight_period': [IMG.symbol_image[4], 10],
            'night': [IMG.fight_image[6], 0.85, 180],
            'night_fight_period': [IMG.symbol_image[4], 10],
            'result': [IMG.fight_image[3], 90],
        }

        self.after_match_delay = {
            'night': 1.75,
        }

    def reset(self):
        self.fight_history.reset()
        self.state = 'rival_info'  # 初始状态等同于 "rival_info" 选择 'discard'
        self.last_action = 'discard'

    def _before_match(self):
        # 点击加速
        if self.state in ['fight_prepare_page']:
            self.timer.click(
                380,
                520,
                delay=0,
                enable_subprocess=True,
            )

        self.timer.update_screen()

    @property
    def node(self):
        return self.timer.ship_point


class NormalExercisePlan(FightPlan):
    """
    常规战斗的决策模块

    Args:
        plan_path: 以 PLAN_ROOT/exercise 为根的相对路径

        fleet_id: 指定舰队编号, 如果为 None 则使用计划中的参数

    """

    def __init__(self, timer: Timer, plan_path: str, fleet_id: int | None) -> None:
        super().__init__(timer)

        # 加载计划配置
        plan_args = yaml_to_dict(self.timer.plan_tree['exercise'][plan_path])
        if fleet_id is not None:
            plan_args['fleet_id'] = fleet_id  # 舰队编号
        assert 'fleet_id' in plan_args, '未指定作战舰队'
        self.config = ExerciseConfig.from_dict(plan_args)

        self.nodes: dict[str, ExerciseDecisionBlock] = {}
        for node_name in self.config.selected_nodes:
            node_args = copy.deepcopy(plan_args.get('node_defaults', {}))
            if node_name in plan_args['node_args']:
                node_args = recursive_dict_update(
                    node_args,
                    plan_args['node_args'][node_name],
                )
            self.nodes[node_name] = ExerciseDecisionBlock(
                timer,
                node_args,
                self.config.max_refresh_times,
                self.config.fleet_id,
            )

        # 构建信息存储结构
        self.info = NormalExerciseInfo(self.timer)

    def _enter_fight(self) -> str:
        """
        从任意界面进入战斗.

        Returns:
            ConditionFlag
        """
        self.timer.goto_game_page('exercise_page')
        self._exercise_times = self.config.exercise_times
        self.exercise_stats = [None, None]
        return ConditionFlag.OPERATION_SUCCESS

    def _make_decision(self, *args, **kwargs):
        state = self.update_state() if 'skip_update' not in kwargs else self.info.state
        if state == ConditionFlag.SL:
            return ConditionFlag.SL

        # 进行MapLevel的决策
        if state == 'exercise_page':
            self.exercise_stats = get_exercise_stats(self.timer, self.exercise_stats[1])
            if self._exercise_times > 0 and any(self.exercise_stats[2:]):
                pos = self.exercise_stats[2:].index(True)
                self.rival = 'player'
                self.timer.click(770, (pos + 1) * 110 - 10)
                return ConditionFlag.FIGHT_CONTINUE
            if 'robot' in self.config.selected_nodes and self.exercise_stats[1]:
                self.timer.swipe(800, 200, 800, 400)  # 上滑
                self.timer.click(770, 100)
                self.rival = 'robot'
                self.exercise_stats[1] = False
                return ConditionFlag.FIGHT_CONTINUE

            return ConditionFlag.FIGHT_END

        # 进行通用NodeLevel决策
        action, fight_stage = self.nodes[self.rival].make_decision(
            state,
            self.info.last_state,
            self.info.last_action,
            self.info,
        )
        self.info.last_action = action
        return fight_stage
