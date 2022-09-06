import copy
import time
from abc import ABC, abstractmethod

from api.api_android import click
from api.api_image import GetImagePosition
from constants.other_constants import ALL_SHIP_TYPES, SAP
from fight.apis import SL
from supports.run_timer import ImageNotFoundErr, Timer


# TODO: 完成
class Ship():
    """ 用于表示一艘船的数据结构, 注意友方与敌方所独有的field """

    def __init__(self) -> None:
        # 友方与敌方通用
        self.name = ''  # 舰船名称
        self.ship_type = 0  # TODO: 舰船类型，用字面常量实现
        self.health = 0  # 舰船生命值
        self.ship_status = 0  # TODO：舰船状态，主要用于记录击沉、空位

        # 友方
        self.level = 0  # 舰船等级
        self.exp = 0  # 舰船经验值
        self.friendliness = 0  # 舰船好感度


class FightInfo(ABC):
    def __init__(self, timer: Timer) -> None:
        self.timer = timer
        self.successor_states = {}  # 战斗流程的有向图建模，在不同动作有不同后继时才记录动作
        self.state2image = {}  # 所需用到的图片模板。格式为 [模板，等待时间]
        self.last_state = ""
        self.last_action = ""
        self.state = ""

    def update_state(self):

        self.last_state = self.state

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
        fun_start_time = time.time()
        while time.time() - fun_start_time <= timeout:
            self._before_match()

            # 尝试匹配
            ret = [GetImagePosition(self.timer, image, 0, .8, no_log=True) is not None for image in images]
            if any(ret):
                self.state = possible_states[ret.index(True)]
                print("matched:", self.state)
                self._after_match()

                return self.state

        # 匹配不到时报错
        print("\n===================================================")
        print(f"state: {self.state} last_action: {self.last_action}")
        raise ImageNotFoundErr()

    @abstractmethod
    def reset(self):
        """ 需要记录与初始化的战斗信息 """
        pass

    @abstractmethod
    def _before_match(self):
        """ 每一轮尝试匹配状态前执行的操作 """
        pass

    @abstractmethod
    def _after_match(self):
        """ 匹配到状态后执行的操作 """
        pass


class FightPlan(ABC):
    def __init__(self, timer) -> None:
        # 把timer引用作为内置对象，减少函数调用的时候所需传入的参数
        self.timer = timer

    def run(self):
        """ 主函数，负责一次完整的战斗. """

        # 战斗前逻辑
        ret = self._enter_fight()
        if ret != "success":
            return ret

        # 战斗中逻辑
        self.Info.reset()  # 初始化战斗信息
        while True:
            ret = self._make_decision()
            if ret == "fight continue":
                continue
            elif ret == "need SL":
                SL(self.timer)
                return self.run()
            elif ret == "fight end":
                self.timer.set_page(self.Info.start_page)
                break

        return "success"

    @abstractmethod
    def _enter_fight(self) -> str:
        pass

    @abstractmethod
    def _make_decision(self) -> str:
        pass


class NodeLevelDecisionBlock():
    """ 地图上一个节点的决策模块 """

    def __init__(self, timer: Timer, args) -> None:

        self.timer = timer
        self.__dict__.update(args)

        # 用于根据规则设置阵型
        self.set_formation_by_rule = False
        self.formation_by_rule = 0

    def make_decision(self, state, last_state, last_action):
        if state in ["fight_period", "night_fight_period"]:
            return None, "fight continue"
        elif state == "spot_enemy_success":
            retreat = self.supply_ship_mode == 1 and self.timer.enemy_type_count[SAP] == 0
            detour = self.detour
            for rule in self.enemy_rules:
                condition, act = rule
                for ship_type in ALL_SHIP_TYPES:
                    condition = condition.replace(ship_type, f"self.timer.enemy_type_count[{ship_type}]")

                if eval(condition):
                    if act == "retreat":
                        retreat = True
                    elif act == "detour":
                        detour = True
                    elif isinstance(act, int):
                        self.set_formation_by_rule = True
                        self.formation_by_rule = act
            if retreat:
                click(self.timer, 677, 492, delay=0)
                return "retreat", "fight end"
            elif detour:
                click(self.timer, 540, 500, delay=0)
                return "detour", "fight continue"
            click(self.timer, 855, 501, delay=0)
            return "fight", "fight continue"
        elif state == "formation":
            spot_enemy = last_state == "spot_enemy_success"
            value = self.formation
            if spot_enemy:
                if self.SL_when_detour_fails and last_action == "detour":
                    return None, "need SL"
                if self.set_formation_by_rule:
                    value = self.formation_by_rule
                    self.set_formation_by_rule = False
            else:
                if self.SL_when_spot_enemy_fails:
                    return None, "need SL"
                if self.formation_when_spot_enemy_fails != False:
                    value = self.formation_when_spot_enemy_fails
            click(self.timer, 573, value * 100 - 20, delay=2)
            return value, "fight continue"
        elif state == "night":
            is_night = self.night
            if is_night:
                click(self.timer, 325, 350, delay=2)
                return "yes", "fight continue"
            else:
                click(self.timer, 615, 350, delay=2)
                return "no", "fight continue"
        elif state == "result":
            time.sleep(1.5)
            click(self.timer, 900, 500, 2, 0.16)
            return None, "fight continue"
        elif state == "get_ship":
            click(self.timer, 900, 500, 1, 0.25)
            return None, "fight continue"
        else:
            print("===========Unknown State==============")
            raise BaseException()
