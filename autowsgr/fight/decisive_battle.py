import os
import time

from autowsgr.constants.custom_exceptions import ImageNotFoundErr
from autowsgr.constants.data_roots import MAP_ROOT
from autowsgr.constants.image_templates import IMG
from autowsgr.controller.emulator import Emulator
from autowsgr.controller.run_timer import Timer
from autowsgr.fight.battle import BattleInfo, BattlePlan
from autowsgr.fight.common import start_march
from autowsgr.game.game_operation import DestroyShip, get_ship, quick_repair
from autowsgr.game.get_game_info import detect_ship_stats
from autowsgr.ocr.ship_name import _recognize_ship, recognize_number
from autowsgr.port.ship import Fleet, count_ship
from autowsgr.utils.io import count, yaml_to_dict

"""决战结构:
上层控制+单点战斗
"""


def is_ship(element):
    return element not in ["长跑训练", "肌肉记忆", "黑科技"]


def get_formation(fleet: Fleet, enemy: list):
    anti_sub = count(["CL", "DD", "CVL"], enemy)
    if fleet.exist("U-1206") and anti_sub <= 1:
        return 4
    elif anti_sub <= 0:
        return 4
    return 2


class DB:
    def __init__(self, *args, **kwargs):
        self.__dict__.update(kwargs)

    def make_decision(self, state):
        rule = self.__dict__
        if state in rule:
            return rule[state]


class DecisiveStats:
    def __init__(self, timer: Timer, chapter=6, map=1, node="A", version=3) -> None:
        # 选择战备舰队的点击位置
        self.timer = timer
        self.key_points = [
            [
                "",
            ]
        ]  # [chapter][map] (str)
        self.map_end = [
            "",
        ]  # [chapter] (str)
        self.enemy = [
            [
                [
                    "",
                ]
            ]
        ]  # [chapter][map][node(str)] (lst["", enemies])
        self.__dict__.update(yaml_to_dict(os.path.join(MAP_ROOT, "decisive_battle", f"{str(version)}.yaml")))
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
        if self.node == self.map_end[self.chapter][self.map]:
            self.map += 1
            self.node = "A"
            return "quit" if (self.map == 4) else "next"
        self.node = chr(ord(self.node) + 1)
        return "continue"

    @property
    def enemy_now(self):
        return self.enemy[self.chapter][self.map][self.node]

    def reset(self):
        chapter = self.chapter
        self.__init__(self.timer)
        self.chapter = chapter

    def is_begin(self):
        return self.node == "A" and self.map == 1


class Logic:
    """决战逻辑模块"""

    def __init__(
        self,
        timer,
        stats: DecisiveStats,
        level1: list,
        level2: list,
        flagship_priority: list,
    ):
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
        if self.stats.fleet.count() <= 1:
            choose = self.level1
        elif self.stats.fleet.count() < 6:
            choose = [element for element in self.level2 if is_ship(element)]
        else:
            lim = score
            choose = self.level1 + [element for element in self.level2 if not is_ship(element)]
        result = []
        for target in choose:
            if target in self.stats.selections.keys():
                cost = self.stats.selections[target][0]
                if score >= cost and cost <= lim:
                    score -= cost
                    result.append(target)
        if not result and must:
            result.append(list(self.stats.selections.keys())[0])
        return result

    def _use_skill(self):
        return 3 if (self.stats.node == "A") else 0

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
        best_ships = [
            "",
        ]
        for ship in self.level1:
            if ship not in ships or len(best_ships) == 7:
                continue
            best_ships.append(ship)
        for ship in self.level2:
            if ship not in ships or len(best_ships) == 7 or ship in self.level1:
                continue
            best_ships.append(ship)

        for flag_ship in self.flag_ships:
            if flag_ship not in best_ships:
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


class DecisiveBattle:
    """决战控制模块
    目前仅支持 E5, E6, E4
    """

    def run_for_times(self, times=1):
        assert times >= 1
        self.start_fight()
        for _ in range(times - 1):
            self.reset_chapter()
            self.start_fight()

    def run(self):
        self.run_for_times()

    def __init__(
        self,
        timer: Timer,
        chapter=6,
        map=1,
        node="A",
        version=3,
        level1=["鲃鱼", "U-1206", "U-47", "射水鱼", "U-96", "U-1405"],
        level2=["U-81", "大青花鱼"],
        flagship_priority=["U-1405", "U-47", "U-96", "U-1206"],
        logic=None,
        repair_level=1,
        full_destroy=False,
        *args,
        **kwargs,
    ):
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
            repair_level: 维修策略，1为中破修，2为大破修，Defaults to 1.
            full_destroy: 船舱满了之后是否自动解装，默认不解装.
        Examples:
            : 若当前决战进度为还没打 6-2-A, 则应填写 chapter=6, map=1, node='A'
            : 可以支持断点开始
        """
        self.timer = timer
        self.config = timer.config
        self.repair_strategy = repair_level
        self.full_destroy = full_destroy
        assert chapter <= 6 and chapter >= 1
        self.stats = DecisiveStats(timer, chapter, map, node, version)
        if logic is None:
            self.logic = Logic(self.timer, self.stats, level1, level2, flagship_priority)
        self.__dict__.update(kwargs)

    def buy_ticket(self, use="steel", times=3):
        self.enter_decisive_battle()
        position = {"oil": 184, "ammo": 235, "steel": 279, "aluminum": 321}
        self.timer.Android.click(458 * 0.75, 665 * 0.75, delay=1.5)
        self.timer.Android.click(638, position[use], delay=1, times=times)
        self.timer.Android.click(488, 405)

    def detect(self, type="enter_map"):
        """检查当前关卡状态
        Args:
            type:
                enter_map: 决战入口检查
                running: 检查地图是否在战斗准备页面

        Returns:
            str: ['challenging', 'refreshed', 'refresh']
            str: ['fight_prepare', 'map']
        """
        if type == "enter_map":
            _res = ["challenging", "refreshed", "refresh"]
            res = self.timer.wait_images(IMG.decisive_battle_image[3:6], after_get_delay=0.2)
        if type == "running":
            _res = ["map", "fight_prepare"]
            res = self.timer.wait_images(
                [IMG.decisive_battle_image[1]] + IMG.identify_images["fight_prepare_page"],
                gap=0.03,
                after_get_delay=0.2,
            )
        return _res[res]

    def _go_map_page(self):
        if self.detect("running") == "fight_prepare":
            self.timer.Android.click(30, 30)
            self.timer.wait_image(IMG.decisive_battle_image[1])

    def go_fleet_page(self):
        if self.detect("running") == "map":
            self.timer.Android.click(900 * 0.75, 667 * 0.75)
            try:
                self.timer.wait_images(
                    IMG.identify_images["fight_prepare_page"],
                    timeout=5,
                    after_get_delay=1,
                )
            except:
                self.timer.logger.warning("进入出征准备页面失败，正在重试")
                self.go_fleet_page()

    def repair(self):
        self.go_fleet_page()
        quick_repair(self.timer, self.repair_strategy)  # TODO：我的中破比很高，先改成只修大破控制一下用桶
        # quick_repair(self.timer, 2)

    def next(self):
        res = self.stats.next()
        if res in ["next", "quit"]:
            self.timer.ConfirmOperation(timeout=5, must_confirm=1)  # 确认通关
            self.timer.ConfirmOperation(timeout=5, must_confirm=1)  # 确认领取奖励
            get_ship(self.timer, 5)
        return res

    def choose(self, refreshed=False, rec_only=False):
        # ===================获取备选项信息======================
        DSP = [
            (250, 390),
            (410, 550),
            (570, 710),
            (730, 870),
            (890, 1030),
        ]  # 扫描战备舰队获取的位置 (1280x720)
        CHOOSE_POSITION = [
            (320 * 0.75, 251),
            (490 * 0.75, 251),
            (645 * 0.75, 251),
            (812 * 0.75, 251),
            (956 * 0.75, 251),
        ]
        screen = self.timer.get_screen()
        # 应该能保证数字读取成功...
        self.stats.score = int(recognize_number(screen[25:55, 1162:1245], min_size=5, text_threshold=0.05, low_text=0.02)[0][1])
        self.timer.logger.debug(f"当前可用费用为：{self.stats.score}")
        costs = recognize_number(screen[550:585, 245:1031], "x")
        _costs, ships, real_position = [], [], []
        for i, cost in enumerate(costs):
            try:
                if int(cost[1][1:]) > self.stats.score:
                    continue
            except Exception as e:
                self.timer.logger.error(f"读取购买费用出错，错误如下:\n {e}")
                continue
            ships.append(_recognize_ship(screen[488:515, DSP[i][0] : DSP[i][1]], self.timer.ship_names)[0][0])
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
        choose = self.logic._choose_ship(must=(self.stats.map == 1 and self.stats.node == "A" and refreshed == True))
        if len(choose) == 0 and refreshed == False:
            self.timer.Android.click(380, 500)  # 刷新备选舰船
            return self.choose(True)

        for target in choose:
            cost, p = selections[target]
            self.stats.score -= cost
            self.timer.logger.debug(f"选择购买：{target}，花费：{cost}，点击位置：{p}")
            self.timer.Android.click(*p)
            if is_ship(target):
                self.stats.ships.add(target)
        self.timer.Android.click(580, 500)  # 关闭/确定

    def up_level_assistant(self):
        self.timer.Android.click(75, 667 * 0.75)
        self.stats.score -= 5

    def use_skill(self, type=3):
        self.timer.Android.click(275 * 0.75, 644 * 0.75)
        if type == 3:
            ships = _recognize_ship(self.timer.get_screen()[488:515], self.timer.ship_names)
            for ship in ships:
                self.stats.ships.add(ship[0])
        self.timer.Android.click(275 * 0.75, 644 * 0.75, times=2, delay=0.3)

    def leave(self):
        self.timer.Android.click(36, 33)
        self.timer.Android.click(360, 300)

    def _get_chapter(self):
        return int(recognize_number(self.timer.get_screen()[588:618, 1046:1110], "Ex-X")[0][1][-1])

    def _move_chapter(self):
        if self._get_chapter() < self.stats.chapter:
            self.timer.Android.click(900, 507)
        elif self._get_chapter() > self.stats.chapter:
            self.timer.Android.click(788, 507)
        else:
            return
        self._move_chapter()

    def enter_decisive_battle(self):
        self.timer.goto_game_page("decisive_battle_entrance")
        self.timer.Android.click(115, 113, delay=1.5)
        self.detect()

    def enter_map(self, check_map=True):
        if check_map:
            self.enter_decisive_battle()
            stats = self.detect()
            self._move_chapter()
            if stats == "refresh":
                self.reset_chapter()
                stats = "refreshed"
            if stats == "refreshed":
                # 选用上一次的舰船并进入
                if self.check_dock_full():
                    return "full_destroy_success"
                self.timer.Android.click(500, 500, delay=0.25)
                for i in range(5):
                    self.timer.click_image(IMG.decisive_battle_image[7], timeout=12, must_click=True)
                    self.timer.Android.click(873, 500)
                    if (
                        self.timer.wait_images(
                            [
                                IMG.decisive_battle_image[1],
                                IMG.decisive_battle_image[6],
                            ],
                            timeout=10,
                            gap=0.03,
                        )
                        is not None
                    ):
                        break
                if i > 3:
                    raise TimeoutError("选择决战舰船失败")
            else:
                self.timer.Android.click(500, 500, delay=0)
        else:
            self.detect()
            self.timer.Android.click(500, 500, delay=0)

        if self.check_dock_full():
            return "full_destroy_success"

        res = self.timer.wait_images(
            [IMG.decisive_battle_image[1], IMG.decisive_battle_image[6]],
            timeout=10,
            gap=0.03,
        )
        if res is None:
            raise ImageNotFoundErr("Can't Identify on enter_map")
        return "other chapter is running" if (res == 1) else "ok"

    def check_dock_full(self):
        """
        检查船舱是否满，船舱满了自动解装
        """
        if self.timer.wait_images(IMG.symbol_image[12], timeout=3) is not None and self.full_destroy:
            self.timer.Android.relative_click(0.38 - 0.5, 0.565 - 0.5)
            DestroyShip(self.timer)
            self.enter_map()
            return True
        return False

    def retreat(self):
        self._go_map_page()
        self.timer.Android.click(36, 33)
        self.timer.Android.click(600, 300)

    def _get_exp(self, retry=0):
        try:
            src = recognize_number(self.timer.get_screen()[592:615, 48:118], "(/)")[0][1]
            self.stats.exp = 0
            self.stats.need = 20
            try:
                i1 = src.index("(")
                i2 = src.index("/")
                self.stats.exp = int(src[i1 + 1 : i2])
                self.stats.need = int(src[i2 + 1 : -1])
                self.timer.logger.debug(f"当前经验：{self.stats.exp}，升级需要经验：{self.stats.need}")
            except:
                self.timer.logger.error("识别副官升级经验数值失败")
        except:
            if retry > 3:
                self.timer.logger.error("重新读取 exp 失败, 退出逻辑")
                raise BaseException()  # ToDo: 定义对应的 Exception

            self.timer.logger.warning("读取exp失败，五秒后重试")
            self.timer.Android.click(580, 500)
            time.sleep(5)
            self._get_exp(retry + 1)

    def _before_fight(self):
        if self.timer.wait_image(IMG.confirm_image[1:], timeout=1) != False:
            self.timer.Android.click(300, 225)  # 选上中下路
            self.timer.ConfirmOperation(must_confirm=1)
        if self.timer.wait_image([IMG.decisive_battle_image[2], IMG.decisive_battle_image[8]], timeout=5):
            self.choose()  # 获取战备舰队
        self._get_exp()
        while self.logic._up_level():
            self.up_level_assistant()
            self._get_exp()
        if self.logic._use_skill():
            self.use_skill(self.logic._use_skill())
        if self.stats.fleet.empty() and not self.stats.is_begin():
            self._check_fleet()
        _fleet = self.logic.get_best_fleet()
        if self.logic._retreat():
            self.retreat()
            return "retreat"
        if self.logic._leave():
            self.leave()
            return "leave"
        if self.stats.fleet != _fleet:
            self._change_fleet(_fleet)
            self.stats.ship_stats = detect_ship_stats(self.timer)
        if self.logic.need_repair():
            self.repair()

    def _after_fight(self):
        self.timer.logger.info(self.stats.ship_stats)

    def _check_fleet(self):
        self.go_fleet_page()
        self.stats.fleet.detect()
        for ship in self.stats.fleet.ships:
            self.stats.ships.add(ship)
        self.stats.ship_stats = detect_ship_stats(self.timer)

    def _during_fight(self):
        formation = get_formation(self.stats.fleet, self.stats.enemy_now)
        night = self.stats.node in self.stats.key_points[self.stats.chapter][self.stats.map]
        plan = DecisiveBattlePlan(
            self.timer,
            formation=formation,
            night=night,
            ship_stats=self.stats.ship_stats,
        )
        plan.run()
        self.stats.ship_stats = plan.Info.fight_history.get_fight_results()[-1].ship_stats

    def _change_fleet(self, fleet):
        self.go_fleet_page()
        self.stats.fleet.set_ship(fleet, order=True, search_method=None)

    def fight(self):
        # try:
        res = self._before_fight()
        # except BaseException as e:
        #     print(e)
        #     if self.stats.map == 1 and self.stats.node == 'A':
        #         # 处理临时 BUG (https://nga.178.com/read.php?tid=34341326)
        #         print(e, "Temporary Game BUG, Processing...")
        #         self.timer.restart()
        #         self.enter_map()
        #         self._reset()
        #         return 'continue'

        if res == "retreat":
            self.enter_map(check_map=False)
            self._reset()
            return self.fight()
        self._during_fight()
        self._after_fight()
        return self.next()

    def start_fight(self):
        self.enter_map()
        while True:
            res = self.fight()
            if res == "quit":
                return
            elif res == "next":
                self.enter_map(False)

    def reset_chapter(self):
        """使用磁盘重置关卡, 并重置状态"""
        # Todo: 缺少磁盘报错
        self._reset()
        self._move_chapter()
        self.timer.Android.click(500, 500)
        self.timer.ConfirmOperation()

    def _reset(self):
        self.stats.reset()


class DecisiveBattlePlan(BattlePlan):
    def __init__(self, timer: Timer, formation, night, ship_stats):
        super().__init__(timer, None)
        self.Info = DecisiveBattleInfo(timer)
        self.Info.ship_stats = ship_stats
        self.node.formation = formation
        self.node.night = night

    def _enter_fight(self, *args, **kwargs):
        return start_march(self.timer)


class DecisiveBattleInfo(BattleInfo):
    def __init__(self, timer: Timer):
        super().__init__(timer)
        self.end_page = "unknown_page"
        self.state2image["battle_page"] = [IMG.decisive_battle_image[1], 5]
        self.state2image["result"] = [IMG.fight_image[3], 60, 0.7]
