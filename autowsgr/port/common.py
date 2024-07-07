import time

from autowsgr.utils.new_logger import Logger


class Ship:
    def __init__(self, name) -> None:
        self.level = 1
        self.name = name  # 舰船名: 舰船的唯一标识
        self.type = "DD"  # 舰船类型, 暂时没啥用
        self.statu = 0  # 数字: 0 绿血, 1 黄血, 2 红血, 3 修理中.
        self.repair_end_time = 0
        self.repair_start_time = 0
        self.waiting_repair = 0  # 是否正在修理队列中
        self.equipments = None  # 装备状态, 暂时不用

    def __str__(self) -> str:
        table = ["绿血", "中破", "大破", "修理中"]
        return f"舰船名:{self.name}\n舰船状态:{table[self.statu]}\n舰船等级:{self.level}\n\n"

    def set_repair(self, end_time: str):
        """设置舰船正在修理中
        Args:
            time_cost (str): 识别出的时间字符串
        """
        self.repair_start_time = time.time()
        self.repair_end_time = end_time

    def is_repairing(self):
        if self.statu == 3:
            if time.time() > self.repair_end_time:
                self.statu = 0
                return True
        else:
            return False


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
            self.logger.info(f"舰船 {name} 已注册")
            return ship
        return None

    def get_ship_by_name(self, name) -> Ship:
        if self.have_ship(name):
            for ship in self.ships:
                if ship.name == name:
                    return ship
        raise BaseException(f"舰船 {ship} 未注册")

    def show_fleet(self):
        self.logger.info("当前已经注册的舰船如下:")
        for ship in self.ships:
            print(ship)
