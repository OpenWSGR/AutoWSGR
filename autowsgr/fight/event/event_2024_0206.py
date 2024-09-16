"""有选择入口和常规推图的活动可以抄这个
"""

import os

from autowsgr.constants.data_roots import MAP_ROOT
from autowsgr.fight.common import start_march
from autowsgr.fight.event.event import Event
from autowsgr.fight.normal_fight import NormalFightInfo, NormalFightPlan
from autowsgr.game.game_operation import MoveTeam, quick_repair
from autowsgr.timer import Timer
from autowsgr.utils.math_functions import CalcDis

NODE_POSITION = (
    None,
    (238, 134),
    (92, 375),
    (666, 444),
    (815, 172),
    (478, 216),  # 阿尔法入口用的地图
    (478, 216),  # 贝塔入口用的地图
    (478, 216),  # 西格玛入口用的地图
    (478, 216),  # 德尔塔入口用的地图
)


class EventFightPlan20240206(Event, NormalFightPlan):
    def __init__(
        self,
        timer: Timer,
        plan_path,
        from_which_entrance=None,
        fleet_id=None,
        event="20240206",
    ):
        """
        Args:
            fleet_id : 新的舰队参数, 优先级高于 plan 文件, 如果为 None 则使用计划参数.

            from_which_entrance : 指定入口, 默认为 1 表示从 alpha 进入, 如果为 2 则从 beta 进入, 以此类推， 优先级高于 plan 文件, 如果为 0 则使用计划文件的参数, 如果都没有指定, 默认从 alpha 进入
        """
        self.event_name = event
        NormalFightPlan.__init__(self, timer, plan_path, fleet_id=fleet_id)
        Event.__init__(self, timer, event)

        if from_which_entrance is not None:
            self.from_alpha = from_which_entrance

        if "from_which_entrance" not in self.__dict__:
            self.from_which_entrance = 0

    def _load_fight_info(self):
        self.Info = EventFightInfo20240206(self.timer, self.chapter, self.map)
        self.Info.load_point_positions(os.path.join(MAP_ROOT, "event", self.event_name))

    def _change_fight_map(self, chapter_id, map_id):
        """选择并进入战斗地图(chapter-map)"""
        # self.change_difficulty(chapter_id)
        pass

    def _check_entrance(self, from_which_entrance):
        # from_which_entrance为1,2,3,4
        check_position_pixel = [
            None,
            ((119, 73), (11, 30, 73)),
            ((277, 75), (12, 32, 81)),
            ((419, 74), (14, 31, 75)),
            ((56, 72), (12, 31, 73)),
        ]

        # return self.timer.check_pixel((795, 321), (254, 148, 36), screen_shot=True)
        # 第一个是xy坐标，第二个是三原色的像素
        # from_which_entrance=int(from_which_entrance)
        if from_which_entrance == 0:
            return True
        else:
            if 1 <= from_which_entrance <= 4:
                return self.timer.check_pixel(
                    check_position_pixel[from_which_entrance][0],
                    check_position_pixel[from_which_entrance][1],
                    screen_shot=True,
                )

            else:
                raise IndexError

    def _go_fight_prepare_page(self) -> None:
        if not self.timer.image_exist(self.Info.event_image[1], need_screen_shot=0):
            self.timer.click(*NODE_POSITION[self.map])

        # 选择入口
        if self._check_entrance(self.from_which_entrance) == False:
            entrance_position = [None, (131, 58), (280, 54), (421, 55), (593, 51)]
            self.timer.click(*entrance_position[self.from_which_entrance])

        self.timer.wait_image(self.event_image[1])
        self.timer.click(850, 490)
        try:
            self.timer.wait_pages("fight_prepare_page", after_wait=0.15)
        except:
            self.timer.logger.warning("匹配战斗页面失败，尝试重新匹配")
            self.timer.go_main_page()
            self._go_map_page()
            self._go_fight_prepare_page()


class EventFightInfo20240206(Event, NormalFightInfo):
    def __init__(self, timer: Timer, chapter_id, map_id, event="20240206") -> None:
        NormalFightInfo.__init__(self, timer, chapter_id, map_id)
        Event.__init__(self, timer, event)
        self.map_image = self.common_image["special"] + [self.event_image[1]]
        self.end_page = "unknown_page"
        self.state2image["map_page"] = [self.map_image, 5]
