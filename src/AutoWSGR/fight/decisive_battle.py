import os

from AutoWSGR.constants.custom_exceptions import ImageNotFoundErr
from AutoWSGR.constants.data_roots import MAP_ROOT
from AutoWSGR.constants.image_templates import IMG
from AutoWSGR.controller.run_timer import Timer
from AutoWSGR.fight.battle import BattleInfo, BattlePlan
from AutoWSGR.fight.common import start_march
from AutoWSGR.game.game_operation import QuickRepair, get_ship
from AutoWSGR.game.get_game_info import DetectShipStats
from AutoWSGR.ocr.ship_name import _recognize_ship, recognize_number
from AutoWSGR.port.ship import Fleet, count_ship
from AutoWSGR.utils.io import count, yaml_to_dict

"""决战结构:
上层控制+单点战斗
"""


def is_ship(element):
    return element not in ["长跑训练", "肌肉记忆", "黑科技"]


def get_formation(fleet: Fleet, enemy: list):
    anti_sub = count(['CL', 'DD', 'CVL'], enemy)
    if fleet.exist("U-1206") and anti_sub <= 1:
        return 4
    elif (anti_sub <= 0):
        return 4
    return 2


class DB():
    def __init__(self, *args, **kwargs):
        self.__dict__.update(kwargs)

    def make_decision(self, state):
        rule = self.__dict__
        if (state in rule):
            return rule[state]


class DecisiveStats():

    def __init__(self, timer: Timer, chapter=6, map=1, node='A', version=3) -> None:
        # 选择战备舰队的点击位置
        self.timer = timer
        self.key_points = [["", ]]  # [chapter][map] (str)
        self.map_end = ["", ]  # [chapter] (str)
        self.enemy = [[["", ]]]  # [chapter][map][node(str)] (lst["", enemies])
        self.__dict__.update(yaml_to_dict(os.path.join(MAP_ROOT, 'decisive_battle', f"{str(version)}.yaml")))
        self.score = 10
        self.level = 1  # 副官等级
        self.exp = 0
        self.need = 0  # 副官升级所需经验
        self.chapter = chapter  # 大关
        self.map = map  # 小关
        self.node = node
        self.fleet = Fleet(self.timer)
        self.ships = set()
        self.ship_stats = [-1] * 7
        self.selections = []  # 获取战备舰队的元素

    def next(self):
        if (self.node == self.map_end[self.chapter][self.map]):
            self.map += 1
            self.node = 'A'
            return 'quit' if (self.map == 4) else 'next'
        self.node = chr(ord(self.node) + 1)
        return 'continue'

    @property
    def enemy_now(self):
        return self.enemy[self.chapter][self.map][self.node]

    def reset(self):
        chapter = self.chapter
        self.__init__(self.timer)
        self.chapter = chapter

    def is_begin(self):
        return self.node == 'A' and self.map == 1


class _Logit():
    """暂时不启用
    """

    def __init__(self, stats: DecisiveStats, level1: list, level2: list, flagship_priority: list):
        pass

    def _choose_ship(self, must=False):
        pass

    def _use_skill(self):
        pass

    def need_repair(self):
        pass

    def _up_level(self):
        pass

    def formation(self):
        pass

    def night(self):
        pass

    def get_best_fleet(self):
        pass

    def _retreat(self):
        pass

    def _leave(self):
        pass


class Logic(_Logit):
    """决战逻辑模块
    """

    def __init__(self, timer, stats: DecisiveStats, level1: list, level2: list, flagship_priority: list):
        self.timer = timer
        self.config = timer.config
        self.logger = timer.logger
        
        self.level1 = level1
        self.level2 = ["长跑训练", "肌肉记忆"] + self.level1 + level2 + ["黑科技"]
        self.flag_ships = flagship_priority
        self.stats = stats

    def _choose_ship(self, must=False):
        lim = 6
        score = self.stats.score
        if (self.stats.fleet.count() <= 1):
            choose = self.level1
        elif (self.stats.fleet.count() < 6):
            choose = [element for element in self.level2 if is_ship(element)]
        else:
            lim = score
            choose = self.level1 + [element for element in self.level2 if not is_ship(element)]
        result = []
        for target in choose:
            if (target in self.stats.selections.keys()):
                cost = self.stats.selections[target][0]
                if (score >= cost and cost <= lim):
                    score -= cost
                    result.append(target)
        if not result and must:
            result.append(list(self.stats.selections.keys())[0])
        return result

    def _use_skill(self):
        return 3 if (self.stats.node == 'A') else 0

    def need_repair(self):
        return bool((1 in self.stats.ship_stats or 2 in self.stats.ship_stats))

    def _up_level(self):
        return bool((self.stats.need - self.stats.exp <= 5 and self.stats.score >= 5))

    def formation(self):
        pass

    def night(self):
        pass

    def get_best_fleet(self):
        ships = self.stats.ships
        self.logger.debug(f"ALL SHIPS: {ships}")
        best_ships = ["", ]
        for ship in self.level1:
            if (ship not in ships or len(best_ships) == 7):
                continue
            best_ships.append(ship)
        for ship in self.level2:
            if (ship not in ships or len(best_ships) == 7 or ship in self.level1):
                continue
            best_ships.append(ship)

        for flag_ship in self.flag_ships:
            if (flag_ship not in best_ships):
                continue
            p = best_ships.index(flag_ship)
            best_ships[p], best_ships[1] = best_ships[1], best_ships[p]
            break

        for _ in range(len(best_ships), 7):
            best_ships.append("")
        self.logger.debug(f"BEST FLEET: {best_ships}")
        return best_ships

    def _retreat(self):
        return bool((count_ship(self.get_best_fleet()) < 2))

    def _leave(self):
        return False


class DecisiveBattle():
    """决战控制模块
    目前仅支持 E5, E6

    Methods:
         start_fight(): 开始战斗, 直到打完第三张图的最后一关停止
         buy_ticket(): 兑换磁盘
         reset(): 重置除了章节之外的所有信息,重置后再调用 start_fight() 则从 chapter-1-A 开始打
    """
    def run_for_times(self, times=1):
        assert(times >= 1)
        self.start_fight()
        for _ in range(times - 1):
            self.reset_chapter()
            self.start_fight()
    
    def run(self):
        self.run_for_times()
    
    def __init__(self, timer: Timer, chapter=6, map=1, node='A', version=3,
                 level1=["鲃鱼", "U-1206", "U-47", "射水鱼", "U-96", "U-1405"],
                 level2=["U-81", "大青花鱼"],
                 flagship_priority=["U-1405", "U-47", "U-96", "U-1206"],
                 logic=None, *args, **kwargs):
        """初始化控制模块
        Important Information:
            : 决战逻辑相当优秀, 不建议自行改写, 满配情况约需要 3~6 快速修复打完一轮 E6, 耗时约为 25mins
            : 请保证可以直接使用上次选船通关, 暂时不支持自动选船
        Args:
            timer (Timer): 记录器
            chapter (int, optional): 决战章节,请保证为 [1, 6] 中的整数. Defaults to 6.
            map (int, optional): 当前小关. Defaults to 1.
            node (str, optional): 当前节点. Defaults to 'A'.
            version (int, optional): 决战版本. Defaults to 3.
            level1: 第一优先舰队, Defaults Recommend
            level2: 第二优先舰船, Defaults Recommend
            flagship_priority: 旗舰优先级, Defaults Recommend
            logic: 逻辑模块, unsupported since now
        Examples:
            : 若当前决战进度为还没打 6-2-A, 则应填写 chapter=6, map=1, node='A'
            : 可以支持断点开始
        """
        self.timer = timer
        self.config = timer.config
        assert (chapter <= 6 and chapter >= 1)
        self.stats = DecisiveStats(timer, chapter, map, node, version)
        if logic is None:
            self.logic = Logic(self.timer, self.stats, level1, level2, flagship_priority)
        self.__dict__.update(kwargs)

    def buy_ticket(self, use='steel', times=3):
        self.enter_decisive_battle()
        position = {"oil": 184, "ammo": 235, "steel": 279, "aluminum": 321}
        self.timer.Android.click(458 * .75, 665 * .75, delay=1.5)
        self.timer.Android.click(638, position[use], delay=1, times=times)
        self.timer.Android.click(488, 405)

    def detect(self, type='enter_map'):
        """检查当前关卡状态
        Args:
            type:
                enter_map: 决战入口检查
                running: 检查地图是否在战斗准备页面

        Returns:
            str: ['challenging', 'refreshed', 'refresh']
            str: ['fight_prepare', 'map']
        """
        if (type == 'enter_map'):
            _res = ['challenging', 'refreshed', 'refresh']
            res = self.timer.wait_images(IMG.decisive_battle_image[3:6], after_get_delay=.2)
        if (type == 'running'):
            _res = ['map', 'fight_prepare']
            res = self.timer.wait_images([IMG.decisive_battle_image[1]] +
                                         IMG.identify_images['fight_prepare_page'], gap=.03, after_get_delay=.2)
        return _res[res]

    def go_map_page(self):
        if (self.detect('running') == 'fight_prepare'):
            self.timer.Android.click(30, 30)
            self.timer.wait_image(IMG.decisive_battle_image[1])

    def go_fleet_page(self):
        if (self.detect('running') == 'map'):
            self.timer.Android.click(900 * .75, 667 * .75)
            self.timer.wait_images(IMG.identify_images['fight_prepare_page'], timeout=4)

    def repair(self):
        self.go_fleet_page()
        QuickRepair(self.timer, 1) # TODO：我的中破比很高，先改成只修大破控制一下用桶
        # QuickRepair(self.timer, 2)

    def next(self):
        res = self.stats.next()
        if res in ['next', 'quit']:
            self.timer.ConfirmOperation()
            self.timer.ConfirmOperation()
            get_ship(self.timer, 5)
        return res

    def choose(self, refreshed=False, rec_only=False):

        # ===================获取备选项信息======================
        DSP = [(250, 390), (410, 550), (570, 710), (730, 870), (890, 1030)]  # 扫描战备舰队获取的位置 (1280x720)
        CHOOSE_POSITION = [(320 * .75, 251), (490 * .75, 251), (645 * .75, 251), (812 * .75, 251), (956 * .75, 251)]
        screen = self.timer.get_screen()
        # 应该能保证数字读取成功...
        self.stats.score = int(recognize_number(screen[25:55, 1162:1245], min_size=5, text_threshold=.05, low_text=.02)[0][1])
        costs = recognize_number(screen[550:585, 245:1031], 'x')
        _costs, ships, real_position = [], [], []
        for i, cost in enumerate(costs):
            if (int(cost[1][1:]) > self.stats.score):
                continue
            ships.append(_recognize_ship(screen[488:515, DSP[i][0]:DSP[i][1]], self.timer.ship_names)[0][0])
            _costs.append(int(cost[1][1:]))
            real_position.append(i)
        # print("Scan result:", costs)
        costs = _costs
        selections = {ships[i]: (costs[i], CHOOSE_POSITION[real_position[i]]) for i in range(len(costs))}
        if rec_only:
            return 
        # ==================做出决策===================
        self.stats.selections = selections
        self.timer.logger.debug(selections)
        choose = self.logic._choose_ship(must=(self.stats.map == 1 and self.stats.node == 'A' and refreshed == True))
        if (len(choose) == 0 and refreshed == False):
            self.timer.Android.click(380, 500)  # 刷新备选舰船
            return self.choose(True)

        for target in choose:
            cost, p = selections[target]
            self.stats.score -= cost
            self.timer.Android.click(*p)
            if (is_ship(target)):
                self.stats.ships.add(target)
        self.timer.Android.click(580, 500)  # 关闭/确定

    def up_level_assistant(self):
        self.timer.Android.click(75, 667 * .75)
        self.stats.score -= 5

    def use_skill(self, type=3):
        self.timer.Android.click(275 * .75, 644 * .75)
        if (type == 3):
            ships = _recognize_ship(self.timer.get_screen()[488:515], self.timer.ship_names)
            for ship in ships:
                self.stats.ships.add(ship[0])
        self.timer.Android.click(275 * .75, 644 * .75, times=2, delay=.3)

    def leave(self):
        self.timer.Android.click(36, 33)
        self.timer.Android.click(360, 300)

    def get_chapter(self):
        return int(recognize_number(self.timer.get_screen()[588:618, 1046:1110], "Ex-X")[0][1][-1])

    def move_chapter(self):
        if (self.get_chapter() < self.stats.chapter):
            self.timer.Android.click(900, 507)
        elif (self.get_chapter() > self.stats.chapter):
            self.timer.Android.click(788, 507)
        else:
            return
        self.move_chapter()

    def enter_decisive_battle(self):
        self.timer.goto_game_page("decisive_battle_entrance")
        self.timer.Android.click(115, 113, delay=1.5)
        self.detect()

    def enter_map(self, check_map=True):
        if (check_map):
            self.enter_decisive_battle()
            stats = self.detect()
            self.move_chapter()
            if (stats == 'refresh'):
                self.reset_chapter()
                stats = 'refreshed'
            if (stats == 'refreshed'):
                # 选用上一次的舰船并进入
                self.timer.Android.click(500, 500, delay=.25)
                self.timer.click_image(IMG.decisive_battle_image[7], timeout=12, must_click=True)
                self.timer.Android.click(873, 500)
            else:
                self.timer.Android.click(500, 500, delay=0)
        else:
            self.detect()
            self.timer.Android.click(500, 500, delay=0)
        res = self.timer.wait_images([IMG.decisive_battle_image[1], IMG.decisive_battle_image[6]], timeout=5, gap=.03)
        if res is None:
            raise ImageNotFoundErr("Can't Identify on enter_map")
        return "other chapter is running" if (res == 1) else "ok"

    def retreat(self):
        self.go_map_page()
        self.timer.Android.click(36, 33)
        self.timer.Android.click(600, 300)

    def get_exp(self):
        src = recognize_number(self.timer.get_screen()[592:615, 48:118], "(/)")[0][1]
        self.stats.exp = 0
        self.stats.need = 20
        try:
            i1 = src.index('(')
            i2 = src.index('/')
            self.stats.exp = int(src[i1 + 1:i2])
            self.stats.need = int(src[i2 + 1:-1])
        except:
            pass

    def before_fight(self):
        if (self.timer.wait_image(IMG.confirm_image[1:], timeout=1) != False):
            self.timer.Android.click(300, 225)  # 选上中下路
            self.timer.ConfirmOperation(must_confirm=1)
        if (self.timer.wait_image([IMG.decisive_battle_image[2], IMG.decisive_battle_image[8]], timeout=5)):
            self.choose()  # 获取战备舰队
        self.get_exp()
        while (self.logic._up_level()):
            self.up_level_assistant()
            self.get_exp()
        if (self.logic._use_skill()):
            self.use_skill(self.logic._use_skill())
        if (self.stats.fleet.empty() and not self.stats.is_begin()):
            self.check_fleet()
        _fleet = self.logic.get_best_fleet()
        if (self.logic._retreat()):
            self.retreat()
            return 'retreat'
        if (self.logic._leave()):
            self.leave()
            return 'leave'
        if (self.stats.fleet != _fleet):
            self.change_fleet(_fleet)
            self.stats.ship_stats = DetectShipStats(self.timer)
        if (self.logic.need_repair()):
            self.repair()

    def after_fight(self):
        self.stats.ship_stats = self.timer.ship_stats
        self.timer.logger.info(self.stats.ship_stats)

    def check_fleet(self):
        self.go_fleet_page()
        self.stats.fleet.detect()
        for ship in self.stats.fleet.ships:
            self.stats.ships.add(ship)
        self.stats.ship_stats = DetectShipStats(self.timer)

    def during_fight(self):
        formation = get_formation(self.stats.fleet, self.stats.enemy_now)
        night = self.stats.node in self.stats.key_points[self.stats.chapter][self.stats.map]
        DecisiveBattlePlan(self.timer, decision_block=DB(formation=formation, night=night)).run()

    def change_fleet(self, fleet):
        self.go_fleet_page()
        self.stats.fleet.set_ship(fleet, order=True, search_method=None)

    def fight(self):
        # try:
        res = self.before_fight()
        # except BaseException as e:
        #     print(e)
        #     if self.stats.map == 1 and self.stats.node == 'A':
        #         # 处理临时 BUG (https://nga.178.com/read.php?tid=34341326)
        #         print(e, "Temporary Game BUG, Processing...")
        #         self.timer.restart()
        #         self.enter_map()
        #         self.reset()
        #         return 'continue'

        if (res == 'retreat'):
            self.enter_map(check_map=False)
            self.reset()
            return self.fight()
        self.during_fight()
        self.after_fight()
        return self.next()

    def start_fight(self):
        self.enter_map()
        while (True):
            res = self.fight()
            if (res == 'quit'):
                return
            elif (res == 'next'):
                self.enter_map(False)

    def reset_chapter(self):
        """使用磁盘重置关卡, 并重置状态
        """
        # Todo: 缺少磁盘报错
        self.stats.reset()
        self.move_chapter()
        self.timer.Android.click(500, 500)
        self.timer.ConfirmOperation()

    def reset(self):
        self.stats.reset()


class DecisiveBattlePlan(BattlePlan):

    def __init__(self, timer: Timer, decision_block=None):
        super().__init__(timer, None, decision_block=decision_block)
        self.Info = DecisiveBattleInfo(timer)

    def _enter_fight(self, *args, **kwargs):
        return start_march(self.timer)


class DecisiveBattleInfo(BattleInfo):

    def __init__(self, timer: Timer):
        super().__init__(timer)
        self.end_page = 'unknown_page'
        self.state2image["battle_page"] = [IMG.decisive_battle_image[1], 5]
        self.state2image["result"] = [IMG.fight_image[3], 60, 0.7]
