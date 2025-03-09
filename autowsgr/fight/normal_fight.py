import copy
import os
import time

from autowsgr.configs import FightConfig
from autowsgr.constants.custom_exceptions import ImageNotFoundErr
from autowsgr.constants.data_roots import MAP_ROOT
from autowsgr.constants.image_templates import IMG
from autowsgr.fight.common import DecisionBlock, FightInfo, FightPlan, start_march
from autowsgr.game.game_operation import change_ships, move_team, quick_repair
from autowsgr.game.get_game_info import detect_ship_stats, get_enemy_condition
from autowsgr.timer import Timer
from autowsgr.types import ConditionFlag
from autowsgr.utils.io import recursive_dict_update, yaml_to_dict
from autowsgr.utils.math_functions import cal_dis


"""
常规战决策模块/地图战斗用模板
"""

MAP_NUM = [5, 6, 4, 4, 5, 4, 5, 5, 4]  # 每一章的地图数量


class NormalFightInfo(FightInfo):
    def __init__(self, timer: Timer, chapter_id, map_id) -> None:
        super().__init__(timer)

        self.point_positions = None
        self.map_image = IMG.identify_images.map_page
        self.ship_image = [IMG.symbol_image[8], IMG.symbol_image[13]]
        self.chapter = chapter_id  # 章节名,战役为 'battle', 演习为 'exercise'
        self.map = map_id  # 节点名
        self.ship_position = (0, 0)
        self.node = 'A'  # 常规地图战斗中,当前战斗点位的编号
        # 实现通用 FightInfo 接口
        self.end_page = 'map_page'
        self.successor_states = {
            'proceed': {
                'yes': [
                    'fight_condition',
                    'spot_enemy_success',
                    'formation',
                    'fight_period',
                    'map_page',
                ],
                'no': ['map_page'],
            },
            'fight_condition': ['spot_enemy_success', 'formation', 'fight_period'],
            'spot_enemy_success': {
                'detour': [
                    'fight_condition',
                    'spot_enemy_success',
                    'formation',
                    'fight_period',
                ],
                'retreat': ['map_page'],
                'fight': ['formation', 'fight_period'],
            },
            'formation': ['fight_period'],
            'fight_period': ['night', 'result'],
            'night': {
                'yes': ['result'],
                'no': [['result', 10]],
            },
            'result': [
                'proceed',
                'map_page',
                'get_ship',
                'flagship_severe_damage',
            ],  # 两页战果
            'get_ship': ['proceed', 'map_page', 'flagship_severe_damage'],  # 捞到舰船
            'flagship_severe_damage': ['map_page'],
        }

        self.state2image = {
            'proceed': [IMG.fight_image[5], 7.5],
            'fight_condition': [IMG.fight_image[10], 22.5],
            'spot_enemy_success': [IMG.fight_image[2], 22.5],
            'formation': [IMG.fight_image[1], 22.5],
            'fight_period': [IMG.symbol_image[4], 30],
            'night': [IMG.fight_image[6], 150],
            'result': [IMG.fight_image[3], 90],
            'get_ship': [self.ship_image, 5],
            'flagship_severe_damage': [IMG.fight_image[4], 7.5],
            'map_page': [self.map_image, 7.5],
        }

        self.after_match_delay = {
            'night': 1.75,
            'proceed': 0.5,
            'get_ship': 1,
        }

    def reset(self):
        self.fight_history.reset()
        self.last_state = 'proceed'
        self.last_action = 'yes'
        self.state = 'proceed'  # 初始状态等同于 proceed 选择 yes

    def _before_match(self):
        # 点击加速
        if self.last_state in ['proceed', 'fight_condition'] or self.last_action == 'detour':
            self.timer.click(250, 520, delay=0, enable_subprocess=True)

        self.timer.update_screen()

        # 在地图上走的过程中获取舰船位置
        if self.last_state == 'proceed' or self.last_action == 'detour':
            self._update_ship_position()
            self._update_ship_point()
            pos = self.timer.get_image_position(IMG.confirm_image[3], False, 0.8)
            if pos:
                self.timer.confirm_operation(delay=0.25, must_confirm=1, confidence=0.8)

    def _after_match(self):
        # 在某些State下可以记录额外信息
        if self.state == 'spot_enemy_success':
            get_enemy_condition(self.timer, 'fight')
        super()._after_match()

    # ======================== Functions ========================

    def _update_ship_position(self):
        """在战斗移动界面(有一个黄色小船在地图上跑)更新黄色小船的位置"""
        pos = self.timer.get_image_position(IMG.fight_image[7], False, 0.8)
        if pos is None:
            pos = self.timer.get_image_position(IMG.fight_image[8], False, 0.8)
        if pos is None:
            return
        self.ship_position = pos
        if self.timer.config.show_map_node:
            self.timer.logger.debug(self.ship_position)

    def _update_ship_point(self):
        """更新黄色小船(战斗地图上那个)所在的点位 (1-1A 这种,'A' 就是点位)"""

        self.node = 'A'
        for i in range(26):
            ch = chr(ord('A') + i)
            if ch not in self.point_positions:
                continue
            if cal_dis(self.point_positions[ch], self.ship_position) < cal_dis(
                self.point_positions[self.node],
                self.ship_position,
            ):
                self.node = ch

        if self.timer.config.show_map_node:
            self.timer.logger.debug(self.node)

    def load_point_positions(self, map_path):
        """地图文件命名格式: [chapter]-[map].yaml"""
        self.point_positions = yaml_to_dict(
            os.path.join(map_path, str(self.chapter) + '-' + str(self.map) + '.yaml'),
        )


def check_blood(blood, rule) -> bool:
    """检查血量状态是否满足前进条件
        >>>check_blood([None, 1, 1, 1, 2, -1, -1], [2, 2, 2, -1, -1, -1])

        >>>True
    Args:
        blood (list): 1-based
        rule (list): 0-based
    """
    for i in range(max(len(blood) - 1, len(rule))):
        if blood[i + 1] == -1 or rule[i] == -1:
            continue
        if blood[i + 1] >= rule[i]:
            return False
    return True


class NormalFightPlan(FightPlan):
    """ " 常规战斗的决策模块"""

    """ 多点战斗基本模板 """

    def __init__(self, timer: Timer, plan_path, fleet_id=None, fleet=-1) -> None:
        """初始化决策模块,可以重新指定默认参数,优先级更高

        Args:
            fleet_id: 指定舰队编号, 如果为 None 则使用计划中的参数

            plan_path: 绝对路径 / 以 PLAN_ROOT 为根的相对路径

            fleet: 舰队成员, ["", "1号位", "2号位", ...], 如果为 None 则全部不变, 为 "" 则该位置无舰船, 为 -1 则不覆盖 yaml 文件中的参数

        Raises:
            BaseException: _description_
        """
        super().__init__(timer)
        # 从配置文件加载计划
        plan_path = (
            plan_path
            if os.path.isabs(plan_path)
            else self.timer.plan_tree['normal_fight'][plan_path]
        )
        plan_args = yaml_to_dict(plan_path)
        if fleet_id is not None:
            plan_args['fleet_id'] = fleet_id  # 舰队编号
        if fleet != -1:
            plan_args['fleet'] = fleet

        self.config = FightConfig.from_dict(plan_args)

        # 加载节点配置
        self.nodes: dict[str, DecisionBlock] = {}
        for node_name in self.config.selected_nodes:
            node_args = copy.deepcopy(plan_args.get('node_defaults', {}))
            if (
                'node_args' in plan_args
                and plan_args['node_args'] is not None
                and node_name in plan_args['node_args']
            ):
                node_args = recursive_dict_update(
                    node_args,
                    plan_args['node_args'][node_name],
                )
            self.nodes[node_name] = DecisionBlock(timer, node_args)
        self._load_fight_info()

    def _load_fight_info(self) -> None:
        # 信息记录器
        self.info = NormalFightInfo(self.timer, self.config.chapter, self.config.map)
        self.info.load_point_positions(os.path.join(MAP_ROOT, 'normal'))

    def _go_map_page(self) -> None:
        """活动多点战斗必须重写该模块"""
        """ 进入选择战斗地图的页面 """
        """ 这个模块负责的工作在战斗结束后如果需要进行重复战斗, 则不会进行 """
        self.timer.goto_game_page('map_page')

    def _go_fight_prepare_page(self) -> None:
        """活动多点战斗必须重写该模块"""
        """(从当前战斗结束后跳转到的页面)进入准备战斗的页面"""
        if not self.timer.ui.is_normal_fight_prepare:
            self.timer.goto_game_page('map_page')
        self.timer.goto_game_page('fight_prepare_page')
        self.timer.ui.is_normal_fight_prepare = True

    def _enter_fight(self, *args, **kwargs):
        """
        从任意界面进入战斗.

        :return: 进入战斗状态信息，包括['success', 'dock is full'].
        """
        if self.config.chapter != self.timer.port.chapter or self.config.map != self.timer.port.map:
            self._go_map_page()
            self._change_fight_map(self.config.chapter, self.config.map)
            self.timer.port.chapter = self.config.chapter
            self.timer.port.map = self.config.map
        self.timer.wait_images(
            [self.info.map_image, IMG.identify_images['fight_prepare_page']],
            timeout=3,
        )
        self._go_fight_prepare_page()
        move_team(self.timer, self.config.fleet_id)
        if (
            self.config.fleet is not None
            and self.timer.port.fleet[self.config.fleet_id] != self.config.fleet
        ):
            change_ships(self.timer, self.config.fleet_id, self.config.fleet)
            self.timer.port.fleet[self.config.fleet_id] = self.config.fleet[:]

        self.info.ship_stats = detect_ship_stats(self.timer)
        quick_repair(self.timer, self.config.repair_mode, self.info.ship_stats)

        return start_march(self.timer)

    def _make_decision(
        self,
        *args,
        **kwargs,
    ):
        state = self.update_state() if 'skip_update' not in kwargs else self.info.state
        if state == ConditionFlag.SL:
            return ConditionFlag.SL

        # 进行 MapLevel 的决策
        if state == 'map_page':
            self.info.fight_history.add_event(
                '自动回港',
                {'position': self.info.node, 'info': '正常'},
            )
            return ConditionFlag.FIGHT_END

        if state == 'fight_condition':
            value = self.config.fight_condition
            self.timer.relative_click(*value.relative_click_position)
            self.info.last_action = value
            self.info.fight_history.add_event(
                '战况选择',
                {'position': self.info.node},
                value,
            )
            return ConditionFlag.FIGHT_CONTINUE

        # 不在白名单之内 SL
        if self.info.node not in self.config.selected_nodes:
            # 可以撤退点撤退
            if state == 'spot_enemy_success':
                self.timer.click(677, 492, delay=0)
                self.info.last_action = 'retreat'
                self.info.fight_history.add_event(
                    '索敌成功',
                    {'position': self.info.node, 'enemies': '不在预设点, 不进行索敌'},
                    '撤退',
                )
                return ConditionFlag.FIGHT_END
            # 不能撤退退游戏
            if state == 'formation':
                self.info.fight_history.add_event(
                    '阵型选择',
                    {'position': self.info.node},
                    'SL',
                )
                return ConditionFlag.SL
            if state == 'fight_period':
                self.info.fight_history.add_event(
                    '进入战斗',
                    {'position': self.info.node},
                    'SL',
                )
                return ConditionFlag.SL

        elif state == 'proceed':
            is_proceed = self.nodes[self.info.node].config.proceed and check_blood(
                self.info.ship_stats,
                self.nodes[self.info.node].config.proceed_stop,
            )

            if is_proceed:
                self.timer.click(325, 350)
                self.info.last_action = 'yes'
                self.info.fight_history.add_event(
                    '继续前进',
                    {'position': self.info.node, 'ship_stats': self.info.ship_stats},
                    '前进',
                )
                return ConditionFlag.FIGHT_CONTINUE
            self.timer.click(615, 350)
            self.info.last_action = 'no'
            self.info.fight_history.add_event(
                '继续前进',
                {'position': self.info.node, 'ship_stats': self.info.ship_stats},
                '回港',
            )
            return ConditionFlag.FIGHT_END

        elif state == 'flagship_severe_damage':
            self.timer.click_image(IMG.fight_image[4], must_click=True, delay=0.25)
            self.info.fight_history.add_event(
                '自动回港',
                {'position': self.info.node, 'info': '旗舰大破'},
            )
            return 'fight end'

        # 进行通用 NodeLevel 决策
        action, fight_stage = self.nodes[self.info.node].make_decision(
            state,
            self.info.last_state,
            self.info.last_action,
            self.info,
        )
        self.info.last_action = action

        return fight_stage

    # ======================== Functions ========================
    def _get_chapter(self) -> int:
        """在出征界面获取当前章节(远征界面也可获取)

        Raises:
            TimeoutError: 无法获取当前章节

        Returns:
            int: 当前章节
        """
        for try_times in range(5):
            time.sleep(0.15 * 2**try_times)
            self.timer.update_screen()
            for i in range(1, len(IMG.chapter_image)):
                if self.timer.image_exist(IMG.chapter_image[i], 0):
                    return i

        raise TimeoutError("can't verify chapter")

    def _move_chapter(self, target_chapter, now_chapter=None):
        """移动地图章节到 target_chapter
        含错误检查

        Args:
            target_chapter (int): 目标
            now_chapter (_type_, optional): 现在的章节. Defaults to None.
        Raise:
            ImageNotFoundErr:如果没有找到章节标志或地图界面标志
        """
        if not self.timer.identify_page('map_page'):
            raise ImageNotFoundErr("not on page 'map_page' now")

        if now_chapter == target_chapter:
            return
        try:
            if now_chapter is None:
                now_chapter = self._get_chapter()
            if self.timer.config.show_chapter_info:
                self.timer.logger.debug('NowChapter:', now_chapter)
            if now_chapter > target_chapter:
                if now_chapter - target_chapter >= 3:
                    now_chapter -= 3
                    self.timer.click(95, 97, delay=0)

                elif now_chapter - target_chapter == 2:
                    now_chapter -= 2
                    self.timer.click(95, 170, delay=0)

                elif now_chapter - target_chapter == 1:
                    now_chapter -= 1
                    self.timer.click(95, 229, delay=0)

            else:
                if now_chapter - target_chapter <= -3:
                    now_chapter += 3
                    self.timer.click(95, 485, delay=0)

                elif now_chapter - target_chapter == -2:
                    now_chapter += 2
                    self.timer.click(95, 416, delay=0)

                elif now_chapter - target_chapter == -1:
                    now_chapter += 1
                    self.timer.click(95, 366, delay=0)

            if not self.timer.wait_image(IMG.chapter_image[now_chapter]):
                raise ImageNotFoundErr(
                    "after 'move chapter' operation but the chapter do not move",
                )

            time.sleep(0.15)
            self._move_chapter(target_chapter, now_chapter)
        except:

            self.logger.warning(
                f'切换章节失败 target_chapter: {target_chapter}   now: {now_chapter}',
            )
            if self.timer.process_bad_network('move_chapter'):
                self._move_chapter(target_chapter)
            else:
                raise ImageNotFoundErr("unknown reason can't find chapter image")

    def _verify_map(self, target_map, chapter, need_screen_shot=True, timeout=0):
        if timeout == 0:
            return self.timer.image_exist(
                IMG.normal_map_image[f'{chapter!s}-'][target_map - 1],
                need_screen_shot,
                confidence=0.85,
            )
        return self.timer.wait_image(
            IMG.normal_map_image[f'{chapter!s}-'][target_map - 1],
            confidence=0.85,
            timeout=timeout,
            gap=0.03,
        )

    def _get_map(self, chapter, need_screen_shot=True) -> int:
        """出征界面获取当前显示地图节点编号
        例如在出征界面显示的地图 2-5,则返回 5

        Returns:
            int: 节点编号
        """
        for try_times in range(5):
            time.sleep(0.15 * 2**try_times)
            if need_screen_shot:
                self.timer.update_screen()

            # 通过+-1来匹配0，1开始的序号
            for map in range(1, MAP_NUM[chapter - 1] + 1):
                if self._verify_map(map, chapter, need_screen_shot=False):
                    return map

        raise TimeoutError("can't verify map")

    def _move_map(self, target_map, chapter):
        """改变地图节点,不检查是否有该节点
        含网络错误检查
        Args:
            target_map (_type_): 目标节点

        """
        if not self.timer.identify_page('map_page'):
            raise ImageNotFoundErr("not on page 'map_page' now")

        now_map = self._get_map(chapter)
        try:
            if self.timer.config.show_chapter_info:
                self.timer.logger.debug('now_map:', now_map)
            if target_map > now_map:
                for i in range(target_map - now_map):
                    self.timer.swipe(715, 147, 552, 147, duration=0.25)
                    if not self._verify_map(now_map + (i + 1), chapter, timeout=4):
                        raise ImageNotFoundErr(
                            "after 'move map' operation but the chapter do not move",
                        )
                    time.sleep(0.15)
            else:
                for i in range(now_map - target_map):
                    self.timer.swipe(552, 147, 715, 147, duration=0.25)
                    if not self._verify_map(now_map - (i + 1), chapter, timeout=4):
                        raise ImageNotFoundErr(
                            "after 'move map' operation but the chapter do not move",
                        )
                    time.sleep(0.15)
        except:
            self.logger.error(f'切换地图失败 target_map: {target_map}   now: {now_map}')
            if self.timer.process_bad_network():
                self._move_map(target_map, chapter)
            else:
                raise ImageNotFoundErr(
                    "unknown reason can't find number image" + str(target_map),
                )

    def _change_fight_map(self, chapter, map):
        """活动多点战斗必须重写该模块"""
        """ 这个模块负责的工作在战斗结束后如果需要进行重复战斗, 则不会进行 """
        """在地图界面改变战斗地图(通常是为了出征)
        可以处理网络错误
        Args:
            chapter (int): 目标章节
            map (int): 目标节点

        Raises:
            ValueError: 不在地图界面
            ValueError: 不存在的节点
        """
        if self.timer.now_page.name != 'map_page':
            raise ValueError(
                "can't change fight map at page:",
                self.timer.now_page.name,
            )
        if map - 1 not in range(MAP_NUM[chapter - 1]):
            raise ValueError(
                f'map {map!s} not in the list of chapter {chapter!s}',
            )

        self._move_chapter(chapter)
        self._move_map(map, chapter)
        self.info.chapter = self.config.chapter
        self.info.map = self.config.map
