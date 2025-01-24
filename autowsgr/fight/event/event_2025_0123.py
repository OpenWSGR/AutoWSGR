"""舰队问答类活动抄这个
后续做活动地图时截取简单活动页面，放在event_image，出击按钮为1.png，简单活动页面是2.png
"""

import os

from autowsgr.constants.data_roots import MAP_ROOT
from autowsgr.fight.event.event import Event
from autowsgr.fight.normal_fight import NormalFightInfo, NormalFightPlan
from autowsgr.timer import Timer


NODE_POSITION = (
    None,
    (0.583, 0.206),
    # (0.202, 0.761),
    # (0.489, 0.291),
    # (0.512, 0.768),
    # (0.812, 0.268),
    # (0.832, 0.744),
)


class EventFightPlan20250123(Event, NormalFightPlan):
    def __init__(
        self,
        timer: Timer,
        plan_path,
        fleet_id=None,
        event='20250123',
    ) -> None:
        """
        Args:
            fleet_id : 新的舰队参数, 优先级高于 plan 文件, 如果为 None 则使用计划参数.
        """
        if os.path.isabs(plan_path):
            plan_path = plan_path
        else:
            plan_path = timer.plan_tree['event'][event][plan_path]

        self.event_name = event
        NormalFightPlan.__init__(self, timer, plan_path, fleet_id=fleet_id)
        Event.__init__(self, timer, event)

    def _load_fight_info(self):
        self.info = EventFightInfo20250123(self.timer, self.chapter, self.map)
        self.info.load_point_positions(os.path.join(MAP_ROOT, 'event', self.event_name))

    def _change_fight_map(self, chapter_id, map_id):
        """选择并进入战斗地图(chapter-map)"""
        self.change_difficulty(chapter_id)

    def _go_map_page(self):
        self.timer.go_main_page()
        self.timer.click_image(self.event_image[3], timeout=10)

    def _go_fight_prepare_page(self) -> None:
        if not self.timer.image_exist(self.info.event_image[1]):
            self.timer.relative_click(*NODE_POSITION[self.map])

        if not self.timer.click_image(self.event_image[1], timeout=10):
            self.timer.logger.warning('进入战斗准备页面失败,重新尝试进入战斗准备页面')
            self.timer.relative_click(*NODE_POSITION[self.map])
            self.timer.click_image(self.event_image[1], timeout=10)

        try:
            self.timer.wait_pages('fight_prepare_page', after_wait=0.15)
        except Exception as e:
            self.timer.logger.warning(f'匹配fight_prepare_page失败, 尝试重新匹配, error: {e}')
            self.timer.go_main_page()
            self._go_map_page()
            self._go_fight_prepare_page()


class EventFightInfo20250123(Event, NormalFightInfo):
    def __init__(self, timer: Timer, chapter_id, map_id, event='20250123') -> None:
        NormalFightInfo.__init__(self, timer, chapter_id, map_id)
        Event.__init__(self, timer, event)
        self.map_image = (
            self.common_image['easy']
            + self.common_image['hard']
            + [self.event_image[1]]
            + [self.event_image[2]]
        )
        self.end_page = 'unknown_page'
        self.state2image['map_page'] = [self.map_image, 5]
