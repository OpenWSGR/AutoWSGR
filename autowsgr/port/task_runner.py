import datetime
import queue
import threading
import time

from autowsgr.constants import literals
from autowsgr.constants.custom_exceptions import ShipNotFoundErr
from autowsgr.fight.decisive_battle import DecisiveBattle, Logic
from autowsgr.game.build import BuildManager  # noqa: TC001
from autowsgr.game.expedition import Expedition
from autowsgr.game.game_operation import (
    change_ship,
    destroy_ship,
    detect_ship_stats,
    move_team,
    quick_repair,
)
from autowsgr.port.common import Ship
from autowsgr.port.ship import Fleet, count_ship
from autowsgr.timer.timer import Timer
from autowsgr.types import ShipType
from autowsgr.utils.api_image import crop_rectangle_relative
from autowsgr.utils.io import yaml_to_dict


def quick_register(timer: Timer, ships):
    def get_input():
        enable_quick = input() == 'y'
        q.put(enable_quick)

    print('检测到你在当前任务中启用了快速注册')
    print('请确认以下所有舰船均为绿血且不处于修复状态:')
    print(ships)
    print('确认吗(y/n)')

    q = queue.Queue()
    th = threading.Thread(target=get_input)
    th.start()
    th.join(10)
    if not q.empty() and q.get():
        for ship in ships:
            if not timer.port.have_ship(ship):
                tmp = timer.port.register_ship(ship)
                tmp.level = 1
                tmp.status = 0
        return True
    timer.logger.info('放弃快速注册')
    return False


def register(timer: Timer, ships, fleet_id):
    if any(not timer.port.have_ship(ship) for ship in ships):
        timer.logger.info('含有未注册的舰船, 正在注册中...')

        # 检查当前舰队中是否含有未初始化的舰船并将其初始化
        timer.goto_game_page('fight_prepare_page')
        fleet = Fleet(timer, fleet_id)
        fleet.detect()
        if any(ship in ships for ship in fleet.ships):
            timer.logger.info('该舰队中处于修复状态的舰船正在被快速修复')
            quick_repair(timer, 3, switch_back=True)

        for i, ship in enumerate(fleet.ships):
            if ship in ships and not timer.port.have_ship(ship):
                tmp = timer.port.register_ship(ship)
                tmp.level = fleet.levels[i]
                tmp.status = detect_ship_stats(timer)[i]

        # 逐个初始化舰船, 效率较低, 待优化
        for ship in ships:
            if not timer.port.have_ship(ship):  #
                timer.logger.info(f'正在尝试注册 {ship}')
                try:
                    change_ship(timer, fleet_id, 1, ship)
                    quick_repair(timer, 3, switch_back=True)
                except ShipNotFoundErr:
                    timer.relative_click(0.05, 0.05)
                    timer.logger.warning(f'舰船 {ship} 注册失败, 放弃注册')
                    continue
                    # raise BaseException(f"未找到 {ship} 舰船")
                tmp = timer.port.register_ship(ship)
                tmp.status = detect_ship_stats(timer)[1]
                fleet.detect()
                tmp.level = fleet.levels[1]
        timer.port.show_fleet()


class Task:
    def __init__(self, timer: Timer) -> None:
        self.port = timer.port
        self.timer = timer

    def run(self):
        """执行任务
        Returns:
            bool: 任务是否结束, 如果任务正常结束, 则从 TaskRunner 中删除
            list:
        """


class FightTask(Task):
    def __init__(self, timer: Timer, file_path='', plan=None, *args, **kwargs) -> None:
        """
        Args:
            plan(FightPlan): 使用哪个战斗方案模板, 默认为 None.

            banned_ship (list(list(str))): 1-index 的列表, banned_ship[i] 表示第 i 号位不允许的舰船

            default_level_limit: 默认等级限制(2-111 之间的整数)

            level_limit (dict): 舰船名到等级限制的映射

            default_repair_mode: 默认修理方式

            repair_mode (dict): 舰船名到修理方式的映射

            ship_count: 舰队舰船数量

            fleet_id: 使用的舰队编号, 忽视 fight_plan 中的对应参数, 不支持第一舰队

            times: 任务重复次数

            max_repair_time: 最大修理时间: 超出该时间使用快修

            quick_repair: 无轮换时是否使用快修

            destroy_ship_types: 解装舰船

            all_ships: 所有参与轮换的舰船
        """
        super().__init__(timer)
        self.quick_register = False
        self.last_exec = time.time()
        self.plan = plan
        self.quick_repair = False
        self.destroy_ship_types = None
        self.default_level_limit = 2
        self.level_limit = {}
        self.default_repair_mode = 2
        self.repair_mode = {}
        self.ship_count = 0
        self.banned_ship = [[]] * 7
        self.fleet_id = 2
        self.times = 1
        self.all_ships = []
        if file_path != '':
            self.__dict__.update(yaml_to_dict(file_path))
        self.__dict__.update(kwargs)

        # 处理填写不规范的一些问题
        if self.repair_mode is None:
            self.repair_mode = {}
        if self.level_limit is None:
            self.level_limit = {}

        # 添加到舰船名字列表中
        for ship in self.all_ships:
            if ship not in self.timer.ship_names:
                self.timer.ship_names.append(ship)

        # 注册舰船 (等级直接设置成 1, 打完一遍后会更新掉)
        if self.quick_register and quick_register(timer, self.all_ships):
            return
        register(timer, self.all_ships, self.fleet_id)

    def build_fleet(self, ignore_statu=False):
        """尝试组建出征舰队"""

        def _build_fleet(ships):
            fleet = [
                None,
            ]
            ships = [ship for ship in ships if self.port.have_ship(ship)]
            ships = set(ships)
            for i in range(1, self.ship_count + 1):
                fleet.append(None)
                for ship in ships:
                    if self.banned_ship == -1 or ship not in self.banned_ship[i]:
                        fleet[i] = ship
                        ships.remove(ship)
                        break

            return None if any(ship is None for ship in fleet[1 : self.ship_count + 1]) else fleet

        if self.ship_count not in range(1, 7):
            raise ValueError(
                f'舰队舰船数量设置错误或者未设置, 当前设置的舰船数量为 {self.ship_count}',
            )
        # 清除已经达到等级要求的舰船并检查
        self.all_ships = [
            ship
            for ship in self.all_ships
            if self.port.get_ship_by_name(ship).level
            < self.level_limit.get(ship, self.default_level_limit)
        ]
        fleet = _build_fleet(self.all_ships)
        if fleet is None:
            self.timer.logger.info('由于等级超限无法组织舰队, 任务终止.')
            return 1, None

        # 清除不满足出征条件的舰船并检查
        fleet = _build_fleet(
            [
                ship
                for ship in self.all_ships
                if (
                    (
                        not ignore_statu
                        and self.port.get_ship_by_name(ship).status
                        < self.repair_mode.get(ship, self.default_repair_mode)
                    )
                    or ignore_statu
                )
            ],
        )
        if fleet is None:
            self.timer.logger.info(
                '由于部分舰船不满足出征条件而无法组织舰队, 任务暂停中...',
            )
            return 2, None
        return 0, fleet

    def check_repair(self):
        tasks = []
        for name in self.all_ships:
            ship = self.port.get_ship_by_name(name)
            if ship.status != 3 and ship.status >= self.repair_mode.get(
                ship,
                self.default_repair_mode,
            ):
                # 满足修理条件
                if ship.waiting_repair:
                    self.timer.logger.debug(
                        f'舰船 {name} 已在修理队列中, 不再重复添加.',
                    )
                else:
                    ship.waiting_repair = True
                    self.timer.logger.info(f'添加舰船 {name} 到修理队列.')
                    tasks.append(RepairTask(self.timer, ship))
        return tasks

    def run(self):
        # 应该退出的情况: 1.等级限制 2.不允许快修, 需要等待 3. 船坞已满, 需清理 4. 战斗任务已经执行完毕
        if self.times <= 0:
            return True, []

        status, fleet = self.build_fleet()
        if status == 1:
            return True, []
        if status == 2 and not self.quick_repair:
            return False, [*self.check_repair(), self]
        if self.port.ship_factory.full:
            tasks = [
                OtherTask(
                    self.timer,
                    'destroy',
                    destroy_ship_types=self.destroy_ship_types,
                ),
            ]
            return False, tasks
        if self.plan is None:
            raise ValueError('没有指定战斗策略')
        plan = self.plan
        plan.fleet = fleet
        plan.fleet_id = self.fleet_id
        plan.repair_mode = [3] * 6
        # 设置战时快修
        if status == 2:
            status, fleet = self.build_fleet(True)
            for i, name in enumerate(fleet):
                if name is None:
                    continue
                ship = self.port.get_ship_by_name(name)
                if ship.status >= self.repair_mode.get(name, self.default_repair_mode):
                    self.timer.logger.info(f'舰船 {name} 的状态已经标记为修复')
                    plan.repair_mode[i] = ship.status
                    ship.set_repair(0)
        # 执行战斗
        ret = plan.run()
        # 处理船坞已满
        if ret == literals.DOCK_FULL_FLAG:
            return False, [
                OtherTask(
                    self.timer,
                    'destroy',
                    destroy_ship_types=self.destroy_ship_types,
                ),
            ]
        self.times -= 1
        # 更新舰船状态
        if self.plan is None:
            self.timer.wait_pages('map_page')
        else:
            pass
        plan._go_fight_prepare_page()
        self.timer.goto_game_page('fight_prepare_page')
        move_team(self.timer, self.fleet_id)
        fleet = Fleet(self.timer)
        fleet.detect()
        ship_stats = detect_ship_stats(self.timer)
        for i, name in enumerate(fleet.ships):
            if name is None:
                continue
            ship = self.port.get_ship_by_name(name)
            if ship is not None:
                ship.level = fleet.levels[i]
                ship.status = ship_stats[i]

        return True, [*self.check_repair(), self]


class BuildTask(Task):
    def __init__(self, port) -> None:
        super().__init__(port)


class RepairTask(Task):
    def __init__(self, timer: Timer, ship: Ship, *args, **kwargs) -> None:
        super().__init__(timer)
        self.max_repiar_time = 1e9
        self.__dict__.update(kwargs)
        self.ship = ship

    def run(self):
        def switch_quick_repair(enable: bool):
            enabled = self.timer.check_pixel(
                (445, 91),
                (253, 150, 40),
                screen_shot=True,
            )
            if enabled != enable:
                self.timer.relative_click(0.464, 0.168)

        waiting = self.port.bathroom.get_waiting_time()
        if waiting is None:
            # 检查等待时间
            available_time = []
            timer = self.timer
            timer.goto_game_page('bath_page')
            baths = [(0.076, 0.2138), (0.076, 0.325), (0.076, 0.433)]
            repair_position = [
                (0.283, 0.544),
                (0.530, 0.537),
                (0.260, 0.656),
                (0.513, 0.644),
            ]

            for i in range(self.timer.config.bathroom_feature_count):
                timer.relative_click(*baths[i])
                for j in range(4):
                    timer.relative_click(*repair_position[j])
                    time.sleep(0.5)
                    timer.update_screen()
                    timer.logger.info(f'检查中:{(i, j)}')
                    if '快速修理' in [
                        result[1]
                        for result in self.recognize_screen_relative(
                            0.279,
                            0.319,
                            0.372,
                            0.373,
                        )
                    ]:
                        timer.logger.info('此位置有舰船修理中')
                        seconds = self.port.bathroom._time_to_seconds(
                            self.recognize_screen_relative(0.413, 0.544, 0.506, 0.596)[0][1],
                        )
                        timer.logger.info(f'预期用时: {seconds} 秒')
                        available_time.append(time.time() + seconds)
                        timer.relative_click(
                            797 / 1280,
                            509 / 720,
                            delay=1,
                        )  # 关闭快修选择界面

            while len(available_time) < timer.config.bathroom_count:
                available_time.append(0)
            info = str(
                [
                    datetime.datetime.fromtimestamp(timestamp).strftime(
                        '%Y-%m-%d %H:%M:%S',
                    )
                    for timestamp in available_time
                ],
            )
            self.port.bathroom.update_available_time(available_time)
            timer.logger.info(f'浴室信息检查完毕:{info}')

        # 扫描等待修理列表
        last_result = None
        self.timer.goto_game_page('choose_repair_page')
        while True:
            time_costs = self.recognize_screen_relative(
                0.041,
                0.866,
                0.966,
                0.943,
                True,
            )
            for time_cost in time_costs:
                self.timer.update_screen()
                text = time_cost[1].replace(' ', '')
                if text.startswith('耗时') and len(text) == 11:
                    # 整个图像截取完全
                    x = 0.041 + time_cost[0][0] / self.timer.screen.shape[1]
                    y = 0.741
                    img = crop_rectangle_relative(self.timer.screen, x - 0.06, y, 0.12, 0.042)
                    name = self.timer.recognize(img, candidates=self.timer.ship_names)
                    if len(name) == 0:
                        # 单字船名识别失败
                        continue
                    name = name[1]
                    seconds = self.port.bathroom._time_to_seconds(text[3:])
                    if name == self.ship.name:
                        if self.max_repiar_time <= seconds:
                            # 快速修复
                            self.timer.logger.info('满足快速修复条件, 使用快速修复工具')
                            self.ship.set_repair(0)
                            switch_quick_repair(True)
                            self.timer.relative_click(x, y)
                            return True, []

                        if not self.port.bathroom.is_available():
                            self.timer.logger.info(
                                '当前浴场已满, 不允许快速修复, 此任务延后',
                            )
                            return False, []

                        self.port.bathroom.add_repair(text[3:])
                        self.timer.relative_click(x, y)
                        self.timer.set_page('bath_page')
                        self.ship.set_repair(seconds)
                        return True, []

                    self.timer.logger.debug(f'识别到舰船: {name}')

            self.timer.relative_swipe(0.33, 0.5, 0.66, 0.5, delay=1)
            time.sleep(0.5)
            if time_costs == last_result:
                raise BaseException('未找到目标舰船')
            last_result = time_costs

    def recognize_screen_relative(self, left, top, right, bottom, update=False):
        if update:
            self.timer.update_screen()
        return self.timer.recognize(
            crop_rectangle_relative(self.timer.screen, left, top, right - left, bottom - top),
            multiple=True,
        )


class OtherTask(Task):
    def __init__(self, timer: Timer, type, *args, **kwargs) -> None:
        """其它类型的任务
        Args:
            type (str): 任务类型
                "destroy": 舰船解装
                "empty": 不执行任何操作
                "build": 建造舰船
                "develop": 开发装备
            use_quick_build (bool): 是否允许使用快速修理
            resources_use (tuple): 按顺序油弹钢铝四项
        """
        super().__init__(timer)
        self.type = type
        if type == 'destroy':
            self.destroy_ship_types = kwargs['destroy_ship_types']
            for type in self.destroy_ship_types:
                if not isinstance(type, ShipType):
                    object.__setattr__(
                        self,
                        'destroy_ship_types',
                        [ShipType(t) for t in self.destroy_ship_types],
                    )
                    break
            timer.logger.info('船舱已满, 添加解装任务中...')
            if timer.port.ship_factory.waiting_destory:
                timer.logger.info('任务队列中已经有解装任务, 跳过')
                self.run = lambda self: None

        if type == 'build' or type == 'develop':
            try:
                self.resources_use = kwargs['resources_use']
                if 'use_quick_build' in kwargs:
                    self.use_quick_build = kwargs['use_quick_build']
                else:
                    timer.logger.warning('未指定是否使用快修, 默认不使用')
                    self.use_quick_build = False
            except:
                raise ValueError('未指定油弹钢铝数量')

    def run(self):
        if self.type == 'destroy':
            destroy_ship(self.timer, ship_types=self.destroy_ship_types)

        if self.type == 'build' or self.type == 'develop':
            factory: BuildManager = self.timer.port.factory
            type = 'ship' if self.type == 'build' else 'equipment'
            factory.update_slot_eta(type)
            if factory.has_empty_slot(type):
                factory.build(type, self.resources_use)
            elif not self.use_quick_build:
                factory.build(type, self.resources_use, True)
            else:
                return False, []
        return True, []


class DecisiveLogic(Logic):
    def __init__(self, timer, stats, level1, level2, flagship_priority) -> None:
        super().__init__(timer, stats, level1, level2, flagship_priority)

    def _get_best_fleet(self):
        return super().get_best_fleet()

    def get_best_fleet(self):
        def ship_available(ship):
            # return ship in ships and self.timer.port.have_ship(ship) and self.timer.port.get_ship_by_name(ship).status < 2 # 大破修
            return (
                ship in ships
                and self.timer.port.have_ship(ship)
                and self.timer.port.get_ship_by_name(ship).status < 1
            )  # 中破修

        ships = self.stats.ships
        self.logger.debug(f'拥有舰船: {ships}')
        best_ships = [
            '',
        ]
        for ship in self.level1:
            if not ship_available(ship) or len(best_ships) == 7:
                continue
            best_ships.append(ship)
        for ship in self.level2:
            if not ship_available(ship) or len(best_ships) == 7 or ship in self.level1:
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
        self.logger.debug(f'(考虑破损情况)当前最优：{best_ships}')
        return best_ships

    def _leave(self):
        return count_ship(self.get_best_fleet()) != count_ship(self._get_best_fleet())


class DecisiveFight(DecisiveBattle):
    def __init__(self, timer) -> None:
        super().__init__(timer)
        self.logic = DecisiveLogic(
            self.timer,
            self.stats,
            self.config.level1,
            self.config.level2,
            self.config.flagship_priority,
        )

    def can_fight(self):
        return count_ship(self.logic.get_best_fleet()) == count_ship(self.logic._get_best_fleet())


class DecisiveFightTask(Task):
    def __init__(self, timer, times, enable_quick_register=True, fleet_id=4) -> None:
        """
        Args:
            enable_quick_register (bool, optional): 是否启用快速注册. Defaults to False.
            fleet_id (int, optional): 注册舰队时占用的舰队编号. Defaults to 4.
        """
        super().__init__(timer)
        self.times = times
        self.ships = timer.config.decisive_battle.level1 + timer.config.decisive_battle.level2
        self.db = DecisiveFight(self.timer)
        self.db.rships = self.ships
        if all(self.timer.port.have_ship(ship) for ship in self.ships):
            return
        if enable_quick_register and quick_register(timer, self.ships):
            return
        register(timer, self.ships, fleet_id)

    def check_repair(self):
        tasks = []
        for ship in self.ships:
            ship = self.timer.port.get_ship_by_name(ship)
            # if ship.status > 1 and ship.status < 3: # 大破修
            if ship.status > 0 and ship.status < 2:  # 中破修
                self.timer.logger.info(f'{ship.name} 需要修复')
                tasks.append(RepairTask(self.timer, ship))
        return tasks

    def run(self):
        while self.times > 0:
            if not self.db.can_fight():
                self.timer.logger.info('无法组合出足量的战斗舰船, 任务暂停中')
                return False, []

            res = self.db.run()

            if res == 'leave':
                self.timer.logger.info('战斗舰船发生破损, 暂离修复中....')
                return False, self.check_repair()
            self.times -= 1
            self.db = DecisiveFight(self.timer)
            self.db.rships = self.ships
        return True, []


class TaskRunner:
    def __init__(self, timer: Timer) -> None:
        self.tasks = []
        self.timer = timer

    def add_decisive_task(self, times=1):
        if any(isinstance(task, DecisiveFightTask) for task in self.tasks):
            raise ValueError('已经存在决战任务, 不允许再次添加')
        self.tasks.append(DecisiveFightTask(self.timer, times))

    def run(self):
        while True:
            # 调度逻辑: 依次尝试任务列表中的每个任务, 如果任务正常结束, 则从头开始, 否则找下一个任务.
            # 每个任务尝试执行后, 会向任务列表中添加一些新任务.
            id = 0
            while id < len(self.tasks):
                task = self.tasks[id]
                self.timer.logger.info(f'当前任务类型: {type(task)}')
                if 'times' in task.__dict__:
                    self.timer.logger.info(f'当前任务剩余次数: {task.times}')
                status, new_tasks = task.run()
                if status:
                    self.tasks = self.tasks[0:id] + new_tasks + self.tasks[id + 1 :]
                    break
                self.tasks = self.tasks[0 : id + 1] + new_tasks + self.tasks[id + 1 :]
                id += 1
            if len(self.tasks) == 0:
                self.timer.logger('本次全部任务已经执行完毕')
                return
            print('当轮任务已完成, 正在检查远征')
            time.sleep(30)
            Expedition(self.timer).run(True)
