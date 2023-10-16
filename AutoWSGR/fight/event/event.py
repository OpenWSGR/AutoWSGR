import os
import time

from AutoWSGR.constants.custom_exceptions import ImageNotFoundErr
from AutoWSGR.constants.data_roots import IMG_ROOT
from AutoWSGR.constants.image_templates import (
    IMG,
    make_dir_templates,
    make_dir_templates_without_number,
)
from AutoWSGR.controller.run_timer import Timer
from AutoWSGR.utils.math_functions import CalcDis


class Event:
    def __init__(self, timer: Timer, event_name):
        image_dir = os.path.join(IMG_ROOT, "event")
        common_dir = os.path.join(IMG_ROOT, "event", "common")
        enemy_dir = os.path.join(IMG_ROOT, "event", "enemy")
        event_dir = os.path.join(image_dir, event_name)
        self.timer = timer
        self.logger = timer.logger

        self.event_image = make_dir_templates(event_dir)
        self.common_image = make_dir_templates_without_number(common_dir)
        self.enemy_image = make_dir_templates_without_number(enemy_dir)

        self.common_image["monster"] = self.common_image["little_monster"] + self.common_image["big_monster"]

    def _go_map_page(self):
        self.timer.go_main_page()
        self.timer.Android.click(849, 261)

    def get_difficulty(self):
        """获取难度信息
        Returns:
            简单 0,困难 1
        这里同时有检查 _go_map_page 是否成功的功能
        """
        res = self.timer.wait_images(self.common_image["hard"] + self.common_image["easy"])
        if res is None:
            self.logger.error("ImageNotFoundErr", "difficulty image not found")
            self.timer.log_screen()
            raise ImageNotFoundErr()

        if self.timer.image_exist(self.common_image["hard"], need_screen_shot=False):
            return 0
        else:
            return 1

    def change_difficulty(self, chapter, retry=True):
        r_difficulty = int(chapter in "Hh")
        difficulty = self.get_difficulty()

        if r_difficulty != difficulty:
            time.sleep(0.2)
            self.timer.Android.click(66, 483)
            if self.get_difficulty() != r_difficulty:
                if retry:
                    return self.change_difficulty(chapter, False)
                self.timer.log_screen()
                raise ImageNotFoundErr("Can't change difficulty")


class PatrollingEvent(Event):
    """巡戈作战活动 类"""

    def __init__(self, timer: Timer, event_name, map_positions):
        """
        Args:
            map_positions : 从主页面点进活动后, 去到对应地图需要点的位置
                : 对于 E1~E3/H1~H3, 值为地图页面滑到最左边时的点击位置
                : 对于 E4~E6/H4~H6, 值为地图页面滑到最右边时点击的位置
                : map_positions[0] 为 None
                : map_positions[1] 为 E1 的点击位置
                : map_positions[2] 为 E2 的点击位置...
        """
        self.MAP_POSITIONS = map_positions
        super().__init__(timer, event_name)

    def enter_map(self, chapter, map):
        """从活动地图选择界面进入到巡游地图"""
        assert chapter in "HEhe"
        assert map in range(1, 7)
        self.change_difficulty(chapter)
        if map <= 3:
            self.timer.Android.swipe(100, 300, 600, 300, duration=0.4, delay=0.15)
            self.timer.Android.swipe(100, 300, 600, 300, duration=0.4, delay=0.15)
        else:
            self.timer.Android.swipe(600, 300, 100, 300, duration=0.4, delay=0.15)
            self.timer.Android.swipe(600, 300, 100, 300, duration=0.4, delay=0.15)
        self.timer.Android.click(*self.MAP_POSITIONS[map], delay=0.25)
        assert self.timer.wait_image(self.event_image[2]) is not False  # 是否成功进入地图

    def go_fight_prepare_page(self):
        self.timer.Android.click(789, 455)
        assert self.timer.wait_image(IMG.identify_images["fight_prepare_page"]) is not False

    def random_walk(self):
        "随机游走,寻找敌人"
        ways = ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1))
        import random

        way = random.choice(ways)
        position = (480, 270)
        step = (320, 180)
        end = (position[0] + step[0] * way[0], position[1] + step[1] * way[1])
        self.timer.Android.click(*end, delay=3)
        if self.timer.image_exist(self.event_image[1]):
            self.timer.Android.click(911, 37)
        if self.timer.image_exist(self.event_image[3]):
            self.timer.Android.click(30, 50)

    def get_close(self, images):
        while True:
            ret = self.timer.wait_images_position(images, confidence=0.8, gap=0.03, timeout=1)
            if CalcDis([ret[0]], [480]) ** 0.5 < 320 and CalcDis([ret[1]], [270]) ** 0.5 < 180:
                return ret
            if ret[0] > 480:
                ret = (ret[0] - 130, ret[1])
            else:
                ret = (ret[0] + 130, ret[1])
            self.timer.Android.click(*ret)

    def find(self, images, max_times=20):
        for _ in range(max_times):
            ret = self.timer.wait_images_position(images, confidence=0.75, gap=0.03, timeout=1)
            if ret is not None:
                return ret
            else:
                self.random_walk()
        return None
