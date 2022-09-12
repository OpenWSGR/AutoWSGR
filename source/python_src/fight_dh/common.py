import copy
import time
import constants.settings as S
from abc import ABC, abstractmethod

from constants.custom_expections import ImageNotFoundErr
from constants.image_templates import FightImage, FightResultImage
from constants.keypoint_info import BLOODLIST_POSITION
from constants.other_constants import ALL_SHIP_TYPES, INFO1, SAP
from game.game_operation import SL
from controller.run_timer import Timer, GetImagePosition, ImagesExist, WaitImages
from utils.logger import logit
from utils.math_functions import get_nearest
from utils import remove_0_value_from_dict


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


class FightResult():
    def __init__(self, timer: Timer):
        self.timer = timer
        self.result = 'D'
        self.mvp = 0
        self.experiences = [None, 0, 0, 0, 0, 0, 0]

    @logit(level=INFO1)
    def detect_result(self):
        mvp_pos = GetImagePosition(self.timer, FightImage[14])
        self.mvp = get_nearest((mvp_pos[0], mvp_pos[1] + 20), BLOODLIST_POSITION[1])
        self.result = WaitImages(self.timer, FightResultImage)
        if (ImagesExist(self.timer, FightResultImage['SS'])):
            self.result = 'SS'
        return self

    # TODO：获得经验
    def detect_experiences(self):
        pass

    def __str__(self):
        return "mvp:{mvp},result:{result}".format(mvp=str(self.mvp), result=str(self.result))

    def __lt__(self, other):    # <
        order = ["D", "C", "B", "A", "S", "SS"]
        if (isinstance(other, FightResult)):
            other = other.result

        order.index(self.result) < order.index(other)

    def __le__(self, other):    # <=
        order = ["D", "C", "B", "A", "S", "SS"]
        if (isinstance(other, FightResult)):
            other = other.result

        order.index(self.result) <= order.index(other)

    def __gt__(self, other):    # >
        return not (self <= other)

    def __ge__(self, other):    # >=
        return not (self < other)


class FightInfo(ABC):
    """ 存储战斗中需要用到的所有状态信息, 以及更新逻辑 """

    def __init__(self, timer: Timer) -> None:
        self.timer = timer
        self.successor_states = {}  # 战斗流程的有向图建模，在不同动作有不同后继时才记录动作
        self.state2image = {}  # 所需用到的图片模板。格式为 [模板，等待时间]
        self.last_state = ""
        self.last_action = ""
        self.state = ""
        self.fight_result = FightResult(self.timer)  # 战斗结果记录

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
        if(S.DEBUG):print("waiting:", possible_states, end="  ")
        images = [self.state2image[state][0] for state in possible_states]
        timeout = [self.state2image[state][1] for state in possible_states]
        timeout = [timeout[i] if modified_timeout[i] == -1 else modified_timeout[i] for i in range(len(timeout))]
        timeout = max(timeout)

        # 等待其中一种出现
        fun_start_time = time.time()
        while time.time() - fun_start_time <= timeout:
            self._before_match()

            # 尝试匹配
            ret = [ImagesExist(self.timer, image, 0, no_log=True) for image in images]
            if any(ret):
                self.state = possible_states[ret.index(True)]
                if(S.DEBUG):print("matched:", self.state)
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


class StageRecorder():
    def __str__(self):
        return f"(stage:{self.stage_name},action:{self.action_name},point:{self.point},info:" + str(self.info) + ")"

    def __init__(self, Info: FightInfo, timer: Timer, no_action=False):
        self.stage_name = str(Info.state)
        self.action_name = 'None' if no_action else str(Info.last_action)
        self.point = Info.node
        self.info = "no info"
        if self.stage_name == 'spot_enemy_success' and self.action_name == 'retreat':
            self.info = remove_0_value_from_dict(timer.enemy_type_count)
        if self.stage_name == 'fight_period':
            self.info = remove_0_value_from_dict(timer.enemy_type_count)
        if self.stage_name == "result":
            self.info = timer.fight_result
        if self.stage_name == 'proceed':
            self.info = timer.ship_status


class FightRecorder():
    def __init__(self):
        self.sr = []

    def reset(self):
        self.sr = []

    def add_stage(self, stage, action, timer: Timer):
        self.append(StageRecorder(stage, action, timer))

    def append(self, stage: StageRecorder):
        self.sr.append(stage)

    def get_fight_infos(self, stage):
        return [x.info for x in self.sr if x.stage_name == stage]

    @property
    def fight_results(self):
        return self.get_fight_infos("result")

    @property
    def enemys(self):
        return self.get_fight_infos("fight_period")

    def __str__(self):
        res = "".join(str(x) + "\n" for x in self.sr)
        return res


class FightPlan(ABC):
    def __init__(self, timer: Timer):
        # 把timer引用作为内置对象，减少函数调用的时候所需传入的参数
        self.timer = timer
        self.fight_recorder = FightRecorder()

    def run(self):
        """ 主函数，负责一次完整的战斗. """
        self.fight_recorder.reset()
        # 战斗前逻辑
        ret = self._enter_fight()
        if ret == "success":
            pass
        elif ret == "dock is full":
            return ret  # TODO：加入分解逻辑
        elif ret == "fight end":
            self.timer.set_page(self.Info.end_page)
            return ret
        elif ret == "out of times":
            return ret
        else:
            print("\n==========================================")
            print('enter fight error,screen logged')
            self.timer.log_screen()
            raise BaseException(str(time.time()) + "enter fight error")

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
                self.timer.set_page(self.Info.end_page)
                break

        return "success"

    @abstractmethod
    def _enter_fight(self) -> str:
        pass

    @abstractmethod
    def _make_decision(self) -> str:
        pass


class DecisionBlock():
    def __init__(self, timer: Timer, args):
        self.timer = timer
        self.__dict__.update(args)

        # 用于根据规则设置阵型
        self.set_formation_by_rule = False
        self.formation_by_rule = 0

    def check_rules(self):
        for rule in self.enemy_rules:
            condition, act = rule
            rcondition = ""
            last = 0
            for i, ch in enumerate(condition):
                if ord(ch) > ord("Z") or ord(ch) < ord("A"):
                    if last != i:
                        if condition[last:i] in ALL_SHIP_TYPES:
                            rcondition += f"self.timer.enemy_type_count['{condition[last:i]}']"
                        else:
                            rcondition += condition[last:i]
                    rcondition += ch
                    last = i + 1

            if (S.DEBUG):
                print(rcondition)
            if eval(rcondition):
                return act

    def make_decision(self, state, last_state, last_action):

        if state in ["fight_period", "night_fight_period"]:
            return None, "fight continue"

        elif state == "spot_enemy_success":
            retreat = self.supply_ship_mode == 1 and self.timer.enemy_type_count[SAP] == 0  # 功能：遇到补给舰则战斗，否则撤退
            detour = self.detour  # 由Node指定是否要迂回

            # 功能，根据敌方阵容进行选择
            act = self.check_rules()

            if act == "retreat":
                retreat = True
            elif act == "detour":
                detour = True
            elif isinstance(act, int):
                self.set_formation_by_rule = True
                self.formation_by_rule = act
            if retreat:
                self.timer.Android.click(677, 492, delay=0)
                return "retreat", "fight end"
            elif detour:
                self.timer.Android.click(540, 500, delay=0)
                return "detour", "fight continue"
            self.timer.Android.click(855, 501, delay=0)
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
            self.timer.Android.click(573, value * 100 - 20, delay=2)
            return value, "fight continue"
        elif state == "night":
            is_night = self.night
            if is_night:
                self.timer.Android.click(325, 350, delay=2)
                return "yes", "fight continue"
            else:
                self.timer.Android.click(615, 350, delay=2)
                return "no", "fight continue"
        elif state == "result":
            time.sleep(1.5)
            self.timer.Android.click(900, 500, 2, 0.16)
            return None, "fight continue"
        elif state == "get_ship":
            self.timer.Android.click(900, 500, 1, 0.25)
            return None, "fight continue"

        elif state == "lock_ship":
            pass    # TODO: 锁定舰船

        else:
            print("===========Unknown State==============")
            raise BaseException()


class NodeLevelDecisionBlock(DecisionBlock):
    """ 地图上一个节点的决策模块 """

    def make_decision(self, state, last_state, last_action):
        """进行决策并执行
        """
        return super().make_decision(state, last_state, last_action)
