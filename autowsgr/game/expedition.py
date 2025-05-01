import time

from autowsgr.constants.ui import Node
from autowsgr.timer.timer import Timer, try_to_get_expedition


class Expedition:
    def __init__(self, timer: Timer) -> None:
        self.timer = timer
        self.is_ready = False
        self.last_check = time.time()

    def update(self, force=False):
        self.timer.update_screen()
        if (isinstance(self.timer.now_page, str) and 'unknown' in self.timer.now_page) or (
            isinstance(self.timer.now_page, Node)
            and self.timer.now_page.name
            not in [
                'expedition_page',
                'map_page',
                'battle_page',
                'exercise_page',
                'decisive_battle_entrance',
            ]
        ):
            if force or time.time() - self.last_check > 1800:
                self.timer.go_main_page()
            if isinstance(self.timer.now_page, Node) and self.timer.now_page.name == 'main_page':
                self.is_ready = self.timer.check_pixel(
                    (933, 454),
                    bgr_color=(45, 89, 255),
                )
        else:
            self.is_ready = self.timer.check_pixel((464, 11), bgr_color=(45, 89, 255))

    def run(self, force=False):
        """检查远征, 如果有未收获远征, 则全部收获并用原队伍继续

        Args:
            force (bool): 是否强制检查
        Returns:
            bool: 是否进行了远征操作
        """
        self.update(force=force)
        if self.is_ready:
            self.timer.goto_game_page('expedition_page')
            try_to_get_expedition(self.timer)
            self.timer.last_expedition_check_time = time.time()
        else:
            self.timer.logger.debug('暂无已完成的远征任务')
