import time
from typing import Any

from autowsgr.utils.logger import Logger


class Ship:
    def __init__(self, name) -> None:
        self.level = 1
        self.name = name  # 舰船名: 舰船的唯一标识
        self.type = 'DD'  # 舰船类型, 暂时没啥用
        self._statu = 0  # 数字: 0 绿血, 1 黄血, 2 红血, 3 修理中.
        self.repair_end_time = 0
        self.repair_start_time = 0
        self.waiting_repair = 0  # 是否正在修理队列中
        self.equipments = None  # 装备状态, 暂时不用

    def __str__(self) -> str:
        table = ['绿血', '中破', '大破', '修理中']
        return f'舰船名:{self.name}\n舰船状态:{table[self.status]}\n舰船等级:{self.level}\n\n'

    @property
    def status(self):
        if self.is_repairing():
            return 3
        return self._statu

    @status.setter
    def status(self, new_statu):
        self._statu = new_statu

    def set_repair(self, time_cost):
        """设置舰船正在修理中
        Args:
            time_cost (str): 识别出的时间字符串
        """
        self.waiting_repair = False
        self._statu = 0
        self.repair_start_time = time.time()
        self.repair_end_time = self.repair_start_time + time_cost

    def is_repairing(self):
        return time.time() < self.repair_end_time


class WorkShop:
    def __init__(self) -> None:
        self.available_time = None

    def _time_to_seconds(self, time_str):
        parts = time_str.split(':')
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

    def update_available_time(self, available_time):
        self.available_time = available_time

    def get_waiting_time(self):
        # 如果不确定, 返回 None
        if self.available_time is None:
            return None

        waiting_time = 86400
        for bath in self.available_time:
            if time.time() > bath:
                return 0
            waiting_time = min(waiting_time, bath - time.time() + 0.1)
        return waiting_time

    def is_available(self):
        return self.get_waiting_time() == 0

    def add_work(self, time_cost: str) -> tuple[bool, float]:
        """增加一项工作

        Args:
            time_cost (str): _description_

        Returns:
            (bool, float): bool 值表示是否成功添加, float 表示结束时间

        """
        if self.is_available() and self.available_time is not None:
            for id, bath in enumerate(self.available_time):
                if time.time() > bath:
                    end_time = time.time() + self._time_to_seconds(time_cost)
                    self.available_time[id] = end_time
                    return (True, end_time)
        return (False, 0)


class BathRoom(WorkShop):
    def __init__(self) -> None:
        super().__init__()

    def add_repair(self, time_cost: str) -> None:
        super().add_work(time_cost)


class Factory(WorkShop):
    def __init__(self) -> None:
        self.capacity = None
        self.waiting_destory = False

    def update_capacity(self, capacity, occupation, blueprint: int | None = None):
        """更新仓库容量状态

        Args:
            capacity : 总容量
            occupation : 总占用量
        """
        self.capacity = int(capacity)
        self.occupation = int(occupation)
        if blueprint is not None:
            self.blueprint = blueprint

    @property
    def full(self):
        if self.capacity is not None:
            return self.occupation >= self.capacity
        return False


class Port:
    factory: Any

    def __init__(self, logger: Logger) -> None:
        self.logger = logger
        self.oil = 0
        self.ammo = 0
        self.steel = 0
        self.aluminum = 0
        self.diamond = 0
        self.quick_build = 0
        self.bathroom = BathRoom()
        self.ship_factory = Factory()
        self.ships = []
        self.fleet = [[]] * 5
        self.map: int | None = 0
        self.chapter: int | None = 0

    def have_ship(self, name):
        return any(name == ship.name for ship in self.ships)

    def register_ship(self, name):
        if not self.have_ship(name):
            ship = Ship(name)
            self.ships.append(ship)
            self.logger.info(f'舰船 {name} 已注册')
            return ship
        return None

    def get_ship_by_name(self, name) -> Ship | None:
        if self.have_ship(name):
            for ship in self.ships:
                if ship.name == name:
                    return ship
        self.show_fleet()
        self.logger.info(f'需要查找的舰船 {name} 未找到')
        return None

    def show_fleet(self):
        self.logger.info('当前已经注册的舰船如下:')
        for ship in self.ships:
            print(ship)
