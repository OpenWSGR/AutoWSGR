"""舰队问答类活动抄这个
后续做活动地图时截取简单活动页面，放在event_image，出击按钮为1.png，简单活动页面是2.png
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
    (0.266, 0.196),
    (0.135, 0.559),
    (0.535, 0.765),
    (0.718, 0.316),
    (0.851, 0.671),
)


class EventFightPlan20240930(Event, NormalFightPlan):
    def __init__(
        self,
        timer: Timer,
        plan_path,
        fleet_id=None,
        event="20240930",
    ):
        """
        Args:
            fleet_id : 新的舰队参数, 优先级高于 plan 文件, 如果为 None 则使用计划参数.

        """
        if os.path.isabs(plan_path):
            plan_path = plan_path
        else:
            plan_path = timer.plan_root_list["event"][event][plan_path]
        self.event_name = event
        NormalFightPlan.__init__(self, timer, plan_path, fleet_id=fleet_id)
        Event.__init__(self, timer, event)

    def _load_fight_info(self):
        self.Info = EventFightInfo20240930(self.timer, self.chapter, self.map)
        self.Info.load_point_positions(os.path.join(MAP_ROOT, "event", self.event_name))

    def _change_fight_map(self, chapter_id, map_id):
        """选择并进入战斗地图(chapter-map)"""
        self.change_difficulty(chapter_id)

    def _go_fight_prepare_page(self) -> None:
        # 进入相应地图页面
        if not self.timer.image_exist(self.Info.event_image[1]):
            self.timer.relative_click(*NODE_POSITION[self.map])

        if not self.timer.click_image(self.event_image[1], timeout=10):
            self.timer.logger.warning("进入战斗准备页面失败,重新尝试进入战斗准备页面")
            self.timer.relative_click(*NODE_POSITION[self.map])
            self.timer.click_image(self.event_image[1], timeout=10)

        try:
            self.timer.wait_pages("fight_prepare_page", after_wait=0.15)
        except Exception as e:
            self.timer.logger.warning(
                f"匹配fight_prepare_page失败，尝试重新匹配, error: {e}"
            )
            self.timer.go_main_page()
            self._go_map_page()
            self._go_fight_prepare_page()


class EventFightInfo20240930(Event, NormalFightInfo):
    def __init__(self, timer: Timer, chapter_id, map_id, event="20240930") -> None:
        NormalFightInfo.__init__(self, timer, chapter_id, map_id)
        Event.__init__(self, timer, event)
        self.map_image = (
            self.common_image["easy"]
            + self.common_image["hard"]
            + self.event_image[1]
            + self.event_image[2]
        )
        self.end_page = "unknown_page"
        self.state2image["map_page"] = [self.map_image, 5]
