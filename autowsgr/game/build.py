import datetime

from autowsgr.constants.image_templates import IMG
from autowsgr.game.game_operation import get_ship
from autowsgr.timer import Timer
from autowsgr.utils.api_image import (
    absolute_to_relative,
    crop_image,
    match_nearest_index,
)
from autowsgr.utils.time import get_eta, str2time

# 开始建造，建造完成，快速建造 三个按钮的中心位置
BUILD_POSITIONS = {
    "ship": [
        (0.823, 0.312),
        (0.823, 0.508),
        (0.823, 0.701),
        (0.823, 0.898),
    ]
}
# x轴边缘到中心距离，y轴边缘到中心距离，y轴相对于BUILD上移
ETA_DELTA = [0.066, 0.025, 0.086]
# 剩余时间区域
ETA_AREAS = {
    "ship": [
        (
            (pos[0] - ETA_DELTA[0], pos[1] + ETA_DELTA[1] - ETA_DELTA[2]),
            (pos[0] + ETA_DELTA[0], pos[1] - ETA_DELTA[1] - ETA_DELTA[2]),
        )
        for pos in BUILD_POSITIONS["ship"]
    ]
}
# 装备页面，右侧整体下移
EQUIPMENT_DELTA = 0.02
BUILD_POSITIONS["equipment"] = [
    (pos[0], pos[1] + EQUIPMENT_DELTA) for pos in BUILD_POSITIONS["ship"]
]
ETA_AREAS["equipment"] = [
    (
        (area[0][0], area[0][1] + EQUIPMENT_DELTA),
        (area[1][0], area[1][1] + EQUIPMENT_DELTA),
    )
    for area in ETA_AREAS["ship"]
]
# 四个资源的左下角位置
RESOURCE_POSITIONS = [(0.2, 0.455), (0.59, 0.455), (0.2, 0.855), (0.59, 0.855)]
# 四个资源的区域
RESOURCE_AREAS = [(pos, (pos[0] + 0.16, pos[1] - 0.1)) for pos in RESOURCE_POSITIONS]
# 操作资源的位置（第一位）
RESOURCE_OPERATE_POSITIONS = [
    [(pos[0] + 0.022 + i * 0.057, pos[1] - 0.046) for i in range(3)]
    for pos in RESOURCE_POSITIONS
]
# 滑动的距离
RESOURCE_OPERATE_DELTA = 0.09


class BuildManager:
    # TODO: 获取建造舰船名称; 正确处理异常情况; 使用内部记忆代替查询
    def __init__(self, timer: Timer) -> None:
        self.timer = timer
        # -1代表空位. None代表未开通
        self.slot_eta = {
            "ship": [None] * 4,
            "equipment": [None] * 4,
        }
        self.update_slot_eta("ship")
        self.update_slot_eta("equipment")

    def update_slot_eta(self, type="ship"):
        """更新建造队列的剩余时间"""
        # 进入页面
        if type == "equipment":
            self.timer.goto_game_page("develop_page")
        if type == "ship":
            self.timer.goto_game_page("build_page")
        # 截图检测
        screen = self.timer.get_screen(self.timer.resolution, need_screen_shot=True)
        for build_slot in range(4):
            ocr_result = self.timer.recognize(
                crop_image(screen, *ETA_AREAS[type][build_slot]),
                allow_nan=True,
            )
            if not ocr_result:
                self.slot_eta[type][build_slot] = None
            elif "完成" in ocr_result[1] or "开始" in ocr_result[1]:
                self.slot_eta[type][build_slot] = -1
            elif ":" in ocr_result[1]:
                self.slot_eta[type][build_slot] = get_eta(str2time(ocr_result[1]))

    def get_timedelta(self, type="ship"):
        """获取建造队列的最小剩余时间
        Args:
            type (str): "ship"/"equipment"
        Returns:
            datetime.timedelta: 剩余时间
        """
        valid_times = [eta for eta in self.slot_eta[type] if eta not in (-1, None)]
        print(valid_times)
        return (
            min(valid_times) - datetime.datetime.now()
            if valid_times
            else datetime.timedelta()
        )

    def get_min_eta(self, type="ship"):
        """获取建造队列的最小结束时间
        Args:
            type (str): "ship"/"equipment"
        Returns:
            datetime.datetime: 结束时间
        """
        return min(self.slot_eta[type])

    def has_empty_slot(self, type="ship") -> bool:
        """检查是否有空位
        Args:
            type (str): "ship"/"equipment"
        Returns:
            bool: 是否有空位
        """
        # 检查是否包含 -1 或当前时间是否大于任何非 None 的时间
        return -1 in self.slot_eta[type] or any(
            datetime.datetime.now() > eta
            for eta in self.slot_eta[type]
            if eta is not None
        )

    def get_build(self, type="ship", allow_fast_build=False) -> bool:
        """获取已经建造好的舰船或装备
        Args:
            type (str): "ship"/"equipment"
            allow_fast_build: 是否允许快速建造
        Returns:
            bool: 是否获取成功
        """
        # 进入页面
        if type == "equipment":
            self.timer.goto_game_page("develop_page")
        if type == "ship":
            self.timer.goto_game_page("build_page")

        # 快速建造
        if allow_fast_build:
            while self.timer.image_exist(IMG.build_image[type].fast):
                self.timer.click_image(IMG.build_image[type].fast)
                self.timer.ConfirmOperation(must_confirm=1, timeout=3)

        # 收完成
        while self.timer.image_exist(IMG.build_image[type].complete):
            try:
                pos = self.timer.click_image(
                    IMG.build_image[type].complete, timeout=3, must_click=True
                )
                if self.timer.image_exist(IMG.build_image[type].full_depot):
                    self.timer.logger.error(f"{type} 仓库已满")
                    self.timer.go_main_page()
                    return False
            except Exception as e:
                self.timer.logger.error(f"收取 {type} 失败: {e}")
                return False

            try:
                ship_name, ship_type = get_ship(self.timer)
                self.timer.logger.info(f"获取 {type}: {ship_name} {ship_type}")
            except Exception as e:
                self.timer.logger.error(f"识别获取{type}内容失败: {e}")

            slot = match_nearest_index(
                absolute_to_relative(pos, self.timer.resolution), BUILD_POSITIONS[type]
            )
            self.slot_eta[type][slot] = -1
        return True

    def build(self, type="ship", resources=None, allow_fast_build=False):
        """建造操作
        Args:
            type (str): "ship"/"equipment"
            resources: 一个列表, 表示油弹钢铝四项资源. Defaults to None.
            allow_fast_build (bool, optional): 如果队列已满, 是否立刻结束一个以开始建造. Defaults to False.
        """

        def choose_build_resources():
            """移动资源
            Args:
                resource_id (int): 资源编号
                dst (int): 目标值
            """
            # 无需设置资源的情况
            if not resources:
                return

            def value_to_digits(value):
                # 拆分为3位数
                return [value // 100, value // 10 % 10, value % 10]

            def detect_build_resources(resource_id) -> list:
                """检查四项资源余量
                Args:
                    resource_id (int): 具体哪一项资源 [0,3]
                Returns:
                    list: 拆分为3位数的资源
                """
                screen = self.timer.get_screen()
                value = self.timer.recognize_number(
                    crop_image(screen, *RESOURCE_AREAS[resource_id]),
                    rgb_select=(255, 155, 81),
                )[1]
                return value_to_digits(value)

            resource_digits = [value_to_digits(res) for res in resources]
            for resource_id, dst in enumerate(resource_digits):
                src = detect_build_resources(resource_id)
                for digit in range(3):
                    while src[digit] != dst[digit]:
                        print(f"资源 {resource_id} 目前 {src} 目标 {dst}")
                        way = -1 if src[digit] < dst[digit] else 1
                        self.timer.relative_swipe(
                            *RESOURCE_OPERATE_POSITIONS[resource_id][digit],
                            RESOURCE_OPERATE_POSITIONS[resource_id][digit][0],
                            RESOURCE_OPERATE_POSITIONS[resource_id][digit][1]
                            + way * RESOURCE_OPERATE_DELTA,
                            duration=0.25,
                        )
                        src = detect_build_resources(resource_id)

        # 检查资源有效性
        if resources:
            minv = 30 if type == "ship" else 10
            maxv = 999
            if min(resources) < minv or max(resources) > maxv:
                self.timer.logger.error(
                    f"用于 {type} 的资源 {resources} 越界, 已自动取消操作"
                )
                return False

        # 收完成，检查空队列
        if not self.get_build(type, allow_fast_build):
            return False
        elif not self.slot_eta[type].count(-1):
            self.timer.logger.error(f"{type} 建造队列已满")
            return False

        # 点击建造
        self.timer.click_image(IMG.build_image[type].start)
        # 选择资源，开始建造
        self.timer.wait_image(IMG.build_image.resource)
        choose_build_resources()
        self.timer.relative_click(0.89, 0.89)
        # 更新建造时间
        self.update_slot_eta(type)

        return True
