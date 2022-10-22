import time

from AutoWSGR.main import start_script
from AutoWSGR.constants.image_templates import IMG
from AutoWSGR.constants.other_constants import ALL_NORMAL_MAP, NORMAL_MAP_EVERY_CHAPTER
from AutoWSGR.constants.settings import S, show_all_debug_info
from AutoWSGR.fight.battle import BattlePlan
from AutoWSGR.fight.normal_fight import NormalFightPlan
from AutoWSGR.fight.exercise import NormalExercisePlan
from AutoWSGR.fight.decisive_battle import DecisiveBattle
from AutoWSGR.fight.event.event_2022_0928 import EventFightPlan20220928, EventFightPlan20220928_2
from AutoWSGR.game.game_operation import Expedition, GainBounds, RepairByBath
from AutoWSGR.port.ship import Fleet


timer = start_script('user_settings.yaml', to_main_page=False)
show_all_debug_info()
timer.goto_game_page('map_page')
# print(fight_plan._get_node(1))

decisive_battle = DecisiveBattle(timer, 6, 1, 'G', level1=["肥鱼", "U-1206", "狼群47", "射水鱼", "U-96", "U-1405"], \
    level2=["U-81", "大青花鱼"], flagship_priority=["U-1405", "狼群47"])
battle_plan = BattlePlan(timer, plan_path='battle/hard_Cruiser.yaml')
exercise_plan = NormalExercisePlan(timer, plan_path='exercise/plan_1.yaml')
expedition_plan = Expedition(timer)
start_time = last_time = time.time()
exercise_plan.run()
for _ in range(8):
    battle_plan.run()
# 自动出征
"""ret = fight_plan.run()
while ret == "success":
    ret = fight_plan.run(same_work=True)
    if time.time() - last_time >= 900:
        expedition_plan.run(True)
        GainBounds(timer)
        last_time = time.time()"""

# 自动远征
"""exercise_plan = NormalExercisePlan(timer, 'exercise/plan_1.yaml')
exercise_plan.run()"""
while True:
    RepairByBath(timer)
    expedition_plan.run(True)
    GainBounds(timer)
    time.sleep(360)
