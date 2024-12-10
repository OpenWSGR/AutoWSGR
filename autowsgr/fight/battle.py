from autowsgr.constants import literals
from autowsgr.constants.image_templates import IMG
from autowsgr.fight.common import DecisionBlock, FightInfo, FightPlan, start_march
from autowsgr.game.game_operation import get_ship, quick_repair
from autowsgr.game.get_game_info import detect_ship_stats
from autowsgr.timer import Timer
from autowsgr.utils.io import recursive_dict_update, yaml_to_dict


"""
战役模块/单点战斗模板
"""


class BattleInfo(FightInfo):
    def __init__(self, timer: Timer) -> None:
        super().__init__(timer)

        self.end_page = 'battle_page'

        self.successor_states = {
            'proceed': ['spot_enemy_success', 'formation', 'fight_period'],
            'spot_enemy_success': {
                'retreat': ['battle_page'],
                'fight': ['formation', 'fight_period'],
            },
            'formation': ['fight_period'],
            'fight_period': ['night', 'result'],
            'night': {
                'yes': ['result'],
                'no': [['result', 7]],
            },
            'night_fight_period': ['result'],
            'result': ['battle_page'],  # 两页战果
        }

        self.state2image = {
            'proceed': [IMG.fight_image[5], 7.5],
            'spot_enemy_success': [IMG.fight_image[2], 15],
            'formation': [IMG.fight_image[1], 15, 0.8],
            'fight_period': [IMG.symbol_image[4], 7.5],
            'night': [IMG.fight_image[6], 150],
            'result': [IMG.fight_image[16], 75],
            'battle_page': [
                IMG.identify_images.battle_page,
                7.5,
            ],
        }

        self.after_match_delay = {
            'night': 1.75,
            'get_ship': 1,
        }

    def reset(self):
        self.fight_history.reset()
        self.last_state = ''
        self.last_action = ''
        self.state = 'proceed'

    def _before_match(self):
        # 点击加速
        if self.state in ['proceed']:
            self.timer.click(380, 520, delay=0, enable_subprocess=True)
        self.timer.update_screen()

    def _after_match(self):
        if self.state == 'get_ship':
            get_ship(self.timer)
        super()._after_match()


class BattlePlan(FightPlan):
    def __init__(self, timer, plan_path=None) -> None:
        super().__init__(timer)

        # 加载默认配置
        default_args = yaml_to_dict(self.timer.plan_tree['default'])
        plan_defaults = default_args['battle_defaults']
        plan_defaults.update({'node_defaults': default_args['node_defaults']})

        # 加载计划配置
        if plan_path is not None:
            plan_args = yaml_to_dict(self.timer.plan_tree['battle'][plan_path])
            args = recursive_dict_update(plan_defaults, plan_args, skip=['node_args'])
        else:
            args = plan_defaults
        self.__dict__.update(args)

        # 加载节点配置
        node_defaults = self.node_defaults
        if plan_path is not None:
            node_args = recursive_dict_update(node_defaults, plan_args['node_args'])
        else:
            node_args = node_defaults
        self.node = DecisionBlock(timer, node_args)
        self.info = BattleInfo(timer)

    def _go_fight_prepare_page(self):
        self.timer.goto_game_page('battle_page')
        now_hard = self.timer.wait_images([IMG.fight_image[9], IMG.fight_image[15]])
        hard = self.map > 5
        if now_hard != hard:
            self.timer.click(800, 80, delay=1)

    def _enter_fight(self) -> str:
        self._go_fight_prepare_page()
        self.timer.click(180 * ((self.map - 1) % 5 + 1), 200)
        self.timer.wait_pages('fight_prepare_page', after_wait=0.15)
        self.info.ship_stats = detect_ship_stats(self.timer)
        quick_repair(self.timer, self.repair_mode, ship_stats=self.info.ship_stats)
        try:
            return start_march(self.timer)
        except TimeoutError:
            self.logger.warning(
                '由于进入战斗超时跳过了一次战役, 请检查战役队伍中是否有舰船正在远征',
            )
            return literals.SKIP_FIGHT

    def _make_decision(self, *args, **kwargs) -> str:
        state = self.update_state() if 'skip_update' not in kwargs else self.info.state
        if state == 'need SL':
            return 'need SL'
        if self.info.state == 'battle_page':
            return literals.FIGHT_END_FLAG

        # 进行通用 NodeLevel 决策
        action, fight_stage = self.node.make_decision(
            self.info.state,
            self.info.last_state,
            self.info.last_action,
            self.info,
        )
        self.info.last_action = action
        return fight_stage
