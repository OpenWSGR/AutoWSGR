
from fight.normal_fight import NormalFightInfo, NormalFightPlan
from controller.run_timer import Timer
from utils.math_functions import CalcDis
from constants.image_templates import make_tmplate, IMG
from ..event import Event

import os

class EventFightPlan20220928(Event, NormalFightPlan):
    
    def __init__(self, timer: Timer, plan_path, default_path='plans/default.yaml', event="20220928"):
        self.event_name = event
        NormalFightPlan.__init__(self, timer, plan_path, default_path)
        Event.__init__(self, timer, event)
        self.MAP_POSITIONS = [None, (275, 118), (364, 383), (578, 147), (522, 337), (445, 158), (791, 157)]

    def load_fight_info(self):
        self.Info = EventFightInfo20220928(self.timer, self.chapter, self.map)
        self.Info.load_point_positions(os.path.join('data/map/event', self.event_name))
    
    def _change_fight_map(self, chapter, map):
        assert(chapter in 'HEhe')
        assert(map in range(1, 7))
        self.change_difficulty(chapter)
        if(map <= 3):
            self.timer.Android.swipe(100, 300, 600, 300, duration=.4, delay=.15)
            self.timer.Android.swipe(100, 300, 600, 300, duration=.4, delay=.15)
        else:
            self.timer.Android.swipe(600, 300, 100, 300, duration=.4, delay=.15)
            self.timer.Android.swipe(600, 300, 100, 300, duration=.4, delay=.15)
        self.timer.Android.click(*self.MAP_POSITIONS[map], delay=.25)
        
        assert(self.timer.wait_image(self.event_image[2]) is not None) # 是否成功进入地图
        
        while(self.timer.image_exist(self.common_image['little_monster']) == False): # 找到小怪物图标,点击下方进入主力决战
            while(self.timer.wait_images_position(self.common_image['monster'], timeout=1) is None):
                self.random_walk()
            if(self.timer.image_exist(self.common_image['little_monster'])):
                break
            ret = self.timer.wait_images_position(self.common_image['monster'])
            self.timer.Android.click(*ret)
        
        while(True):
            ret = self.timer.get_image_position(self.common_image['little_monster'][0])
            if(CalcDis([ret[0]], [480]) ** .5 < 320 and CalcDis([ret[1]], [270]) ** .5 < 180):
                break
            if(ret[0] > 480):ret = (ret[0] - 130, ret[1])
            else: ret = (ret[0] + 130, ret[1])
            self.timer.Android.click(*ret)
            
        self.timer.Android.click(ret[0], ret[1] + 60)
        assert(self.timer.wait_image(self.event_image[1]))
        
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
        self.timer.Android.click(*end)
        

class EventFightInfo20220928(Event, NormalFightInfo):
    
    def __init__(self, timer: Timer, chapter, map, event="20220928") -> None:
        NormalFightInfo.__init__(self, timer, chapter, map)
        Event.__init__(self, timer, event)
        self.map_image = self.event_image[1]
        self.end_page = 'unknown_page'
        self.state2image["map_page"] = [self.map_image, 5]
        
    