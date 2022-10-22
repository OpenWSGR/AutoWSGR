import copy
import time
from abc import ABC, abstractmethod
from functools import partial

from AutoWSGR.constants.custom_expections import ImageNotFoundErr, NetworkErr
from AutoWSGR.constants.image_templates import IMG
from AutoWSGR.constants.other_constants import (ALL_SHIP_TYPES, INFO1, INFO2,
                                                SAP)
from AutoWSGR.constants.positions import BLOODLIST_POSITION
from AutoWSGR.constants.settings import S
from AutoWSGR.controller.run_timer import Timer, process_error
from AutoWSGR.game.game_operation import get_ship
from AutoWSGR.utils.debug import print_err
from AutoWSGR.utils.function_wrapper import try_for_times
from AutoWSGR.utils.io import recursive_dict_update, yaml_to_dict
from AutoWSGR.utils.logger import logit
from AutoWSGR.utils.math_functions import get_nearest
from AutoWSGR.utils.operator import remove_0_value_from_dict


@logit(level=INFO2)
def start_march(timer:Timer, position=(900, 500)):
    timer.Android.click(*position, 1, delay=0)
    start_time = time.time()
    while timer.identify_page('fight_prepare_page'):
        if time.time() - start_time > 3:
            timer.Android.click(*position, 1, delay=0)
            time.sleep(1)
        if timer.image_exist(IMG.symbol_image[3], need_screen_shot=0):
            return "dock is full"
        if timer.image_exist(IMG.symbol_image[9], need_screen_shot=0):
            return "out of times"
        if time.time() - start_time > 15:
            if timer.process_bad_network():
                if timer.identify_page('fight_prepare_page'):
                    return start_march(timer, position)
                else:
                    NetworkErr("status unknow")
            else:
                raise TimeoutError("map_fight prepare timeout")
    return "success"


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
        mvp_pos = self.timer.get_image_position(IMG.fight_image[14])
        self.mvp = get_nearest((mvp_pos[0], mvp_pos[1] + 20), BLOODLIST_POSITION[1])
        self.result = self.timer.wait_images(IMG.fight_result_image, timeout=5)
        if (self.timer.image_exist(IMG.fight_result_image['SS'], need_screen_shot=False)):
            self.result = 'SS'
        if self.result is None:
            self.timer.log_screen()
            raise ImageNotFoundErr("can't identify fight result")
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

    # @try_for_times(process_error) # TODO：这里process_error没有timer，会报错
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
        if (S.SHOW_MATCH_FIGHT_STAGE):
            print("waiting:", possible_states, end="  ")
        images = [self.state2image[state][0] for state in possible_states]
        timeout = [self.state2image[state][1] for state in possible_states]
        confidence = min([0.8] + [self.state2image[state][2] for state in possible_states if len(self.state2image[state]) >= 3])
        timeout = [timeout[i] if modified_timeout[i] == -1 else modified_timeout[i] for i in range(len(timeout))]
        timeout = max(timeout)
        
        
        # 等待其中一种出现
        fun_start_time = time.time()
        while time.time() - fun_start_time <= timeout:
            self._before_match()

            # 尝试匹配
            ret = [self.timer.images_exist(image, 0, confidence=confidence, no_log=True) for image in images]
            if any(ret):
                self.state = possible_states[ret.index(True)]
                if (S.SHOW_MATCH_FIGHT_STAGE):
                    print("matched:", self.state)
                self._after_match()

                return self.state

        # 匹配不到时报错
        print_err(f"state: {self.state} last_action: {self.last_action}", "匹配状态失败,时间戳:" + str(time.time()))
        self.timer.log_screen(True)
        for image in images:
            self.timer.log_image(image, f"match_{str(time.time())}.PNG")
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
            self.info = copy.deepcopy(Info.fight_result)
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

    @property
    def last_stage(self):
        if (len(self.sr) == 0):
            return None
        return self.sr[-1]

    def __str__(self):
        res = "".join(str(x) + "\n" for x in self.sr)
        return res


class FightPlan(ABC):
    def __init__(self, timer: Timer):
        # 把timer引用作为内置对象，减少函数调用的时候所需传入的参数
        self.timer = timer
        self.fight_recorder = FightRecorder()

    def fight(self):
        self.Info.reset()  # 初始化战斗信息
        while True:
            ret = self._make_decision()
            if ret == "fight continue":
                continue
            elif ret == "need SL":
                self.SL()
                return "SL"
            elif ret == "fight end":
                self.timer.set_page(self.Info.end_page)
                return 'success'
                
    def run(self, same_work=False):
        """ 主函数，负责一次完整的战斗. """
        self.fight_recorder.reset()
        # 战斗前逻辑
        ret = self._enter_fight(same_work)
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
            print_err("无法进入战斗,原因未知", '屏幕状态已记录,时间戳:' + str(time.time()))
            self.timer.log_screen()
            raise BaseException(str(time.time()) + "enter fight error")

        # 战斗中逻辑
        return self.fight()

    @abstractmethod
    def _enter_fight(self, same_work=False) -> str:
        pass

    @abstractmethod
    def _make_decision(self) -> str:
        pass

    # =============== 战斗中通用的操作 ===============
    @logit(level=INFO2)
    def SL(self):
        self.timer.restart()
        self.timer.go_main_page()
        self.timer.set_page('main_page')


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

            if (S.SHOW_ENEMY_RUELS):
                print(rcondition)
            if eval(rcondition):
                return act

    def make_decision(self, state, last_state, last_action, _action=None):
        """
        Args:
            _action: 用于强行指定夜战和阵型参数. Defaults to None.
        """
        if state in ["fight_period", "night_fight_period"]:
            if (self.SL_when_enter_fight == True):
                return None, "need SL"
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
            if(_action is not None):
                value = _action
            if spot_enemy:
                if self.SL_when_detour_fails and last_action == "detour":
                    return None, "need SL"

                if self.set_formation_by_rule:
                    if (S.DEBUG):
                        print("set formation by rule:", self.formation_by_rule)
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
            if(_action is not None):
                is_night = _action
            if is_night:
                self.timer.Android.click(325, 350, delay=.5)
                return "yes", "fight continue"
            else:
                self.timer.Android.click(615, 350, delay=.5)
                return "no", "fight continue"
        elif state == "result":
            time.sleep(1.5)
            self.timer.Android.click(900, 500, 2, 0.16)
            return None, "fight continue"
        elif state == "get_ship":
            get_ship(self.timer)
            return None, "fight continue"
        else:
            print("===========Unknown State==============")
            raise BaseException()


class NodeLevelDecisionBlock(DecisionBlock):
    """ 地图上一个节点的决策模块 """

    """ 地图上一个节点的决策模块 """

    def make_decision(self, state, last_state, last_action, _action=None):
        """进行决策并执行
        """
        return super().make_decision(state, last_state, last_action, _action=_action)


class IndependentFightPlan(FightPlan):
    def __init__(self, timer:Timer, end_image, plan_path=None, default_path='plans/default.yaml', *args, **kwargs):
        """创建一个独立战斗模块,处理从形如战役点击出征到收获舰船(或战果结算)的整个过程
        Args:
            end_image (MyTemplate): 整个战斗流程结束后的图片
        """
        super().__init__(timer)
        default_args = yaml_to_dict(default_path)
        node_defaults = default_args["node_defaults"]
        if(plan_path is not None):
            node_args = yaml_to_dict(plan_path)
        else:
            node_args = kwargs
        node_args = recursive_dict_update(node_defaults, node_args)
        self.decision_block = NodeLevelDecisionBlock(timer, node_args)
        self.Info = IndependentFightInfo(timer, end_image)
        
    def run(self):
        super().fight()
        
    def _make_decision(self):
        self.Info.update_state()
        if self.Info.state == "battle_page":
            return "fight end"

        # 进行通用NodeLevel决策
        action, fight_stage = self.decision_block.make_decision(self.Info.state, self.Info.last_state, self.Info.last_action)
        self.Info.last_action = action
        return fight_stage


class IndependentFightInfo(FightInfo):
    def __init__(self, timer: Timer, end_image) -> None:
        super().__init__(timer)

        self.end_page = "battle_page"

        self.successor_states = {
            "proceed": ["spot_enemy_success", "formation", "fight_period"],
            "spot_enemy_success": {
                "retreat": ["battle_page"],
                "fight": ["formation", "fight_period"],
            },
            "formation": ["fight_period"],
            "fight_period": ["night", "result"],
            "night": {
                "yes": ["night_fight_period"],
                "no": [["result", 5]],
            },
            "night_fight_period": ["result"],
            "result": ["battle_page"],    # 两页战果
        }

        self.state2image = {
            "proceed": [IMG.fight_image[5], 5],
            "spot_enemy_success": [IMG.fight_image[2], 15],
            "formation": [IMG.fight_image[1], 15],
            "fight_period": [IMG.symbol_image[4], 3],
            "night": [IMG.fight_image[6], 120],
            "night_fight_period": [IMG.symbol_image[4], 3],
            "result": [IMG.fight_image[16], 60],
            "battle_page": [end_image, 5]
        }
        self.state2image["battle_page"] = [end_image, 5]

    def reset(self):
        self.last_state = ""
        self.last_action = ""
        self.state = "proceed"

    def _before_match(self):
        # 点击加速
        if self.state in ["proceed"]:
            p = self.timer.Android.click(380, 520, delay=0, enable_subprocess=True, print=0, no_log=True)
        self.timer.update_screen()

    def _after_match(self):
        pass  # 战役的敌方信息固定，不用获取
    
