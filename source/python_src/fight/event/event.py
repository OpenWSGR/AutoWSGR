from fight.normal_fight import NormalFightInfo, NormalFightPlan
from controller.run_timer import Timer
from utils.io import get_all_files
from constants.image_templates import make_tmplate, make_dir_templates, make_dir_templates_without_number

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
