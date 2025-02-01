import os
from typing import Literal

from autowsgr.constants.custom_exceptions import ImageNotFoundErr
from autowsgr.constants.data_roots import MAP_ROOT
from autowsgr.constants.image_templates import IMG
from autowsgr.fight.battle import BattleInfo, BattlePlan
from autowsgr.fight.common import start_march
from autowsgr.game.game_operation import destroy_ship, get_ship, quick_repair
from autowsgr.game.get_game_info import detect_ship_stats
from autowsgr.port.ship import Fleet, count_ship
from autowsgr.timer import Timer
from autowsgr.utils.api_image import crop_image, crop_rectangle_relative
from autowsgr.utils.io import count, yaml_to_dict


"""决战结构:
上层控制+单点战斗
"""


def is_ship(element: str) -> bool:
    return element not in ['长跑训练', '肌肉记忆', '黑科技']


def get_formation(fleet: Fleet, enemy: list) -> Literal[4, 2]:
    anti_sub = count(['CL', 'DD', 'CVL'], enemy)
    if (fleet.exist('U-1206') and anti_sub <= 1) or anti_sub <= 0:
        return 4
    return 2


class DecisiveStats:
    def __init__(self, timer: Timer, chapter: int = 6) -> None:
        # 选择战备舰队的点击位置
        self.timer = timer
        self.key_points = [
            [
                '',
            ],
        ]  # [chapter][map] (str)
        self.map_end = [
            '',
        ]  # [chapter] (str)
        self.enemy = [
            [
                [
                    '',
                ],
            ],
        ]  # [chapter][map][node(str)] (lst["", enemies])
        self.__dict__.update(
            yaml_to_dict(os.path.join(MAP_ROOT, 'decisive_battle', '3.yaml')),
        )
        self.score = 10
        self.level = 1  # 副官等级
        self.exp = 0
        self.need = 0  # 副官升级所需经验
        self.chapter = chapter  # 大关
        self.fleet = Fleet(self.timer)
        self.ships = set()
        self.ship_stats = [-1] * 7
        self.selections = []  # 获取战备舰队的元素

    def next(self) -> Literal['quit', 'next', 'continue']:
        if self.node == self.map_end[self.chapter][self.map]:
            self.map += 1
            self.node = 'A'
            return 'quit' if (self.map == 4) else 'next'
        self.node = chr(ord(self.node) + 1)
        return 'continue'

    @property
    def enemy_now(self):
        return self.enemy[self.chapter][self.map][self.node]

    def reset(self) -> None:
        chapter = self.chapter
        self.__init__(self.timer)
        self.chapter = chapter

    def is_begin(self):
        return self.node == 'A' and self.map == 1


class Logic:
    """决战逻辑模块"""

    def __init__(
        self,
        timer: Timer,
        stats: DecisiveStats,
        level1: list,
        level2: list,
        flagship_priority: list,
    ) -> None:
        self.timer = timer
        self.config = timer.config
        self.logger = timer.logger

        self.level1 = list(set(level1))
        self.level2 = list(
            {'长跑训练', '肌肉记忆', *self.level1, *level2, '黑科技'},
        )  # 包括 level1 和可用增益
        self.flag_ships = list(flagship_priority)
        self.stats = stats

    def _choose_ship(self, must=False) -> list:
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
            if target in self.stats.selections:
                cost = self.stats.selections[target][0]
                if score >= cost and cost <= lim:
                    score -= cost
                    result.append(target)
        if not result and must:
            result.append(next(iter(self.stats.selections.keys())))
        return result

    def _use_skill(self) -> Literal[3, 0]:
        return 3 if (self.stats.node == 'A') else 0

    def need_repair(self) -> bool:
        return bool(1 in self.stats.ship_stats or 2 in self.stats.ship_stats)

    def _up_level(self) -> bool:
        return bool(self.stats.need - self.stats.exp <= 5 and self.stats.score >= 5)

    def formation(self) -> None:
        pass

    def night(self) -> None:
        pass

    def get_best_fleet(self) -> list[str]:
        ships = self.stats.ships
        self.logger.debug(f'拥有舰船: {ships}')
        best_ships = [
            '',
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
            best_ships.append('')  # noqa: PERF401
        self.logger.debug(f'(不考虑破损情况) 当前最优：{best_ships}')
        return best_ships

    def _retreat(self) -> bool:
        if type(self) is not Logic:
            return count_ship(self._get_best_fleet()) < 2
        return count_ship(self.get_best_fleet()) < 2

    def _leave(self) -> Literal[False]:
        return False


class DecisiveBattle:
    """决战控制模块
    目前仅支持 E5, E6, E4
    """

    def run_for_times(self, times: int = 1) -> Literal['leave', 'quit']:
        assert times >= 1
        res = self.start_fight()
        for _ in range(times - 1):
            self.reset_chapter()
            res = self.start_fight()
        return res

    def run(self) -> Literal['leave', 'quit']:
        return self.run_for_times()

    def __init__(self, timer: Timer) -> None:
        self.timer = timer
        self.config = timer.config.decisive_battle

        self.repair_strategy = self.config.repair_level
        self.full_destroy = self.config.full_destroy
        self.stats = DecisiveStats(timer, self.config.chapter)
        self.logic = Logic(
            self.timer,
            self.stats,
            self.config.level1,
            self.config.level2,
            self.config.flagship_priority,
        )

    def buy_ticket(self, use: str = 'steel', times: int = 3) -> None:
        self.enter_decisive_battle()
        position = {'oil': 184, 'ammo': 235, 'steel': 279, 'aluminum': 321}
        self.timer.click(458 * 0.75, 665 * 0.75, delay=1.5)
        self.timer.click(638, position[use], delay=1, times=times)
        self.timer.click(488, 405)

    def recognize_map(self) -> int:
        CHECK_POINT = {
            4: [(0.381, 0.436), (0.596, 0.636), (0.778, 0.521)],
            5: [(0.418, 0.378), (0.760, 0.477), (0.550, 0.750)],
            6: [(0.606, 0.375), (0.532, 0.703), (0.862, 0.644)],
        }
        check_point = CHECK_POINT[self.stats.chapter]
        for i, point in enumerate(check_point):
            if not self.timer.check_pixel(
                (int(point[0] * 960), int(point[1] * 540)),
                (250, 244, 253),
                30,
                True,
            ):
                self.timer.logger.info(f'识别决战地图参数, 第 {i} 小节正在进行')
                return i
        self.timer.logger.info('识别决战地图参数, 第 3 小节正在进行')
        return 3

    def recognize_node(self, retry: int = 0) -> str:
        position = self.timer.wait_images_position(
            IMG.fight_image[18:20],
            confidence=0.7,
        )
        self.timer.logger.debug(f'Ship_ICON position: {position}')
        cropped_image = crop_rectangle_relative(
            self.timer.get_screen(),
            position[0] / 960 - 0.03,
            0,
            0.042,
            1,
        )
        result = self.timer.ocr_backend.bin.recognize_map(cropped_image)
        if result != '0':
            self.timer.logger.info(f'识别决战地图参数, 第 {result[0]} 节点正在进行')
            return result[0]
        if retry > 3:
            self.timer.logger.warning('识别决战地图参数失败, 退出逻辑')
            raise BaseException
        self.timer.logger.warning(
            f'识别决战地图参数失败, 正在重试第 {retry + 1} 次',
        )
        return self.recognize_node(retry + 1)
        # result = recognize(cropped_image, "ABCDEFGHIJK")
        # return result[0][1]

    def detect(self, type: str = 'enter_map'):
        """检查当前关卡状态
        Args:
            type:
                enter_map: 决战入口检查
                running: 检查地图是否在战斗准备页面

        Returns:
            str: ['challenging', 'refreshed', 'refresh']
            str: ['fight_prepare', 'map']
        """
        if type == 'enter_map':
            _res = ['cant_fight', 'challenging', 'refreshed', 'refresh']
            res = self.timer.wait_images(
                IMG.decisive_battle_image[3:7],
                after_get_delay=0.2,
            )
        if type == 'running':
            _res = ['map', 'fight_prepare']
            res = self.timer.wait_images(
                [IMG.decisive_battle_image[1]] + IMG.identify_images['fight_prepare_page'],
                gap=0.03,
                after_get_delay=0.2,
            )
        return _res[res]

    def _go_map_page(self) -> None:
        if self.detect('running') == 'fight_prepare':
            self.timer.click(30, 30)
            self.timer.wait_image(IMG.decisive_battle_image[1])

    def go_fleet_page(self) -> None:
        if self.detect('running') == 'map':
            self.timer.click(900 * 0.75, 667 * 0.75)
            try:
                self.timer.wait_images(
                    IMG.identify_images['fight_prepare_page'],
                    timeout=5,
                    after_get_delay=1,
                )
            except:
                self.timer.logger.warning('进入出征准备页面失败，正在重试')
                self.go_fleet_page()

    def repair(self) -> None:
        self.go_fleet_page()
        quick_repair(
            self.timer,
            self.repair_strategy,
        )  # TODO：我的中破比很高，先改成只修大破控制一下用桶
        # quick_repair(self.timer, 2)

    def next(self) -> Literal['quit', 'next', 'continue']:
        res = self.stats.next()
        if res in ['next', 'quit']:
            self.timer.confirm_operation(timeout=5, must_confirm=1)  # 确认通关
            self.timer.confirm_operation(timeout=5, must_confirm=1)  # 确认领取奖励
            get_ship(self.timer)
        return res

    def choose(self, refreshed: bool = False, rec_only: bool = False):
        # ===================获取备选项信息======================
        # 右上角资源位置
        RESOURCE_AREA = ((0.911, 0.082), (0.974, 0.037))
        # 船名位置
        SHIP_X = [
            (0.195, 0.305),
            (0.318, 0.429),
            (0.445, 0.555),
            (0.571, 0.677),
            (0.695, 0.805),
        ]
        SHIP_Y = (0.715, 0.685)
        # 船的费用
        COST_AREA = ((0.195, 0.808), (0.805, 0.764))
        # 选择位置
        CHOOSE_X = [0.25, 0.375, 0.5, 0.625, 0.75]
        CHOOSE_Y = 0.5

        screen = self.timer.get_screen()
        try:
            self.stats.score = self.timer.recognize_number(
                crop_image(screen, *RESOURCE_AREA),
                # rgb_select=(250, 250, 250),
                # tolerance = 50,
            )[1]
        except:
            # TODO: 提高OCR对单个数字的识别率
            self.timer.logger.warning('读取当前可用费用失败')
            self.stats.score = 0
        self.timer.logger.debug(f'当前可用费用为：{self.stats.score}')
        results = self.timer.recognize_number(
            crop_image(screen, *COST_AREA),
            extra_chars='x',
            multiple=True,
        )
        costs = [t[1] for t in results]
        _costs, ships, real_position = [], [], []
        for i, cost in enumerate(costs):
            try:
                if cost > self.stats.score:
                    continue
            except Exception as e:
                self.timer.logger.warning(f'读取购买费用出错，错误如下:\n {e}')
                continue
            ships.append(
                self.timer.recognize(
                    crop_image(
                        screen,
                        (SHIP_X[i][0], SHIP_Y[0]),
                        (SHIP_X[i][1], SHIP_Y[1]),
                    ),
                    candidates=self.timer.ship_names,
                )[1],
            )
            _costs.append(cost)
            real_position.append(i)
        # print("Scan result:", costs)
        costs = _costs
        selections = {
            ships[i]: (costs[i], (CHOOSE_X[real_position[i]], CHOOSE_Y)) for i in range(len(costs))
        }
        if rec_only:
            return None
        # ==================做出决策===================
        self.stats.selections = selections
        self.timer.logger.debug('可购买舰船：', selections)
        choose = self.logic._choose_ship(
            must=(self.stats.map == 1 and self.stats.node == 'A' and refreshed),
        )
        if len(choose) == 0 and not refreshed:
            self.timer.click(380, 500)  # 刷新备选舰船
            self.timer.wait_image(
                [IMG.decisive_battle_image[2], IMG.decisive_battle_image[8]],
                timeout=2,
            )
            self.timer.logger.info('刷新备选舰船')
            return self.choose(True)

        for target in choose:
            cost, p = selections[target]
            self.stats.score -= cost
            self.timer.logger.debug(f'选择购买：{target}，花费：{cost}，点击位置：{p}')
            self.timer.relative_click(*p)
            if is_ship(target):
                self.stats.ships.add(target)
        self.timer.click(580, 500)  # 关闭/确定
        return None

    def up_level_assistant(self) -> None:
        self.timer.click(75, 667 * 0.75)
        self.stats.score -= 5

    def use_skill(self, type: int = 3) -> None:
        SKILL_POS = (0.2143, 0.894)
        SHIP_AREA = ((0.26, 0.715), (0.74, 0.685))

        self.timer.relative_click(*SKILL_POS)
        if type == 3:
            ship_results = self.timer.recognize(
                crop_image(self.timer.get_screen(), *SHIP_AREA),
                candidates=self.timer.ship_names,
                multiple=True,
            )
            ships = [ship[1] for ship in ship_results]
            self.timer.logger.info(f'使用技能获得: {ships}')
            for ship in ships:
                self.stats.ships.add(ship)
        self.timer.relative_click(*SKILL_POS, times=2, delay=0.3)

    def _get_chapter(self) -> int:
        CHAPTER_AREA = ((0.818, 0.867), (0.875, 0.81))
        text = self.timer.recognize(
            crop_image(self.timer.get_screen(), *CHAPTER_AREA),
            allowlist='Ex-0123456789',
            # rgb_select=(247, 221, 82),
            tolerance=50,
        )[1]
        return int(text[-1])

    def _move_chapter(self) -> None:
        if self._get_chapter() < self.stats.chapter:
            self.timer.click(900, 507)
        elif self._get_chapter() > self.stats.chapter:
            self.timer.click(788, 507)
        else:
            return
        self._move_chapter()

    def enter_decisive_battle(self) -> None:
        self.timer.goto_game_page('decisive_battle_entrance')
        self.timer.click(115, 113, delay=1.5)
        self.detect()

    def enter_map(
        self,
        check_map=True,
    ) -> Literal['full_destroy_success', 'other chapter is running', 'ok'] | None:
        self.stats.node = 'A'
        if check_map:
            self.enter_decisive_battle()
            self._move_chapter()
            stats = self.detect()
            self.stats.map = self.recognize_map()
            if stats == 'refresh':
                entered = self.reset_chapter()
                if entered:
                    return None
                stats = 'refreshed'
            if stats == 'refreshed':
                # 选用上一次的舰船并进入
                if self.check_dock_full():
                    return 'full_destroy_success'
                self.timer.click(500, 500, delay=0.25)
                self.stats.map = 1
                for i in range(5):  # noqa: B007
                    self.timer.click_image(
                        IMG.decisive_battle_image[7],
                        timeout=12,
                        must_click=True,
                    )
                    self.timer.click(873, 500)
                    if (
                        self.timer.wait_images(
                            [
                                IMG.decisive_battle_image[1],
                                IMG.decisive_battle_image[3],
                            ],
                            timeout=10,
                            gap=0.03,
                        )
                        is not None
                    ):
                        break
                if i > 3:
                    raise TimeoutError('选择决战舰船失败')
            else:
                self.timer.click(500, 500, delay=0)
        else:
            self.detect()
            self.stats.map = self.recognize_map()
            self.timer.click(500, 500, delay=0)

        if self.check_dock_full():
            return 'full_destroy_success'

        res = self.timer.wait_images(
            [IMG.decisive_battle_image[1], IMG.decisive_battle_image[3]],
            timeout=5,
            gap=0.03,
        )
        if res is None:
            raise ImageNotFoundErr("Can't Identify on enter_map")
        return 'other chapter is running' if (res == 1) else 'ok'

    def check_dock_full(self) -> bool:
        """
        检查船舱是否满，船舱满了自动解装
        """
        if self.timer.wait_images(IMG.symbol_image[12], timeout=2) is not None:
            if self.full_destroy:
                self.timer.relative_click(0.38, 0.565)
                destroy_ship(self.timer)
                self.enter_map()
                return True
            self.timer.logger.warning('船舱已满, 但不允许解装')
            return False
        return False

    def retreat(self) -> None:
        self._go_map_page()
        self.timer.click(36, 33)
        self.timer.click(600, 300)

    def leave(self) -> None:
        self._go_map_page()
        self.timer.click(36, 33)
        self.timer.relative_click(0.372, 0.584)
        self.detect()
        self.timer.relative_click(0.03, 0.08)
        self.timer.go_main_page()

    def _get_exp(self, retry: int = 0) -> None:
        EXP_AREA = ((0.018, 0.854), (0.092, 0.822))
        try:
            self.stats.exp = 0
            self.stats.need = 20
            src = self.timer.recognize(
                crop_image(self.timer.get_screen(), *EXP_AREA),
                allowlist='Lv.(/)0123456789',
            )[1]
            try:
                index1 = src.index('(')
            except ValueError:
                index1 = float('inf')  # 如果没有找到，设置为无穷大
            try:
                index2 = src.index('（')
            except ValueError:
                index2 = float('inf')  # 如果没有找到，设置为无穷大
            i1 = min(index1, index2)
            if i1 == float('inf'):
                raise ValueError("未找到 '(' 或 '（'")
            i2 = src.index('/')
            src = src.rstrip(')）')
            self.stats.exp = int(src[i1 + 1 : i2])
            self.stats.need = int(src[i2 + 1 :])
            self.timer.logger.debug(
                f'当前经验：{self.stats.exp}，升级需要经验：{self.stats.need}',
            )
        except:
            self.timer.logger.warning('识别副官升级经验数值失败')

    def _before_fight(self) -> Literal['retreat', 'leave'] | None:
        if self.timer.wait_image(IMG.confirm_image[1:], timeout=1):
            self.timer.click(300, 225)  # 选上中下路
            self.timer.confirm_operation(must_confirm=1)
        if self.timer.wait_image(
            [IMG.decisive_battle_image[2], IMG.decisive_battle_image[8]],
            timeout=2,
        ):
            self.choose()  # 获取战备舰队
        # 升级副官坏了,经验检测也停用
        # self._get_exp()
        self.timer.wait_image(IMG.decisive_battle_image[9])
        self.stats.node = self.recognize_node()
        # 升级副官, 现在这功能坏掉了
        # while self.logic._up_level():
        #     self.up_level_assistant()
        #     self._get_exp()
        if self.logic._use_skill():
            self.use_skill(self.logic._use_skill())

        if self.stats.fleet.empty() and not self.stats.is_begin():
            self._check_fleet()
        self.fleet = self.logic.get_best_fleet()
        # if self.logic._leave() or (
        #     type(self) is not DecisiveBattle
        #     and any(self.timer.port.get_ship_by_name(ship).status in [2] for ship in self.rships)
        # ):  # 大破修
        if self.logic._leave() or (
            type(self) is not DecisiveBattle
            and any(self.timer.port.get_ship_by_name(ship).status in [1, 2] for ship in self.rships)
        ):  # 中破修
            self.leave()
            return 'leave'
        if self.logic._retreat():
            self.retreat()
            return 'retreat'
        if self.stats.fleet != self.fleet:
            self._change_fleet(self.fleet)
            self.stats.ship_stats = detect_ship_stats(self.timer)
        if self.logic.need_repair():
            self.repair()
        return None

    def _after_fight(self) -> None:
        self.timer.logger.info(self.stats.ship_stats)

    def _check_fleet(self) -> None:
        self.stats.ships.clear()

        self.go_fleet_page()
        self.stats.fleet.detect()

        for ship in self.stats.fleet.ships[1:]:
            self.stats.ships.add(ship)
        self.stats.ship_stats = detect_ship_stats(self.timer)

        for i in range(1, 7):
            if self.timer.port.have_ship(self.stats.fleet.ships[i]):
                ship = self.timer.port.get_ship_by_name(self.stats.fleet.ships[i])
                if ship.status != 3:
                    ship.status = self.stats.ship_stats[i]

        self.timer.relative_click(0.1, 0.5)
        res = self.timer.wait_images(
            IMG.choose_ship_image[1:3] + [IMG.choose_ship_image[4]],
            after_get_delay=0.4,
            gap=0,
            timeout=16,
        )
        if res is None:
            raise TimeoutError('选择舰船时点击超时')
        ships = self.timer.recognize_ship(
            self.timer.get_screen()[:, :1048],
            self.timer.ship_names,
        )
        self.timer.logger.info(f'其它可用舰船：{[item[1] for item in ships]}')
        for ship in ships:
            self.stats.ships.add(ship[1])
        self.timer.relative_click(0.05, 0.05)
        res = self.timer.wait_images(
            IMG.identify_images['fight_prepare_page'],
            gap=0.03,
            after_get_delay=0.2,
        )

    def _during_fight(self) -> None:
        formation = get_formation(self.stats.fleet, self.stats.enemy_now)
        night = self.stats.node in self.stats.key_points[self.stats.chapter][self.stats.map]
        plan = DecisiveBattlePlan(
            self.timer,
            formation=formation,
            night=night,
            ship_stats=self.stats.ship_stats,
        )
        plan.run()
        self.stats.ship_stats = plan.info.fight_history.get_fight_results()[-1].ship_stats
        for i in range(1, 7):
            if self.timer.port.have_ship(self.fleet[i]):
                self.timer.port.get_ship_by_name(self.fleet[i]).status = self.stats.ship_stats[i]

    def _change_fleet(self, fleet) -> None:
        self.go_fleet_page()
        self.stats.fleet.set_ship(fleet, order=True, search_method=None)

    def fight(self) -> Literal['quit', 'next', 'continue']:
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

        if res == 'retreat':
            self.enter_map(check_map=False)
            self._reset()
            return self.fight()
        if res == 'leave':
            # 修复受损舰船
            return 'leave'

        self._during_fight()
        self._after_fight()
        return self.next()

    def start_fight(self) -> Literal['quit', 'leave']:
        self.enter_map()
        while True:
            res = self.fight()
            if res == 'leave' or res == 'quit':
                return res
            if res == 'next':  # 下一个关卡
                self.enter_map(False)

    def reset_chapter(self) -> None | Literal[True]:
        """使用磁盘重置关卡, 并重置状态"""
        # Todo: 缺少磁盘报错
        self._reset()
        self._move_chapter()
        self.timer.relative_click(0.5, 0.925)
        if self.check_dock_full():
            return True
        self.timer.confirm_operation(must_confirm=True)
        return None

    def _reset(self) -> None:
        self.stats.reset()


class DecisiveBattlePlan(BattlePlan):
    def __init__(self, timer: Timer, formation: int, night: bool, ship_stats: list) -> None:
        plan_args = {'node_args': {'formation': formation, 'night': night}}
        super().__init__(timer, plan_args=plan_args)
        self.info = DecisiveBattleInfo(timer)
        self.info.ship_stats = ship_stats

    def _enter_fight(self, *args, **kwargs):
        return start_march(self.timer)


class DecisiveBattleInfo(BattleInfo):
    def __init__(self, timer: Timer) -> None:
        super().__init__(timer)
        self.end_page = 'unknown_page'
        self.state2image['battle_page'] = [IMG.decisive_battle_image[1], 5]
        self.state2image['result'] = [IMG.fight_image[3], 60, 0.7]
