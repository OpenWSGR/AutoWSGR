"""舰队问答类活动抄这个
后续做活动地图时截取简单活动页面，放在event_image，出击按钮为1.png，简单活动页面是2.png
"""


import os

from autowsgr.constants.data_roots import MAP_ROOT
from autowsgr.controller.run_timer import Timer
from autowsgr.fight.common import start_march
from autowsgr.fight.event.event import Event
from autowsgr.fight.normal_fight import NormalFightInfo, NormalFightPlan
from autowsgr.game.game_operation import MoveTeam, quick_repair
from autowsgr.utils.math_functions import CalcDis

NODE_POSITION = (
    None,
    (171, 215),
    (166, 445),
    (473, 197),
    (474, 431),
    (790, 179),
    (793, 438),
)


class EventFightPlan20240419(Event, NormalFightPlan):
    def __init__(self, timer: Timer, plan_path, auto_answer_question=False, from_alpha=None, fleet_id=None, event="20240419"):
        """
        Args:
            fleet_id : 新的舰队参数, 优先级高于 plan 文件, 如果为 None 则使用计划参数.

            from_alpha : 指定入口, 默认为 True 表示从 alpha 进入, 如果为 False 则从 beta 进入, 优先级高于 plan 文件, 如果为 None 则使用计划文件的参数, 如果都没有指定, 默认从 alpha 进入
        """
        self.event_name = event
        self.auto_answer_question = auto_answer_question
        NormalFightPlan.__init__(self, timer, plan_path, fleet_id=fleet_id)
        Event.__init__(self, timer, event)

        if from_alpha is not None:
            self.from_alpha = from_alpha

        # 如果未指定入口则默认从 alpha 进入
        if "from_alpha" not in self.__dict__:
            self.from_alpha = True

    def _load_fight_info(self):
        self.Info = EventFightInfo20240419(self.timer, self.chapter, self.map)
        self.Info.load_point_positions(os.path.join(MAP_ROOT, "event", self.event_name))

    def _change_fight_map(self, chapter_id, map_id):
        """选择并进入战斗地图(chapter-map)"""
        self.change_difficulty(chapter_id)

    def _is_alpha(self):
        return self.timer.check_pixel((795, 317), (249, 146, 37), screen_shot=True)  # 蓝 绿 红

    def _go_fight_prepare_page(self) -> None:
        if self.timer.image_exist(self.Info.event_image[3], need_screen_shot=0):  # 每日答题界面
            if self.auto_answer_question:
                pass  # 懒得写了，具体的点和图都没截取
                # self.timer.click_image(self.Info.event_image[4], need_screen_shot=0) # 前往答题界面
                # # 自动答题，只管答题，不管正确率，直到答题结束
                # while self.timer.image_exist(self.Info.event_image[5], need_screen_shot=0): # 判断是否还有下一题答题界面
                #     self.timer.Android.click(800, 450) # 点击第一个答案
                #     if self.timer.image_exist(self.Info.event_image[6], need_screen_shot=0): # 判断是否答题错误
                #         self.timer.Android.click(800, 450) # 答错题选择取消看解析
                #     else:
                #         self.timer.ConfirmOperation() # 答对题收取奖励
                #     self.timer.Android.click(800, 450) # 不确定是否收取奖励之后有下一题
                # self.timer.Android.click() # 退出答题界面

            else:
                self.timer.click_image(self.event_image[4], timeout=3)  # 点击取消每日答题按钮

        if not self.timer.image_exist(self.Info.event_image[1]):
            self.timer.Android.click(*NODE_POSITION[self.map])

        # 选择入口
        if self._is_alpha() != self.from_alpha:
            entrance_position = [(797, 369), (795, 317)]
            self.timer.Android.click(*entrance_position[int(self.from_alpha)])

        if not self.timer.click_image(self.event_image[1], timeout=10):
            self.timer.logger.error("进入战斗准备页面失败,重新尝试进入战斗准备页面")
            self.timer.Android.click(*NODE_POSITION[self.map])
            self.timer.click_image(self.event_image[1], timeout=10)

        try:
            self.timer.wait_pages("fight_prepare_page", after_wait=0.15)
        except Exception as e:
            self.timer.logger.warning("匹配fight_prepare_page失败，尝试重新匹配, error: %s" % e)  #
            self.timer.go_main_page()
            self._go_map_page()
            self._go_fight_prepare_page()


class EventFightInfo20240419(Event, NormalFightInfo):
    def __init__(self, timer: Timer, chapter_id, map_id, event="20240419") -> None:
        NormalFightInfo.__init__(self, timer, chapter_id, map_id)
        Event.__init__(self, timer, event)
        self.map_image = self.common_image["easy"] + self.common_image["hard"] + [self.event_image[1]] + [self.event_image[2]]
        self.end_page = "unknown_page"
        self.state2image["map_page"] = [self.map_image, 5]
