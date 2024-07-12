"""舰队问答类活动抄这个
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
    (240, 180),
    (240, 360),
    (480, 180),
    (480, 360),
    (720, 180),
    (720, 360),
)


class EventFightPlan20230613(Event, NormalFightPlan):
    def __init__(self, timer: Timer, plan_path, from_alpha=True, fleet_id=None, event="20230613"):
        """
        Args:
            fleet_id : 新的舰队参数, 优先级高于 plan 文件, 如果为 None 则使用计划参数.

            from_alpha : 指定入口, 默认为 True 表示从 alpha 进入, 如果为 False 则从 beta 进入, 优先级高于 plan 文件, 如果为 None 则使用计划文件的参数, 如果都没有指定, 默认从 alpha 进入
        """
        self.event_name = event
        NormalFightPlan.__init__(self, timer, plan_path, fleet_id=fleet_id)
        Event.__init__(self, timer, event)

        if from_alpha is not None:
            self.from_alpha = from_alpha

        # 如果未指定入口则默认从 alpha 进入
        if "from_alpha" not in self.__dict__:
            self.from_alpha = True

    def _load_fight_info(self):
        self.Info = EventFightInfo20230613(self.timer, self.chapter, self.map)
        self.Info.load_point_positions(os.path.join(MAP_ROOT, "event", self.event_name))

    def _change_fight_map(self, chapter_id, map_id):
        """选择并进入战斗地图(chapter-map)"""
        self.change_difficulty(chapter_id)

    def _is_alpha(self):
        return self.timer.check_pixel((795, 321), (254, 148, 36), screen_shot=True)

    def _go_fight_prepare_page(self) -> None:
        if not self.timer.image_exist(self.Info.event_image[1], need_screen_shot=0):
            self.timer.click(*NODE_POSITION[self.map])

        # 选择入口
        if self._is_alpha() != self.from_alpha:
            entrance_position = [(820, 377), (820, 321)]
            self.timer.click(*entrance_position[int(self.from_alpha)])

        self.timer.wait_image(self.event_image[1])
        self.timer.click(850, 490)
        self.timer.wait_pages("fight_prepare_page", after_wait=0.15)


class EventFightInfo20230613(Event, NormalFightInfo):
    def __init__(self, timer: Timer, chapter_id, map_id, event="20230613") -> None:
        NormalFightInfo.__init__(self, timer, chapter_id, map_id)
        Event.__init__(self, timer, event)
        self.map_image = self.common_image["easy"] + self.common_image["hard"] + [self.event_image[1]]
        self.end_page = "unknown_page"
        self.state2image["map_page"] = [self.map_image, 5]
