import copy
import os
import time

from AutoWSGR.constants.custom_expections import ImageNotFoundErr
from AutoWSGR.constants.data_roots import MAP_ROOT, PLAN_ROOT
from AutoWSGR.constants.other_constants import INFO1, INFO2, INFO3, NORMAL_MAP_EVERY_CHAPTER
from AutoWSGR.constants.image_templates import IMG
from AutoWSGR.constants.positions import FIGHT_CONDITIONS_POSITON
from AutoWSGR.constants.settings import S
from AutoWSGR.controller.run_timer import Timer
from AutoWSGR.game.game_operation import MoveTeam, QuickRepair
from AutoWSGR.game.get_game_info import DetectShipStatu, GetEnemyCondition
from AutoWSGR.utils.debug import print_err, print_war
from AutoWSGR.utils.io import recursive_dict_update, yaml_to_dict
from AutoWSGR.utils.logger import logit
from AutoWSGR.utils.math_functions import CalcDis

from .common import (FightInfo, FightPlan, NodeLevelDecisionBlock, StageRecorder, start_march)

"""
常规战决策模块/地图战斗用模板
"""

MAP_LIST = [None, range(1, 6), range(1, 7), range(1, 5), range(1, 5),
            range(1, 6), range(1, 5), range(1, 6), range(1, 6), range(1, 2)]


class NormalFightInfo(FightInfo):
    # ==================== Unified Interface ====================
    def __init__(self, timer: Timer, chapter_id, map_id) -> None:
        super().__init__(timer)

        self.point_positions = None
        self.end_page = "map_page"
        self.map_image = IMG.identify_images["map_page"][0]
        self.chapter = chapter_id  # 章节名,战役为 'battle', 演习为 'exercise'
        self.map = map_id  # 节点名
        self.ship_position = (0, 0)
        self.node = "A"  # 常规地图战斗中,当前战斗点位的编号
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
            "result": ["proceed", "map_page", "get_ship", "flagship_severe_damage"],  # 两页战果
            "get_ship": ["proceed", "map_page", "flagship_severe_damage"],  # 捞到舰船
            "flagship_severe_damage": ["map_page"],
        }

        self.state2image = {
            "proceed": [IMG.fight_image[5], 5],
            "fight_condition": [IMG.fight_image[10], 15],
            "spot_enemy_success": [IMG.fight_image[2], 15],
            "formation": [IMG.fight_image[1], 15],
            "fight_period": [IMG.symbol_image[4], 3],
            "night": [IMG.fight_image[6], 120],
            "night_fight_period": [IMG.symbol_image[4], 3],
            "result": [IMG.fight_image[3], 60],
            "get_ship": [IMG.symbol_image[8], 5],
            "flagship_severe_damage": [IMG.fight_image[4], 5],
            "map_page": [self.map_image, 5]
        }

    def reset(self):
        self.last_state = "proceed"
        self.last_action = "yes"
        self.state = "proceed"  # 初始状态等同于 proceed选择yes

    def _before_match(self):
        # 点击加速
        if self.state in ["proceed", "fight_condition"]:
            self.timer.Android.click(380, 520, delay=0, enable_subprocess=True, print=0, no_log=True)

        self.timer.update_screen()

        # 在地图上走的过程中获取舰船位置
        if self.state in ["proceed"]:
            self._update_ship_position()
            self._update_ship_point()

        # 1. proceed: 资源点  2. get_ship: 锁定新船
        if self.state in ["proceed", "get_ship"]:
            self.timer.ConfirmOperation(delay=0)

    def _after_match(self):
        # 在某些State下可以记录额外信息
        if self.state == "spot_enemy_success":
            GetEnemyCondition(self.timer, 'fight')

        elif self.state == "result":
            DetectShipStatu(self.timer, 'sumup')
            self.fight_result.detect_result()

    # ======================== Functions ========================
    @logit(level=INFO1)
    def _update_ship_position(self):
        """在战斗移动界面(有一个黄色小船在地图上跑)更新黄色小船的位置
        """
        pos = self.timer.get_image_position(IMG.fight_image[7], 0, 0.8)
        if pos is None:
            pos = self.timer.get_image_position(IMG.fight_image[8], 0, 0.8)
        if pos is None:
            return
        self.ship_position = pos
        if S.SHOW_MAP_NODE:
            print(self.ship_position)

    def _update_ship_point(self):
        """更新黄色小船(战斗地图上那个)所在的点位 (1-1A 这种,'A' 就是点位)
        """

        self.node = "A"
        for i in range(26):
            ch = chr(ord('A') + i)
            if ch not in self.point_positions.keys():
                break
            if CalcDis(self.point_positions[ch], self.ship_position) < CalcDis(self.point_positions[self.node],
                                                                               self.ship_position):
                self.node = ch

        if S.SHOW_MAP_NODE:
            print(self.node)

    def load_point_positions(self, map_path):
        self.point_positions = yaml_to_dict(os.path.join(map_path, str(self.chapter) + "-" + str(self.map) + ".yaml"))


def _check_blood(blood, rule):
    """检查血量状态是否满足前进条件
        >>>check_blood([None, 1, 1, 1, 2, -1, -1], [2, 2, 2, -1, -1, -1])

        >>>True
    Args:
        blood (list): 1-based
        rule (list): 0-based
    """
    l = max(len(blood) - 1, len(rule))
    for i in range(l):
        if (blood[i + 1] == -1 or rule[i] == -1):
            continue
        if (blood[i + 1] >= rule[i]):
            return False
    return True


class NormalFightPlan(FightPlan):
    """" 常规战斗的决策模块 """

    def __init__(self, timer: Timer, plan_path, fleet_id=1):
        """初始化决策模块,可以重新指定默认参数,优先级更高

        Args:

        Raises:
            BaseException: _description_
        """
        super().__init__(timer)

        # 从配置文件加载计划
        default_args = yaml_to_dict(os.path.join(PLAN_ROOT, "default.yaml"))
        plan_defaults = default_args["normal_fight_defaults"]
        plan_defaults.update({"node_defaults": default_args["node_defaults"]})
        plan_args = yaml_to_dict(os.path.join(PLAN_ROOT, plan_path))
        args = recursive_dict_update(plan_defaults, plan_args, skip=['node_args'])
        self.__dict__.update(args)

        # 从参数加载计划
        self.fleet_id = fleet_id  # 舰队编号

        # 加载节点配置
        self.nodes = {}
        for node_name in self.selected_nodes:
            node_args = copy.deepcopy(self.node_defaults)
            if 'node_args' in plan_args and plan_args['node_args'] is not None and node_name in plan_args['node_args']:
                node_args = recursive_dict_update(node_args, plan_args['node_args'][node_name])
            self.nodes[node_name] = NodeLevelDecisionBlock(timer, node_args)

        # 信息记录器
        self.Info = NormalFightInfo(self.timer, self.chapter, self.map)
        self.Info.load_point_positions(os.path.join(MAP_ROOT, 'normal'))

    def go_map_page(self):
        """进入选择战斗地图的页面
        """
        self.timer.goto_game_page('map_page')

    def go_fight_prepare_page(self):
        """(从当前战斗结束后跳转到的页面)进入准备战斗的页面"""
        self.timer.goto_game_page('fight_prepare_page')

    def _enter_fight(self, same_work=False, *args, **kwargs):
        """
        从任意界面进入战斗.

        :return: 进入战斗状态信息，包括['success', 'dock is full].
        """
        if not same_work:
            self.go_map_page()
            self._change_fight_map(self.chapter, self.map)
        try:
            assert (self.timer.wait_image(self.Info.map_image) != False)
            self.go_fight_prepare_page()
            MoveTeam(self.timer, self.fleet_id)
            QuickRepair(self.timer, self.repair_mode)
        except AssertionError:
            if "process_err" in kwargs and kwargs["process_err"] == False:
                raise ImageNotFoundErr("进入战斗前置界面错误")
            print_war("进入战斗前置界面不正确")
            self.timer.process_bad_network()
            return self._enter_fight(process_err=False)

        return start_march(self.timer)

    def _make_decision(self):

        if S.SHOW_FIGHT_STAGE:
            print(self.fight_recorder.last_stage)
        self.Info.update_state()
        state = self.Info.state
        # 进行MapLevel的决策
        if state == "map_page":
            return "fight end"

        elif state == "fight_condition":
            value = self.fight_condition
            self.timer.Android.click(*FIGHT_CONDITIONS_POSITON[value])
            self.Info.last_action = value
            self.fight_recorder.append(StageRecorder(self.Info, self.timer))
            return "fight continue"

        elif state == "spot_enemy_success":
            if self.Info.node not in self.selected_nodes:  # 不在白名单之内直接SL
                self.timer.Android.click(677, 492, delay=0)
                self.Info.last_action = "retreat"
                self.fight_recorder.append(StageRecorder(self.Info, self.timer))
                return "fight end"

        elif state == "proceed":
            is_proceed = self.nodes[self.Info.node].proceed and \
                         _check_blood(self.timer.ship_status, self.nodes[self.Info.node].proceed_stop)

            if is_proceed:
                self.timer.Android.click(325, 350)
                self.Info.last_action = "yes"
                self.fight_recorder.append(StageRecorder(self.Info, self.timer, no_action=True))
                return "fight continue"
            else:
                self.timer.Android.click(615, 350)
                self.Info.last_action = "no"
                self.fight_recorder.append(StageRecorder(self.Info, self.timer, no_action=True))
                return "fight end"

        elif state == "flagship_severe_damage":
            self.timer.click_image(IMG.fight_image[4], must_click=True, delay=0.25)
            self.fight_recorder.append(StageRecorder(self.Info, self.timer, no_action=True))
            return 'fight end'

        # 进行通用NodeLevel决策

        action, fight_stage = self.nodes[self.Info.node].make_decision(state, self.Info.last_state,
                                                                       self.Info.last_action)
        self.Info.last_action = action
        self.fight_recorder.append(StageRecorder(self.Info, self.timer))
        return fight_stage

    # ======================== Functions ========================
    @logit(level=INFO1)
    def _get_chapter(self):
        """在出征界面获取当前章节(远征界面也可获取)

        Raises:
            TimeoutError: 无法获取当前章节

        Returns:
            int: 当前章节
        """
        for try_times in range(5):
            time.sleep(0.15 * 2 ** try_times)
            self.timer.update_screen()
            for i in range(1, len(IMG.chapter_image)):
                if self.timer.image_exist(IMG.chapter_image[i], 0):
                    return i
        raise TimeoutError("can't verify chapter")

    def vertify_node(self, target, chapter, need_screen_shot=True, timeout=0):
        if timeout == 0:
            return self.timer.image_exist(IMG.normal_map_image[f"{str(chapter)}-{str(target)}"], need_screen_shot, confidence=0.85)
        return self.timer.wait_image(IMG.normal_map_image[f"{str(chapter)}-{str(target)}"], confidence=0.85, timeout=timeout, gap=0.03)
        
    @logit(level=INFO1)
    def _get_node(self, chapter, need_screen_shot=True):
        """出征界面获取当前显示地图节点编号
        例如在出征界面显示的地图 2-5,则返回 5
        
        Returns:
            int: 节点编号
        """
        for try_times in range(5):
            time.sleep(.15 * 2 ** try_times)
            if (need_screen_shot):
                self.timer.update_screen()
            for i in range(1, len(NORMAL_MAP_EVERY_CHAPTER[chapter]) + 1):
                if (self.vertify_node(i, chapter, False)):
                    return i
        raise TimeoutError("can't vertify map")

    @logit(level=INFO2)
    def _move_chapter(self, target, chapter_now=None):
        """移动地图章节到 target
        含错误检查

        Args:
            target (int): 目标
            chapter_now (_type_, optional): 现在的章节. Defaults to None.
        Raise:
            ImageNotFoundErr:如果没有找到章节标志或地图界面标志
        """
        if not self.timer.identify_page('map_page'):
            raise ImageNotFoundErr("not on page 'map_page' now")

        if chapter_now == target:
            return
        try:
            if chapter_now is None:
                chapter_now = self._get_chapter()
            if S.SHOW_CHAPTER_INFO:
                print("NowChapter:", chapter_now)
            if chapter_now > target:
                if chapter_now - target >= 3:
                    chapter_now -= 3
                    self.timer.Android.click(95, 97, delay=0)

                elif chapter_now - target == 2:
                    chapter_now -= 2
                    self.timer.Android.click(95, 170, delay=0)

                elif chapter_now - target == 1:
                    chapter_now -= 1
                    self.timer.Android.click(95, 229, delay=0)

            else:
                if chapter_now - target <= -3:
                    chapter_now += 3
                    self.timer.Android.click(95, 485, delay=0)

                elif chapter_now - target == -2:
                    chapter_now += 2
                    self.timer.Android.click(95, 416, delay=0)

                elif chapter_now - target == -1:
                    chapter_now += 1
                    self.timer.Android.click(95, 366, delay=0)

            if not self.timer.wait_image(IMG.chapter_image[chapter_now]):
                raise ImageNotFoundErr("after movechapter operation but the chapter do not move")

            time.sleep(0.15)
            self._move_chapter(target, chapter_now)
        except:
            print_err("切换章节失败", ex_info="时间戳:" + str(time.time()))
            if self.timer.process_bad_network('move_chapter'):
                self._move_chapter(target)
            else:
                raise ImageNotFoundErr("unknow reason can't find chapter image")

    @logit(level=INFO2)
    def _move_node(self, target, chapter):
        """改变地图节点,不检查是否有该节点
        含网络错误检查
        Args:
            target (_type_): 目标节点

        """
        if not self.timer.identify_page('map_page'):
            raise ImageNotFoundErr("not on page 'map_page' now")

        NowNode = self._get_node(chapter)
        try:
            if S.SHOW_CHAPTER_INFO:
                print("NowNode:", NowNode)
            if target > NowNode:
                for i in range(1, target - NowNode + 1):
                    self.timer.Android.swipe(715, 147, 552, 147, duration=0.25)
                    if (not self.vertify_node(NowNode + i, chapter, timeout=4)):
                        raise ImageNotFoundErr("after movenode operation but the chapter do not move")
                    time.sleep(0.15)
            else:
                for i in range(1, NowNode - target + 1):
                    self.timer.Android.swipe(552, 147, 715, 147, duration=0.25)
                    if (not self.vertify_node(NowNode - i, chapter, timeout=4)):
                        raise ImageNotFoundErr("after movecnode operation but the chapter do not move")
                    time.sleep(0.15)
        except:
            print_err("切换地图失败", "时间戳:" + str(time.time()))
            if self.timer.process_bad_network():
                self._move_node(target, chapter)
            else:
                raise ImageNotFoundErr("unknown reason can't find number image" + str(target))

    @logit(level=INFO3)
    def _change_fight_map(self, chapter_id, map_id):
        """在地图界面改变战斗地图(通常是为了出征)
        可以处理网络错误
        Args:
            chapter_id (int): 目标章节
            map_id (int): 目标节点

        Raises:
            ValueError: 不在地图界面
            ValueError: 不存在的节点
        """
        if self.timer.now_page.name != 'map_page':
            raise ValueError("can't _change_fight_map at page:", self.timer.now_page.name)
        if map not in MAP_LIST[chapter_id]:
            raise ValueError(f"map {str(map)} not in the list of chapter {str(chapter_id)}")

        self._move_chapter(chapter_id)
        self._move_node(map, chapter_id)
        self.Info.chapter = self.chapter
        self.Info.map = self.map
