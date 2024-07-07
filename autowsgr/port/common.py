import time

from autowsgr.controller.run_timer import Timer
from autowsgr.fight.normal_fight import NormalFightPlan
from autowsgr.game.game_operation import (
    ChangeShip,
    MoveTeam,
    detect_ship_stats,
    quick_repair,
)
from autowsgr.port.ship import Fleet, Ship
from autowsgr.utils.io import yaml_to_dict


class WorkShop:
    def __init__(self) -> None:
        self.available_time = []

    def _time_to_seconds(time_str):
        parts = time_str.split(":")
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

    def update_available_time(self, available_time):
        self.available_time = available_time

    def get_waiting_time(self) -> bool:
        waiting_time = 86400
        for bath in self.bath_available_time:
            if time.time() > bath:
                return 0
            else:
                waiting_time = min(waiting_time, bath - time.time() + 0.1)

    def is_available(self):
        return self.get_waiting_time() == 0

    def add_work(self, time_cost: str) -> bool:
        """增加一项工作

        Args:
            time_cost (str): _description_

        Returns:
            (bool, float): bool 值表示是否成功添加, float 表示结束时间

        """
        if self.is_available():
            for id, bath in enumerate(self.available_time):
                if time.time() > bath:
                    end_time = time.time() + self._time_to_seconds(time_cost)
                    self.available_time[id] = end_time
                    return (True, end_time)
        else:
            return (False, 0)


class BathRoom(WorkShop):
    def add_repair(self, time_cost: str, ship: Ship) -> bool:
        _, end_time = super().add_work(time_cost)
        ship.set_repair(end_time)


class Factory(WorkShop):
    def __init__(self) -> None:
        self.factories_available_time = []

    def update_capacity(self, capacity, occupation, blueprint):
        """更新仓库容量状态

        Args:
            capacity : 总容量
            occupation : 总占用量
        """
        self.capacity = capacity
        self.occupation = occupation
        self.blueprint = blueprint


class Port:
    def __init__(self, timer: Timer) -> None:
        self.timer = timer
        self.oil = 0
        self.ammo = 0
        self.steel = 0
        self.aluminum = 0
        self.diamond = 0
        self.quick_build = 0
        self.bathroom = BathRoom()
        self.ship_factory = Factory()
        self.equipment_factory = Factory()
        self.ships = []
        self.fleet = [[]] * 5
        self.map = 0
        self.chapter = 0

    def have_ship(self, name):
        return any([name == ship.name for ship in self.ships])

    def register_ship(self, name):
        if not self.have_ship(name):
            ship = Ship(name)
            self.ships.append(ship)
            self.timer.logger.info(f"舰船 {name} 已注册")
            return ship
        return None

    def get_ship_by_name(self, name) -> Ship:
        if self.have_ship(name):
            for ship in self.ships:
                if ship.name == name:
                    return ship
        raise BaseException(f"舰船 {ship} 未注册")

    def show_fleet(self):
        self.timer.logger.info("当前已经注册的舰船如下:")
        for ship in self.ships:
            print(ship)


class Task:
    def __init__(self, port: Port) -> None:
        self.port = port
        self.timer = port.timer

    def run(self) -> tuple(bool, list):
        """执行任务
        Returns:
            bool: 任务是否结束
        """


class FightTask(Task):
    def __init__(self, port, file_path="", *args, **kwargs) -> None:
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
        """
        super().__init__(port)
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
                quick_repair(self.timer, 3)

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
                        fleet.change_ship(1, ship)
                    except:
                        raise BaseException(f"未找到 {ship} 舰船")
                    tmp = self.port.register_ship(ship)
                    tmp.statu = detect_ship_stats(self.timer)[1]
                    fleet.detect()
                    tmp.level = fleet.levels[1]
            self.port.show_fleet()

    def build_fleet(self):
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

            return fleet if fleet[-1] is not None else None

        if self.ship_count not in range(1, 7):
            raise ValueError(f"舰队舰船数量设置错误或者未设置, 当前设置的舰船数量为 {self.ship_count}")
        # 清除已经达到等级要求的舰船并检查
        self.all_ships = [
            ship
            for ship in self.all_ships
            if self.port.get_ship_by_name(ship).level >= self.level_limit.get(ship, self.default_level_limit)
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
                if self.port.get_ship_by_name(ship).statu >= self.repair_mode.get(ship, self.default_repair_mode)
            ]
        )
        if fleet is None:
            self.timer.logger.info("由于部分舰船不满足出征条件而无法组织舰队, 任务暂停中...")
            return 2, None
        return 0, fleet

    def check_repair(self):
        pass

    def run(self):
        statu, fleet = self.build_fleet()
        tasks = self.check_repair()
        if statu == 1:
            return True
        if statu == 2:
            return False
        self.times -= 1
        plan = NormalFightPlan(self.timer, self.plan_path, self.fleet_id)
        plan.run()
        return self.times == 0


class BuildTask(Task):
    def __init__(self, port) -> None:
        super().__init__(port)


class OtherTask(Task):
    def __init__(self, port, type, *args, **kwargs) -> None:
        super().__init__(port)


class TaskRunner:
    def __init__(self) -> None:
        self.tasks = []
        pass

    def add_task():
        pass

    def run(self):
        while True:
            for task in self.tasks:
                statu, new_task = task.run()
