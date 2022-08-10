import copy
import time

import yaml
from api import ClickImage, GetImagePosition, ImagesExist, UpdateScreen, click
from constants import FIGHT_CONDITIONS_POSITON, FightImage, identify_images
from fight import SL
from game import (ConfirmOperation, DetectShipStatu, GetEnemyCondition,
                  MoveTeam, QuickRepair, UpdateShipPoint, UpdateShipPosition,
                  change_fight_map, goto_game_page, identify_page,
                  process_bad_network)
from supports import ImageNotFoundErr, SymbolImage, Timer
from utils.io import recursive_dict_update

from fight_dh import NodeLevelDecisionBlock, Ship


class NormalFightInfo():
    """ 存储战斗中需要用到的所有状态信息 """

    def __init__(self, timer: Timer) -> None:

        self.timer = timer

        # 战斗流程的有向图建模，在不同动作有不同后继时才记录动作
        self.successor_states = {
            "proceed": {
                "yes": ["fight_condition", "spot_enemy_success", "formation"],
                "no": ["map_page"]
            },
            "fight_condition": ["spot_enemy_success", "formation"],
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
            "get_ship": ["lock_new_ship", "proceed", "map_page", "flagship_severe_damage"],  # 捞到舰船
            "lock_new_ship": ["proceed", "map_page", "flagship_severe_damage"],  # 锁定新船
            "flagship_severe_damage": ["map_page"],
        }

        # 所需用到的图片模板。格式位 [模板，等待时间]
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
            "lock_new_ship": [FightImage[1], 3],  # TODO: 这里只是占位符，需要实现”新船锁定“页面的图片模板
            "flagship_severe_damage": [FightImage[4], 5],
            "map_page": [identify_images["map_page"][0], 5]
        }

        # 初始化战斗信息
        self.reset()

    def reset(self):
        self.last_state = "proceed"
        self.last_action = "yes"
        self.state = "proceed"  # 初始状态等同于 proceed选择yes
        self.last_node = ""
        self.node = ""  # 初始无节点信息

        # TODO: 舰船信息，暂时不用
        self.ally_ships = [Ship() for _ in range(6)]  # 我方舰船状态
        self.enemy_ships = [Ship() for _ in range(6)]  # 敌方舰船状态

    def update_state(self):

        # 保存上一个状态
        self.last_state = self.state
        self.last_node = self.node

        # 计算当前可能的状态
        possible_states = copy.deepcopy(self.successor_states[self.state])
        if isinstance(possible_states, dict):
            possible_states = possible_states[self.last_action]
        modified_timeout = [-1 for _ in possible_states]    # 某些状态需要修改等待时间
        for i, state in enumerate(possible_states):
            if isinstance(state, list):
                state, timeout = state
                possible_states[i] = state
                modified_timeout[i] = timeout
        print("waiting:", possible_states, end="  ")
        images = [self.state2image[state][0] for state in possible_states]
        timeout = [self.state2image[state][1] for state in possible_states]
        timeout = [timeout[i] if modified_timeout[i] == -1 else modified_timeout[i] for i in range(len(timeout))]
        timeout = max(timeout)

        # 等待其中一种出现
        need_click = self.state in ["proceed", "fight_condition"]
        locate_yellow_ship = self.state in ["proceed", "fight_condition"]
        may_need_confirm = self.state in ["proceed", "fight_condition", "result"]

        fun_start_time = time.time()
        while time.time() - fun_start_time <= timeout:
            # 点击加速
            if need_click:
                p = click(self.timer, 380, 520, delay=0, enable_subprocess=True, print=0, no_log=True)

            UpdateScreen(self.timer)

            # 获取所到节点
            if locate_yellow_ship:
                UpdateShipPosition(self.timer)
                UpdateShipPoint(self.timer)
                self.node = self.timer.ship_point
            # 点确定
            if may_need_confirm:
                ConfirmOperation(self.timer, delay=0)

            # 尝试匹配
            ret = [GetImagePosition(self.timer, image, 0, .8, no_log=True) is not None for image in images]
            if any(ret):
                self.state = possible_states[ret.index(True)]
                print("matched:", self.state)
                # 在某些State下可以记录额外信息
                match self.state:
                    case "spot_enemy_success":
                        GetEnemyCondition(self.timer, 'fight')
                    case "result":
                        DetectShipStatu(self.timer, 'sumup')
                        self.timer.fight_result.detect_result()

                return self.state

            if need_click:
                p.join()

        print("\n===================================================")
        print(f"state: {self.state} last_action: {self.last_action}")
        raise ImageNotFoundErr()


# TODO: 1）资源点 2）之后把一部分可复用的逻辑放到NodeLevelDecisionBlock中，供战役、决战、演习共享使用
class NormalFight():
    """" 常规战斗的决策模块 """

    def __init__(self, timer: Timer, plan_path, default_path) -> None:
        # 把timer引用作为内置对象，减少函数调用的时候所需传入的参数
        self.timer = timer

        # 构建MapLevel设置
        default_args = yaml.load(open(default_path, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
        plan_args = yaml.load(open(plan_path, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
        args = recursive_dict_update(default_args, plan_args, skip=['node_plans'])
        self.__dict__.update(args)

        # 构建NodeLevel设置
        self.nodes = {}
        for node_name in self.selected_nodes:
            node_args = copy.deepcopy(self.node_defaults)
            node_args = recursive_dict_update(node_args, plan_args['node_plans'][node_name])
            self.nodes[node_name] = NodeLevelDecisionBlock(node_args)

        # 构建信息存储结构
        self.FI = NormalFightInfo(self.timer)

    def run(self) -> None:
        """ 主函数，负责一次完整的战斗. """

        # 战斗前逻辑
        while ret := self._enter_fight() != "success":
            if ret == "dock is full":
                pass  # TODO：加入分解逻辑

        # 战斗中逻辑
        self.FI.reset()  # 初始化战斗信息
        while True:  # TODO：可能需要加入异常处理
            self.FI.update_state()
            ret = self._make_decision()

            if ret == "fight continue":
                continue
            elif ret == "need SL":
                SL(self.timer)  # TODO：SL之后该干嘛
                self.run()
            elif ret == "fight end":
                self.timer.set_page("map_page")
                break

    def _enter_fight(self) -> str:
        """
        从任意界面进入战斗.

        :return: 进入战斗状态信息，包括['success', 'dock is full].
        """

        goto_game_page(self.timer, 'map_page')
        change_fight_map(self.timer, self.chapter, self.map)
        goto_game_page(self.timer, 'fight_prepare_page')
        MoveTeam(self.timer, self.fleet_id)  # TODO: 支持按列表修改舰船
        QuickRepair(self.timer)  # TODO：支持复杂修理逻辑，暂时用快修，修中破
        click(self.timer, 900, 500, 1, delay=0)  # 点击：开始出征

        # 异常处理
        start_time = time.time()
        while identify_page(self.timer, 'fight_prepare_page'):
            UpdateScreen(self.timer)  # 获取当前屏幕
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

    def _make_decision(self):

        node = self.nodes[self.FI.node]
        state = self.FI.state

        match state:
            case "map_page":
                return "fight end"

            case "fight_period":
                return "fight continue"

            case "fight_condition":
                value = self.fight_condition
                click(self.timer, *FIGHT_CONDITIONS_POSITON[value])
                self.FI.last_action = value
                return "fight continue"

            case "spot_enemy_success":
                if self.FI.node not in self.selected_nodes:  # 不在白名单之内直接SL
                    click(self.timer, 677, 492, delay=0)
                    self.FI.last_action = "retreat"
                    return "fight end"
                elif node.detour:  # 由Node指定是否要迂回
                    click(self.timer, 540, 500, delay=0)
                    self.FI.last_action = "detour"
                    return "fight continue"
                else:
                    click(self.timer, 855, 501, delay=0)
                    self.FI.last_action = "fight"
                    return "fight continue"

            case "formation":
                spot_enemy = self.FI.last_state == "spot_enemy_success"
                value = node.formation
                if spot_enemy:
                    # 功能：迂回失败SL
                    if node.SL_when_detour_fails and self.FI.last_action == "detour":
                        return "need SL"
                else:
                    # 功能：索敌失败SL
                    if node.SL_when_spot_enemy_fails:
                        return "need SL"
                    # 功能：索敌失败采用不同阵型
                    if node.formation_when_spot_enemy_fails[0]:
                        value = node.formation_when_spot_enemy_fails[1]

                click(self.timer, 573, value * 100 - 20, delay=2)
                self.FI.last_action = value
                return "fight continue"

            case "night":
                is_night = node.night
                if is_night:
                    click(self.timer, 325, 350, delay=2)
                    self.FI.last_action = "yes"
                    return "fight continue"
                else:
                    click(self.timer, 615, 350, delay=2)
                    self.FI.last_action = "no"
                    return "fight continue"

            case "result":
                time.sleep(1.5)
                click(self.timer, 900, 500, 2, 0.16)    # TODO：需要获取经验则只点一下就行
                return "fight continue"

            case "get_ship":
                click(self.timer, 900, 500, 1, 0.25)
                return "fight continue"

            case "lock_ship":
                pass    # TODO: 锁定舰船

            case "proceed":
                is_proceed = node.proceed
                if is_proceed:
                    click(self.timer, 325, 350)
                    self.FI.last_action = "yes"
                    return "fight continue"
                else:
                    click(self.timer, 615, 350)
                    self.FI.last_action = "no"
                    return "fight end"

            case "flagship_severe_damage":
                ClickImage(self.timer, FightImage[4], must_click=True, delay=0.25)
                return 'fight end'

            # 运行到这里说明出错了
            case _:
                print("============Unknown State=============")
                print(state)
                raise BaseException()
