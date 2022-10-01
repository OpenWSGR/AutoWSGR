from controller.run_timer import Timer
from utils.math_functions import CalcDis
from constants.image_templates import IMG, make_dir_templates, make_dir_templates_without_number
import os

class Event():
    
    def __init__(self, timer:Timer, event_name):
        image_dir = "data/images/event"
        common_dir = "data/images/event/common"
        enemy_dir = "data/images/event/enemy"
        event_dir = os.path.join(image_dir, event_name)
        self.timer = timer
        
        self.event_image = make_dir_templates(event_dir)
        self.common_image = make_dir_templates_without_number(common_dir)
        self.enemy_image = make_dir_templates_without_number(enemy_dir)
        
        self.common_image['monster'] = self.common_image['little_monster'] + self.common_image["big_monster"]

    def go_map_page(self):
        self.timer.go_main_page()
        self.timer.Android.click(849, 261)
        
    def get_difficulty(self):
        """获取难度信息

        Returns:
            简单 0,困难 1
        """
        self.timer.wait_images(self.common_image['hard'] + self.common_image['easy'])
        if(self.timer.image_exist(self.common_image['hard'])):
            return 0
        else:
            return 1
        
    def change_difficulty(self, chapter):
        r_difficulty = int(chapter in 'Hh') 
        difficulty = self.get_difficulty()
        
        if(r_difficulty != difficulty):
            self.timer.Android.click(66, 483)
            assert(self.get_difficulty() == r_difficulty)

class PatrollingEvent(Event):
    
    def enter_map(self, chapter, map):
        assert(chapter in 'HEhe')
        assert(map in range(1, 7))
        self.change_difficulty(chapter)
        if(map <= 3):
            self.timer.Android.swipe(100, 300, 600, 300, duration=.4, delay=.15)
            self.timer.Android.swipe(100, 300, 600, 300, duration=.4, delay=.15)
        else:
            self.timer.Android.swipe(600, 300, 100, 300, duration=.4, delay=.15)
            self.timer.Android.swipe(600, 300, 100, 300, duration=.4, delay=.15)
        self.MAP_POSITIONS = [None, (275, 118), (364, 383), (578, 147), (522, 337), (445, 158), (791, 157)]
        self.timer.Android.click(*self.MAP_POSITIONS[map], delay=.25)
        assert(self.timer.wait_image(self.event_image[2]) is not False) # 是否成功进入地图
        
    def go_fight_prepare_page(self):
        self.timer.Android.click(789, 455)
        assert(self.timer.wait_image(IMG.identify_images['fight_prepare_page']) is not False)
    
    def random_walk(self):
        "随机游走,寻找敌人"
        ways = ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1))
        import random
        way=random.choice(ways)
        position = (480, 270)
        step = (320, 180)
        end = (position[0] + step[0] * way[0], position[1] + step[1] * way[1])
        self.timer.Android.click(*end, delay=3)
        if(self.timer.image_exist(self.event_image[1])):
            self.timer.Android.click(911, 37)
        if(self.timer.image_exist(self.event_image[3])):
            self.timer.Android.click(30, 50)
    
    def get_close(self, images):
        while(True):
            ret = self.timer.wait_images_position(images, confidence=.8, gap=.03, timeout=1)
            if(CalcDis([ret[0]], [480]) ** .5 < 320 and CalcDis([ret[1]], [270]) ** .5 < 180):
                return ret
            if(ret[0] > 480):ret = (ret[0] - 130, ret[1])
            else: ret = (ret[0] + 130, ret[1])
            self.timer.Android.click(*ret)
    
    def find(self, images, max_times=20):
        for _ in range(max_times):
            ret = self.timer.wait_images_position(images, confidence=.75, gap=.03, timeout=1)
            if(ret is not None):
                return ret
            else:
                self.random_walk()
        return None
            
            
            
            
            