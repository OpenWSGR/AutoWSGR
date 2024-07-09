import datetime
import time

from autowsgr.constants import literals
from autowsgr.controller.run_timer import Timer
from autowsgr.fight.normal_fight import NormalFightPlan
from autowsgr.game.game_operation import (
    ChangeShip,
    DestroyShip,
    MoveTeam,
    detect_ship_stats,
    quick_repair,
)
from autowsgr.ocr.ocr import recognize
from autowsgr.ocr.ship_name import _recognize_ship
from autowsgr.port.common import Port, Ship
from autowsgr.port.ship import Fleet
from autowsgr.utils.api_image import absolute_to_relative, crop_rectangle_relative
from autowsgr.utils.io import yaml_to_dict


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
    def __init__(self, timer: Timer, file_path="", *args, **kwargs) -> None:
        """
        Args:
            banned_ship (list(list(str))): 1-index 的列表, banned_ship[i] 表示第 i 号位不允许的舰船

            default_level_limit: 默认等级限制(2-111 之间的整数)

            level_limit (dict): 舰船名到等级限制的映射

            default_repair_mode: 默认修理方式

            repair_mode (dict): 舰船名到修理方式的映射

            ship_count: 舰队舰船数量

            fleet_id: 使用的舰队编号, 忽视 fight_plan 中的对应参数, 不支持第一舰队

            plan_path: 战斗策略文件位置, 参考 NormalFightPlan 的规范

            times: 任务重复次数

            max_repair_time: 最大修理时间: 超出该时间使用快修

            quick_repair: 无轮换时是否使用快修

            destroy_ship_types: 解装舰船
        """
        super().__init__(timer)
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
        self.plan_path = ""
        if file_path != "":
            self.__dict__.update(yaml_to_dict(file_path))
        self.__dict__.update(kwargs)
        if any([not self.port.have_ship(ship) for ship in self.all_ships]):
            self.timer.logger.info("含有未注册的舰船, 正在注册中...")

            # 检查当前舰队中是否含有未初始化的舰船并将其初始化
            self.timer.goto_game_page("fight_prepare_page")
            fleet = Fleet(self.timer, self.fleet_id)
            fleet.detect()
            if any([ship in self.all_ships for ship in fleet.ships]):
                self.timer.logger.info("该舰队中处于修复状态的舰船正在被快速修复")
                quick_repair(self.timer, 3, switch_back=True)

            for i, ship in enumerate(fleet.ships):
                if ship in self.all_ships and not self.port.have_ship(ship):
                    tmp = self.port.register_ship(ship)
                    tmp.level = fleet.levels[i]
                    tmp.statu = detect_ship_stats(self.timer)[i]

            # 逐个初始化舰船, 效率较低, 待优化
            for ship in self.all_ships:
                if not self.port.have_ship(ship):  #
                    self.timer.logger.info(f"正在尝试注册 {ship}")
                    try:
                        ChangeShip(self.timer, self.fleet_id, 1, ship)
                        quick_repair(timer, 3, switch_back=True)
                    except:
                        raise BaseException(f"未找到 {ship} 舰船")
                    tmp = self.port.register_ship(ship)
                    tmp.statu = detect_ship_stats(self.timer)[1]
                    fleet.detect()
                    tmp.level = fleet.levels[1]
            self.port.show_fleet()

    def build_fleet(self, ignore_statu=False):
        """尝试组建出征舰队"""

        def _build_fleet(ships):
            fleet = [
                None,
            ]
            ships = set(ships)
            for i in range(1, self.ship_count + 1):
                fleet.append(None)
                for ship in ships:
                    if ship not in self.banned_ship[i]:
                        fleet[i] = ship
                        ships.remove(ship)
                        break

            return None if any([ship is None for ship in fleet[1 : self.ship_count + 1]]) else fleet

        if self.ship_count not in range(1, 7):
            raise ValueError(f"舰队舰船数量设置错误或者未设置, 当前设置的舰船数量为 {self.ship_count}")
        # 清除已经达到等级要求的舰船并检查
        self.all_ships = [
            ship
            for ship in self.all_ships
            if self.port.get_ship_by_name(ship).level < self.level_limit.get(ship, self.default_level_limit)
        ]
        fleet = _build_fleet(self.all_ships)
        if fleet is None:
            self.timer.logger.info("由于等级超限无法组织舰队, 任务终止.")
            return 1, None

        # 清除不满足出征条件的舰船并检查
        fleet = _build_fleet(
            [
                ship
                for ship in self.all_ships
                if (
                    (
                        ignore_statu == False
                        and self.port.get_ship_by_name(ship).statu < self.repair_mode.get(ship, self.default_repair_mode)
                    )
                    or (ignore_statu == True)
                )
            ]
        )
        if fleet is None:
            self.timer.logger.info("由于部分舰船不满足出征条件而无法组织舰队, 任务暂停中...")
            return 2, None
        return 0, fleet

    def check_repair(self):
        tasks = []
        for name in self.all_ships:
            ship = self.port.get_ship_by_name(name)
            if ship.statu != 3 and ship.statu >= self.repair_mode.get(ship, self.default_repair_mode):
                # 满足修理条件
                if ship.waiting_repair:
                    self.timer.logger.debug(f"舰船 {name} 已在修理队列中, 不再重复添加.")
                else:
                    ship.waiting_repair = True
                    self.timer.logger.info(f"添加舰船 {name} 到修理队列.")
                    tasks.append(RepairTask(self.timer, ship))
        return tasks

    def run(self):
        # 应该退出的情况: 1.等级限制 2.不允许快修, 需要等待 3. 船坞已满, 需清理
        statu, fleet = self.build_fleet()
        if statu == 1:
            return True, []
        if statu == 2 and not self.quick_repair:
            return False, self.check_repair() + [self]
        if self.port.ship_factory.full:
            tasks = [OtherTask(self.timer, "destroy", destroy_ship_types=self.destroy_ship_types)]
            return False, tasks

        plan = NormalFightPlan(self.timer, self.plan_path, self.fleet_id, fleet=fleet)
        plan.repair_mode = [3] * 6
        # 设置战时快修
        if statu == 2:
            statu, fleet = self.build_fleet(True)
            for i, name in enumerate(fleet):
                if name == None:
                    continue
                ship = self.port.get_ship_by_name(name)
                if ship.statu >= self.repair_mode.get(name, self.default_repair_mode):
                    self.timer.logger.info(f"舰船 {name} 的状态已经标记为修复")
                    ship.set_repair(0)
                    plan.repair_mode[i] = ship.statu
        # 执行战斗
        ret = plan.run()
        # 处理船坞已满
        if ret == literals.DOCK_FULL_FLAG:
            return False, [OtherTask(self.timer, "destroy", destroy_ship_types=self.destroy_ship_types)]
        self.times -= 1
        # 更新舰船状态
        self.timer.goto_game_page("fight_prepare_page")
        MoveTeam(self.timer, self.fleet_id)
        fleet = Fleet(self.timer)
        fleet.detect()
        ship_stats = detect_ship_stats(self.timer)
        for i, name in enumerate(fleet.ships):
            ship = self.port.get_ship_by_name(name)
            if ship is not None:
                ship.level = fleet.levels[i]
                ship.statu = ship_stats[i]

        return True, self.check_repair() + [self]


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
            enabled = self.timer.check_pixel((445, 91), (253, 150, 40), screen_shot=True)
            if enabled != enable:
                self.timer.Android.relative_click(0.464, 0.168)

        waiting = self.port.bathroom.get_waiting_time()
        if waiting == None:
            # 检查等待时间
            available_time = []
            timer = self.timer
            timer.goto_game_page("bath_page")
            baths = [(0.076, 0.2138), (0.076, 0.325), (0.076, 0.433)]
            repair_position = [(0.283, 0.544), (0.530, 0.537), (0.260, 0.656), (0.513, 0.644)]

            for i in range(self.timer.config.bath["bathroom_feature_count"]):
                timer.Android.relative_click(*baths[i])
                for j in range(4):
                    timer.Android.relative_click(*repair_position[j])
                    time.sleep(0.5)
                    timer.update_screen()
                    timer.logger.info(f"检查中:{(i, j)}")
                    if "快速修理" in [result[1] for result in timer.recognize_screen_relative(0.279, 0.319, 0.372, 0.373)]:
                        timer.logger.info(f"此位置有舰船修理中")
                        seconds = self.port.bathroom._time_to_seconds(
                            timer.recognize_screen_relative(0.413, 0.544, 0.506, 0.596)[0][1]
                        )
                        timer.logger.info(f"预期用时: {seconds} 秒")
                        available_time.append(time.time() + seconds)
                        timer.Android.relative_click(797 / 1280, 509 / 720, delay=1)  # 关闭快修选择界面

            while len(available_time) < timer.config.bath["bathroom_count"]:
                available_time.append(0)
            info = str(
                [datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") for timestamp in available_time]
            )
            self.port.bathroom.update_available_time(available_time)
            timer.logger.info(f"浴室信息检查完毕:{info}")

        # 扫描等待修理列表
        last_result = None
        self.timer.goto_game_page("choose_repair_page")
        while True:
            time_costs = self.timer.recognize_screen_relative(0.041, 0.866, 0.966, 0.943, True)
            for time_cost in time_costs:
                self.timer.update_screen()
                text = time_cost[1].replace(" ", "")
                if text.startswith("耗时") and len(text) == 11:
                    # 整个图像截取完全
                    x = 0.041 + time_cost[0][0][0] / self.timer.screen.shape[1]
                    y = 0.741
                    img = crop_rectangle_relative(self.timer.screen, x, y, 0.12, 0.042)
                    name = _recognize_ship(img, self.timer.ship_names)
                    if len(name) == 0:
                        # 单字船名识别失败
                        continue
                    name = name[0][0]
                    seconds = self.port.bathroom._time_to_seconds(text[3:])
                    if name == self.ship.name:
                        if self.max_repiar_time <= seconds:
                            # 快速修复
                            self.timer.logger.info("满足快速修复条件, 使用快速修复工具")
                            self.ship.set_repair(0)
                            switch_quick_repair(True)
                            self.timer.Android.relative_click(x, y)
                            return True, []

                        if not self.port.bathroom.is_available():
                            self.timer.logger.info("当前浴场已满, 不允许快速修复, 此任务延后")
                            return False, []

                        self.port.bathroom.add_repair(text[3:])
                        self.timer.Android.relative_click(x, y)
                        self.timer.set_page("bath_page")
                        self.ship.set_repair(seconds)
                        self.port.bathroom.add_repair(text[3:])
                        return True, []

                    else:
                        self.timer.logger.debug(f"识别到舰船: {name}")

            self.timer.Android.relative_swipe(0.33, 0.5, 0.66, 0.5, delay=1)
            time.sleep(0.5)
            if time_costs == last_result:
                raise BaseException("未找到目标舰船")
            last_result = time_costs


class OtherTask(Task):
    def __init__(self, timer: Timer, type, *args, **kwargs) -> None:
        """其它类型的任务
        Args:
            type (str): 任务类型
                "destroy": 舰船解装
                "empty": 不执行任何操作


        """
        super().__init__(timer)
        self.type = type
        if type == "destroy":
            self.destroy_ship_types = kwargs["destroy_ship_types"]
            timer.logger.info("船舱已满, 添加解装任务中...")
            if timer.port.ship_factory.waiting_destory:
                timer.logger.info("任务队列中已经有解装任务, 跳过")
                self.run = lambda self: None

    def run(self):
        if self.type == "destroy":
            DestroyShip(self.timer, ship_types=self.destroy_ship_types)
        return True, []


class TaskRunner:
    def __init__(self) -> None:
        self.tasks = []
        pass

    def run(self):
        while True:
            # 调度逻辑: 依次尝试任务列表中的每个任务, 如果任务正常结束, 则从头开始, 否则找下一个任务.
            # 每个任务尝试执行后, 会向任务列表中添加一些新任务.
            id = 0
            while id < len(self.tasks):
                task = self.tasks[id]
                statu, new_tasks = task.run()
                if statu:
                    self.tasks = self.tasks[0:id] + new_tasks + self.tasks[id + 1 :]
                    break
                else:
                    self.tasks = self.tasks[0 : id + 1] + new_tasks + self.tasks[id + 1 :]
                    id += 1
