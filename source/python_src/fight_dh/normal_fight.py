import copy
import time

import yaml
from api import (ClickImage, GetImagePosition, ImagesExist, UpdateScreen,
                 WaitImage, WaitImages, click)
from constants import FIGHT_CONDITIONS_POSITON, FightImage
from fight import SL
from game import (ConfirmOperation, DetectShipStatu, MoveTeam, QuickRepair,
                  UpdateShipPoint, UpdateShipPosition, change_fight_map,
                  goto_game_page, identify_page,
                  process_bad_network)
from constants import identify_images
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
                "yes": ["fight_condition", "retreat_or_fight", "formation"],
                "no": ["map_page"]
            },
            "fight_condition": ["retreat_or_fight", "formation"],
            "retreat_or_fight": {
                "yes": ["formation"],
                "no": ["map_page"]
            },
            "formation": ["night", "result"],
            "night": ["result"],
            "result": ["proceed", "map_page"],
        }

        # 所需用到的图片模板。格式位 [模板，精度，等待时间]
        self.state2image = {
            "proceed": [FightImage[5], .85, 5],
            "fight_condition": [FightImage[10], .85, 15],
            "retreat_or_fight": [FightImage[2], .8, 15],
            "formation": [FightImage[1], .8, 15],
            "night": [FightImage[6], .85, 120],
            "result": [FightImage[3], .85, 60],
            "map_page": [identify_images["map_page"][0], .85, 5]
        }

        # 初始化战斗信息
        self.reset()

    def reset(self):
        self.state = "proceed"  # 初始状态等同于 proceed选择yes
        self.last_action = "yes"
        self.node = ""  # 初始无节点信息

        # TODO: 舰船信息，暂时不用
        self.ally_ships = [Ship() for _ in range(6)]  # 我方舰船状态
        self.enemy_ships = [Ship() for _ in range(6)]  # 敌方舰船状态

    def update_state(self):

        # 计算当前可能的状态
        possible_states = self.successor_states[self.state]
        if "yes" in possible_states:
            possible_states = possible_states[self.last_action]
        images = [self.state2image[state][0] for state in possible_states]
        confidence = min(self.state2image[state][1] for state in possible_states)
        timeout = max(self.state2image[state][2] for state in possible_states)

        # 等待其中一种出现
        need_click = self.state in ["proceed", "fight_condition"]
        locate_yellow_ship = self.state in ["proceed", "fight_condition"]
        may_need_confirm = self.state in ["proceed", "fight_condition", "result"]
        
        fun_start_time = time.time()
        while time.time() - fun_start_time <= timeout:
            # print(self.state, possible_states)
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
            ret = [GetImagePosition(self.timer, image, 0, confidence, no_log=True) is not None for image in images]
            if any(ret):
                self.state = possible_states[ret.index(True)]
                # TODO：根据匹配到的state，可在此记录额外信息
                return

            if need_click:
                p.join()

        raise TimeoutError('unknown error')


# TODO: 1）资源点 2）迂回 3）之后把一部分可复用的逻辑放到NodeLevelDecisionBlock中，供战役、决战、演习共享使用
class NormalFight():
    """" 常规战斗的决策模块 """

    def __init__(self, timer: Timer, plan_path, defaults=None) -> None:
        # 将该模块作为全局默认值
        if defaults is None:
            self.args = yaml.load(open(plan_path, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
        else:
            # 把timer引用作为内置对象，减少函数调用的时候所需传入的参数
            self.timer = timer

            # 构建MapLevel设置
            self.args = copy.deepcopy(defaults.args)
            new_args = yaml.load(open(plan_path, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
            self.args = recursive_dict_update(self.args, new_args, skip=['node_plans'])

            # 构建NodeLevel设置
            self.nodes = {}
            for node_name in self.args['selected_nodes']:
                node_args = copy.deepcopy(self.args['node_defaults'])
                node_args = recursive_dict_update(node_args, new_args['node_plans'][node_name])
                self.nodes[node_name] = NodeLevelDecisionBlock(node_args)

            # 构建信息存储结构
            self.FI = NormalFightInfo(self.timer)

    def run(self):
        """ 主函数，负责一次完整的战斗. """

        # 战斗前逻辑
        while ret := self._enter_fight() != "success":
            if ret == "dock is full":
                pass  # TODO：加入分解逻辑

        # 战斗中逻辑
        self.FI.reset()  # 初始化战斗信息
        while True:  # TODO：可能需要加入异常处理
            self.FI.update_state()
            ret = self._make_decision(self.FI.state)

            if ret == "fight continue":
                continue
            elif ret == "need SL":  # TODO：SL之后该干嘛
                SL(self.timer)
            elif ret == "fight end":
                self.timer.set_page("map_page")
                break

    def _enter_fight(self) -> str:
        """
        从任意界面进入战斗.

        :return: 进入战斗状态信息，包括['success', 'dock is full].
        """

        goto_game_page(self.timer, 'map_page')
        change_fight_map(self.timer, self.args["chapter"], self.args["map"])
        goto_game_page(self.timer, 'fight_prepare_page')
        MoveTeam(self.timer, self.args["fleet_id"])  # TODO: 支持按列表修改舰船
        QuickRepair(self.timer)  # TODO：支持复杂修理逻辑，暂时修中破
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

    def _make_decision(self, state):

        if state == "map_page":
            return "fight end"

        elif state == "fight_condition":
            value = self.args["fight_condition"]
            if WaitImage(self.timer, FightImage[10]):
                click(self.timer, *FIGHT_CONDITIONS_POSITON[value])
                return "fight continue"
            else:
                raise ImageNotFoundErr("no fight condition options")

        elif state == "retreat_or_fight":
            is_fight = self.FI.node in self.args['selected_nodes']  # 不在白名单之内直接SL
            is_fight = is_fight and not self.nodes[self.FI.node].SL
            # TODO: 1）还没写迂回 2）后续可加入其他更复杂的SL判断逻辑
            if is_fight:
                click(self.timer, 855, 501, delay=0)
                if WaitImages(self.timer, [FightImage[1], SymbolImage[4]], .8) is not None:
                    return "fight continue"
            else:
                click(self.timer, 677, 492, delay=0)
                return "fight end"

        elif state == "formation":
            value = self.nodes[self.FI.node].formation
            click(self.timer, 573, value * 100 - 20, delay=2)
            if WaitImage(self.timer, SymbolImage[4]):
                return "fight continue"

        elif state == "night":
            is_night = self.nodes[self.FI.node].night
            # TODO：可以在此加入更多复杂的判断逻辑
            if is_night:
                click(self.timer, 325, 350, delay=2)
                if WaitImage(self.timer, FightImage[6], 0, .8):
                    return "fight continue"
            else:
                click(self.timer, 615, 350, delay=2)
                if WaitImage(self.timer, FightImage[3], confidence=0.85) == False:
                    return "fight continue"

        elif state == "result":
            return self._process_results()

        elif state == "proceed":
            is_proceed = self.nodes[self.FI.node].proceed
            # TODO：可以在此加入更多复杂的判断逻辑
            if is_proceed:
                click(self.timer, 325, 350)
                self.FI.last_action = "yes"
                return "fight continue"
            else:
                click(self.timer, 615, 350)
                self.FI.last_action = "no"
                return "fight end"

        # 运行到这里说明出错了
        else:
            print("=================================")
            print(state)
            raise BaseException()

    # TODO：暂时直接copy过来了，看看能不能改进
    def _process_results(self, end_page="map_page", gap=0.15, begin=True, try_times=0, *args, **kwargs):
        if try_times > 75:
            if process_bad_network(self.timer):
                try_times = 0
            else:
                raise TimeoutError("unknown error lead to fight_end timeout")
        kwargs['oil_check'] = True
        time.sleep(gap)

        # 点击继续部分
        if begin:
            time.sleep(1.5)
            DetectShipStatu(self.timer, 'sumup')
            self.timer.fight_result.detect_result()
            print(self.timer.fight_result)
            click(self.timer, 900, 500, 2, 0.16)
            if 'no_ship_get' not in kwargs and ImagesExist(self.timer, SymbolImage[8], need_screen_shot=0):
                click(self.timer, 900, 500, 1, 0.25)

        UpdateScreen(self.timer)
        if end_page is not None and identify_page(self.timer, end_page, 0):
            return 'fight end'
        if 'no_flagship_check' not in kwargs and ImagesExist(self.timer, FightImage[4], need_screen_shot=0):
            """旗舰大破"""
            ClickImage(self.timer, FightImage[4], must_click=True, delay=0.25)
            return 'fight end'
        if 'no_ship_get' not in kwargs and ImagesExist(self.timer, SymbolImage[8], need_screen_shot=0):
            click(self.timer, 900, 500, 1, 0.25)
        if 'no_proceed' not in kwargs and ImagesExist(self.timer, FightImage[5], need_screen_shot=0):
            return 'fight continue'

        return self._process_results(end_page, gap, False, try_times + 1, *args, **kwargs)
