import os
import time

from autowsgr.fight.battle import BattleInfo, BattlePlan
from autowsgr.fight.common import ConditionFlag
from autowsgr.fight.event.event import Event
from autowsgr.game.expedition import Expedition
from autowsgr.game.game_operation import detect_ship_stats, quick_repair
from autowsgr.timer import Timer
from autowsgr.utils.io import yaml_to_dict


# image[1] 紧急状况

NODE_POSITION = {
    'main_to_event': (0.95, 0.5),
    'fight_to_event': (0.04, 0.06),
    'map_left': (59 / 960, 230 / 540),
    'map_right': (887 / 960, 230 / 540),
    'not_handle': (614 / 960, 435 / 540),
}


class EventFightPlan2025_0424(Event, BattlePlan):
    def __init__(
        self,
        timer: Timer,
        plan_path,
        fleet_id=None,
        event='20250424',
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
        BattlePlan.__init__(self, timer, plan_args=yaml_to_dict(plan_path))
        self.info = EventFightInfo2025_0424(timer, self.config.chapter, self.config.map)
        Event.__init__(self, timer, event)

    def _load_fight_info(self):
        self.info = EventFightInfo2025_0424(self.timer, self.config.chapter, self.config.map)

    def _go_fight_prepare_page(self) -> None:
        def recognize_map():
            return self.timer.wait_images(self.event_image[3:9]) + 1

        def change_fight_map(target_id):
            cur_id = recognize_map()
            while cur_id < target_id:
                self.timer.relative_click(*NODE_POSITION['map_right'])
                cur_id += 1
            while cur_id > target_id:
                self.timer.relative_click(*NODE_POSITION['map_left'])
                cur_id -= 1
            assert recognize_map() == target_id

        # 进入相应地图页面
        if not self.timer.image_exist(self.event_image[1]):  # 主页到地图
            self.timer.go_main_page()
            self.timer.relative_click(*NODE_POSITION['main_to_event'])

        change_fight_map(self.config.map)
        if not self.timer.click_image(self.event_image[1], timeout=10):
            self.timer.logger.warning('进入战斗准备页面失败,重新尝试进入战斗准备页面')
            self.timer.click_image(self.event_image[1], timeout=10)
        self.timer.relative_click(*NODE_POSITION['not_handle'])
        try:
            self.timer.wait_pages('fight_prepare_page', after_wait=0.15)
        except Exception as e:
            self.timer.logger.warning(
                f'匹配 fight_prepare_page 失败，尝试重新匹配, error: {e}',
            )
            self._go_fight_prepare_page()

    def _enter_fight(self) -> ConditionFlag:
        self._go_fight_prepare_page()
        self.info.ship_stats = detect_ship_stats(self.timer)
        quick_repair(self.timer, self.config.repair_mode, ship_stats=self.info.ship_stats)
        try:
            self.timer.relative_click(0.938, 0.926)  # 开始出征
            self.timer.wait_image(self.event_image[9])
            time.sleep(5)  # 等等吧
            self.timer.relative_click(0.938, 0.926, times=1)  # 点前进
            for _ in range(4):  # 多试几次
                if self.timer.image_exist(self.event_image[9]):
                    time.sleep(0.5)
                    self.timer.relative_click(0.938, 0.926, times=1)
            if not self.timer.image_exist(self.event_image[9]):  # 成功了
                return ConditionFlag.OPERATION_SUCCESS
        except TimeoutError:
            raise RuntimeError('进入战斗超时')

    def _make_decision(self, *args, **kwargs) -> ConditionFlag:
        state = self.update_state() if 'skip_update' not in kwargs else self.info.state
        if state == ConditionFlag.SL:
            return ConditionFlag.SL
        if self.info.state == 'goon_page':  # 估计是打完了
            time.sleep(3)
            for _ in range(8):
                time.sleep(0.5)
                self.timer.relative_click(*NODE_POSITION['fight_to_event'])
                value = self.timer.confirm_operation(False)
                if value:
                    return ConditionFlag.FIGHT_END
            raise RuntimeError('战斗结束确认失败')

        # 进行通用 NodeLevel 决策
        action, fight_stage = self.node.make_decision(
            self.info.state,
            self.info.last_state,
            self.info.last_action,
            self.info,
        )
        self.info.last_action = action
        return fight_stage

    def run_for_times(self, times, gap=1800) -> ConditionFlag:
        """多次执行同一任务, 自动进行远征操作
        Args:
            times (int): 任务执行总次数

            gap (int): 强制远征检查的间隔时间
        Raise:
            RuntimeError: 战斗进行时出现错误
        Returns:
            ConditionFlag
        """
        assert times >= 1
        expedition = Expedition(self.timer)
        self.timer.goto_game_page('map_page')
        for i in range(times):
            if time.time() - self.timer.last_expedition_check_time >= gap:
                self.timer.go_main_page()
                expedition.run(True)
            fight_flag = self.run()
            if fight_flag not in [ConditionFlag.SL, ConditionFlag.OPERATION_SUCCESS]:
                if fight_flag == ConditionFlag.DOCK_FULL:
                    return ConditionFlag.DOCK_FULL
                if fight_flag == ConditionFlag.SKIP_FIGHT:
                    return ConditionFlag.SKIP_FIGHT
                raise RuntimeError(f'战斗进行时出现异常, 信息为 {fight_flag}')
            self.timer.logger.info(f'已出击次数:{i+1}，目标次数{times}')
        return ConditionFlag.OPERATION_SUCCESS


class EventFightInfo2025_0424(Event, BattleInfo):
    def __init__(self, timer: Timer, chapter_id, map_id, event='20250424') -> None:
        self.chapter = chapter_id
        self.map = map_id
        BattleInfo.__init__(self, timer)
        Event.__init__(self, timer, event)
        self.end_page = 'unknown_page'
        self.successor_states['result'] = ['goon_page']
        self.state2image['goon_page'] = [self.event_image[9], 5]  # 打完后的标志
